import asyncio
import base64
import json
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, Mock, patch

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from monitoring_app import signals as lesson_signals
from monitoring_app import tasks as monitoring_tasks
from monitoring_app.admin import (
    ClassLocationAdmin,
    PublicHolidayAdmin,
    StaffAdmin,
    admin_site,
)
from monitoring_app.attendance_fetcher import _compute_attendance_from_events
from monitoring_app.cache_conf import Cache
from monitoring_app.consumers import (
    PHOTO_WS_PROTOCOL,
    STATE_CREATED_NO_PHOTO,
    STATE_DELETED,
    STATE_PHOTO_ATTACHED,
    STATE_UPDATED_META,
    PhotoConsumer,
)
from monitoring_app.models import (
    APIKey,
    ChildDepartment,
    ClassLocation,
    LessonAttendance,
    Position,
    PublicHoliday,
    RemoteWork,
    Staff,
    StaffAttendance,
)
from monitoring_app.views import get_staff_detail
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()


class RemoteWorkAdminTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name="John", surname="Doe")
        self.remote_work = RemoteWork.objects.create(
            staff=self.staff, permanent_remote=True
        )

    def test_get_remote_status(self):
        self.assertEqual(
            self.remote_work.get_remote_status(), "Постоянная дистанционная работа"
        )


class StaffDetailTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(pin="S1000S", name="John", surname="Doe")

    def _create_lesson(
        self,
        event_dt,
        *,
        auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_CLEAN,
        manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_NONE,
    ):
        return LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="Math",
            tutor_id=1,
            tutor="Tutor",
            first_in=event_dt,
            last_out=event_dt + timedelta(hours=1),
            latitude=43.2389,
            longitude=76.8897,
            date_at=event_dt.date(),
            photo_spoof_status=auto_status,
            photo_manual_verdict=manual_verdict,
        )

    def _create_staff_attendance(self, event_dt, area_name="цос"):
        return StaffAttendance.objects.create(
            staff=self.staff,
            date_at=event_dt.date() + timedelta(days=1),
            first_in=event_dt,
            last_out=event_dt + timedelta(hours=6),
            area_name_in=area_name,
            area_name_out=area_name,
        )

    def test_get_staff_detail(self):
        start_date = datetime(2023, 1, 1).date()
        end_date = datetime(2023, 1, 31).date()
        detail = get_staff_detail(self.staff, start_date, end_date)
        self.assertIn("contract_type", detail)
        self.assertIn("salary", detail)

    def test_get_staff_detail_includes_review_but_excludes_suspicious_lesson(self):
        review_day = timezone.make_aware(datetime(2023, 1, 10, 9, 0))
        suspicious_day = timezone.make_aware(datetime(2023, 1, 11, 9, 0))
        clean_day = timezone.make_aware(datetime(2023, 1, 12, 9, 0))

        self._create_lesson(
            review_day,
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_REVIEW,
        )
        self._create_lesson(
            suspicious_day,
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
        )
        self._create_lesson(clean_day)

        detail = get_staff_detail(
            self.staff,
            datetime(2023, 1, 1).date(),
            datetime(2023, 1, 31).date(),
        )

        self.assertIn("10-01-2023", detail["attendance"])  # review
        self.assertIn("12-01-2023", detail["attendance"])  # clean
        self.assertNotIn("11-01-2023", detail["attendance"])  # suspicious

    def test_get_staff_detail_excludes_entire_lesson_day_when_any_lesson_is_suspicious(
        self,
    ):
        mixed_day = timezone.make_aware(datetime(2023, 1, 13, 9, 0))

        self._create_lesson(mixed_day)
        self._create_lesson(
            mixed_day + timedelta(hours=2),
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
        )

        detail = get_staff_detail(
            self.staff,
            datetime(2023, 1, 1).date(),
            datetime(2023, 1, 31).date(),
        )

        self.assertNotIn("13-01-2023", detail["attendance"])

    def test_get_staff_detail_excludes_entire_day_for_manual_suspicious_lesson(self):
        mixed_day = timezone.make_aware(datetime(2023, 1, 14, 9, 0))

        self._create_lesson(mixed_day)
        self._create_lesson(
            mixed_day + timedelta(hours=2),
            manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_SUSPICIOUS,
        )

        detail = get_staff_detail(
            self.staff,
            datetime(2023, 1, 1).date(),
            datetime(2023, 1, 31).date(),
        )

        self.assertNotIn("14-01-2023", detail["attendance"])

    def test_get_staff_detail_keeps_staff_attendance_when_lesson_day_is_suspicious(
        self,
    ):
        mixed_day = timezone.make_aware(datetime(2023, 1, 15, 9, 0))

        self._create_staff_attendance(mixed_day)
        self._create_lesson(
            mixed_day + timedelta(hours=2),
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
        )

        detail = get_staff_detail(
            self.staff,
            datetime(2023, 1, 1).date(),
            datetime(2023, 1, 31).date(),
        )

        self.assertIn("15-01-2023", detail["attendance"])

    def test_get_staff_detail_keeps_day_when_lessons_are_not_suspicious(self):
        mixed_day = timezone.make_aware(datetime(2023, 1, 16, 9, 0))

        self._create_lesson(
            mixed_day,
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_PENDING,
        )
        self._create_lesson(
            mixed_day + timedelta(hours=2),
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_REVIEW,
        )
        self._create_lesson(
            mixed_day + timedelta(hours=4),
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_ERROR,
        )

        detail = get_staff_detail(
            self.staff,
            datetime(2023, 1, 1).date(),
            datetime(2023, 1, 31).date(),
        )

        self.assertIn("16-01-2023", detail["attendance"])

    def test_get_staff_detail_percent_for_period_uses_effective_work_seconds(self):
        """Регрессия: при наличии effective_work_seconds день должен входить в средний % периода.

        Раньше накопление шло только в ветке first_in/last_out, из‑за чего общий % был 0.
        """
        work_day = timezone.make_aware(datetime(2023, 1, 17, 9, 0))
        eight_hours = 8 * 3600
        StaffAttendance.objects.create(
            staff=self.staff,
            date_at=work_day.date() + timedelta(days=1),
            first_in=None,
            last_out=None,
            effective_work_seconds=eight_hours,
            area_name_in=None,
            area_name_out=None,
        )
        detail = get_staff_detail(
            self.staff,
            datetime(2023, 1, 1).date(),
            datetime(2023, 1, 31).date(),
        )
        self.assertGreater(
            detail["percent_for_period"],
            0,
            "percent_for_period must reflect days with effective_work_seconds only",
        )


class LessonAttendanceDayLevelApiFiltersTest(APITestCase):
    def setUp(self):
        super().setUp()
        Cache.clear()
        self.user = User.objects.create_user(
            username="lesson-day-api-user",
            password="12345",
        )
        self.api_key = APIKey.objects.create(
            key_name="Lesson Day API Key",
            created_by=self.user,
        )
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)

        self.department = ChildDepartment.objects.create(
            id="D-LESSON-DAY",
            name="Lesson Day Department",
        )
        self.student_position = Position.objects.create(name="Студент")
        self.staff = Staff.objects.create(
            pin="S5555S",
            name="Api",
            surname="Student",
            department=self.department,
        )
        self.staff.positions.add(self.student_position)
        ClassLocation.objects.create(
            name="Абылай",
            address="Проспект Абылай хана, 51/53",
            latitude=43.2389,
            longitude=76.8897,
        )
        self.target_day = datetime(2026, 3, 10).date()

    def _create_lesson(
        self,
        *,
        auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_CLEAN,
        manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_NONE,
        hour=9,
    ):
        first_in = timezone.make_aware(
            datetime(
                self.target_day.year,
                self.target_day.month,
                self.target_day.day,
                hour,
                0,
            )
        )
        return LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="Math",
            tutor_id=1,
            tutor="Tutor",
            first_in=first_in,
            last_out=first_in + timedelta(hours=1),
            latitude=43.2389,
            longitude=76.8897,
            date_at=self.target_day,
            photo_spoof_status=auto_status,
            photo_manual_verdict=manual_verdict,
        )

    def _create_staff_attendance(self):
        first_in = timezone.make_aware(
            datetime(
                self.target_day.year,
                self.target_day.month,
                self.target_day.day,
                8,
                30,
            )
        )
        return StaffAttendance.objects.create(
            staff=self.staff,
            date_at=self.target_day + timedelta(days=1),
            first_in=first_in,
            last_out=first_in + timedelta(hours=6),
            area_name_in="цос",
            area_name_out="цос",
        )

    def test_map_location_excludes_all_lessons_for_suspicious_day(self):
        self._create_lesson(hour=9)
        self._create_lesson(
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            hour=11,
        )

        response = self.client.get(
            reverse("locations"),
            {"employees": "true", "date_at": self.target_day.isoformat()},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_map_location_keeps_staff_attendance_when_lesson_day_is_suspicious(self):
        self._create_staff_attendance()
        self._create_lesson(
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            hour=11,
        )

        response = self.client.get(
            reverse("locations"),
            {"employees": "true", "date_at": self.target_day.isoformat()},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["employees"], 1)

    def test_staff_attendance_stats_excludes_suspicious_lesson_day(self):
        self._create_lesson(hour=9)
        self._create_lesson(
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            hour=11,
        )

        response = self.client.get(
            reverse("staff-attendance-stats"),
            {"date": self.target_day.isoformat(), "pin": self.department.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["present_staff_count"], 0)
        self.assertEqual(response.data["absent_staff_count"], 1)

    def test_staff_attendance_stats_keeps_staff_attendance_when_lesson_day_is_suspicious(
        self,
    ):
        self._create_staff_attendance()
        self._create_lesson(
            auto_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            hour=11,
        )

        response = self.client.get(
            reverse("staff-attendance-stats"),
            {"date": self.target_day.isoformat(), "pin": self.department.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["present_staff_count"], 1)
        self.assertEqual(response.data["absent_staff_count"], 0)

    def test_department_stats_excludes_suspicious_lesson_day(self):
        self._create_lesson(hour=9)
        self._create_lesson(
            manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_SUSPICIOUS,
            hour=11,
        )

        response = self.client.get(
            reverse("department-stats", kwargs={"department_id": self.department.id}),
            {
                "start_date": self.target_day.isoformat(),
                "end_date": self.target_day.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attendance_entry = response.data["results"][0][self.target_day.isoformat()][
            "attendance"
        ][0]
        self.assertIsNone(attendance_entry["first_in"])
        self.assertIsNone(attendance_entry["last_out"])


class LessonTaskStatusTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.staff = Staff.objects.create(name="John", surname="Doe", pin="st1234")
        self.lesson_attendance = LessonAttendance.objects.create(
            staff=self.staff,
            tutor_id=1,
            first_in=timezone.now(),
            latitude=43.207674,
            longitude=76.851377,
        )
        self.task_id = "some-task-id"
        self.api_key = APIKey.objects.create(key_name="Test Key", created_by=self.user)
        self.token = Token.objects.create(user=self.user)

    def test_check_lesson_task_status(self):
        url = reverse("check_lesson_task_status", args=[self.task_id])
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)
        response = self.client.get(url)
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_202_ACCEPTED]
        )
        if response.status_code == status.HTTP_200_OK:
            self.assertIn("status", response.data)
        elif response.status_code == status.HTTP_202_ACCEPTED:
            self.assertIn("message", response.data)


class LessonAttendanceAutoCloseTaskTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(
            pin="S7000S",
            name="Late",
            surname="Lesson",
        )

    def _create_lesson(self, first_in, *, date_at=None):
        return LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="Duty",
            tutor_id=1,
            tutor="Tutor",
            first_in=first_in,
            last_out=None,
            latitude=43.2389,
            longitude=76.8897,
            date_at=date_at or first_in.date(),
        )

    @override_settings(
        LESSON_ATTENDANCE_AUTO_CLOSE_DEFAULT_MINUTES=120,
        LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_START_HOUR=18,
        LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_MINUTES=90,
        LESSON_ATTENDANCE_AUTO_CLOSE_LATE_START_HOUR=20,
        LESSON_ATTENDANCE_AUTO_CLOSE_LATE_MINUTES=60,
    )
    def test_update_lesson_attendance_last_out_uses_time_bands_and_caps_day_end(self):
        target_day = timezone.localdate() - timedelta(days=1)
        day_lesson = self._create_lesson(
            timezone.make_aware(
                datetime.combine(target_day, datetime.min.time())
            ).replace(
                hour=14,
                minute=0,
            )
        )
        evening_lesson = self._create_lesson(
            timezone.make_aware(
                datetime.combine(target_day, datetime.min.time())
            ).replace(
                hour=18,
                minute=0,
            )
        )
        late_lesson = self._create_lesson(
            timezone.make_aware(
                datetime.combine(target_day, datetime.min.time())
            ).replace(
                hour=20,
                minute=30,
            )
        )
        end_of_day_lesson = self._create_lesson(
            timezone.make_aware(
                datetime.combine(target_day, datetime.min.time())
            ).replace(
                hour=23,
                minute=30,
            )
        )

        monitoring_tasks.update_lesson_attendance_last_out()

        day_lesson.refresh_from_db()
        evening_lesson.refresh_from_db()
        late_lesson.refresh_from_db()
        end_of_day_lesson.refresh_from_db()

        self.assertEqual(
            timezone.localtime(day_lesson.last_out),
            timezone.localtime(day_lesson.first_in) + timedelta(minutes=120),
        )
        self.assertEqual(
            timezone.localtime(evening_lesson.last_out),
            timezone.localtime(evening_lesson.first_in) + timedelta(minutes=90),
        )
        self.assertEqual(
            timezone.localtime(late_lesson.last_out),
            timezone.localtime(late_lesson.first_in) + timedelta(minutes=60),
        )
        self.assertEqual(
            timezone.localtime(end_of_day_lesson.last_out),
            timezone.make_aware(
                datetime.combine(target_day, datetime.max.time()),
                timezone.get_current_timezone(),
            ),
        )

    @override_settings(
        LESSON_ATTENDANCE_AUTO_CLOSE_DEFAULT_MINUTES=120,
        LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_START_HOUR=18,
        LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_MINUTES=90,
        LESSON_ATTENDANCE_AUTO_CLOSE_LATE_START_HOUR=20,
        LESSON_ATTENDANCE_AUTO_CLOSE_LATE_MINUTES=60,
    )
    def test_update_lesson_attendance_last_out_does_not_close_day_lesson_too_early(
        self,
    ):
        fixed_now = timezone.make_aware(datetime(2026, 3, 20, 15, 0))
        lesson = self._create_lesson(
            fixed_now - timedelta(minutes=70),
            date_at=fixed_now.date(),
        )

        with patch("monitoring_app.tasks.timezone.now", return_value=fixed_now):
            monitoring_tasks.update_lesson_attendance_last_out()

        lesson.refresh_from_db()
        self.assertIsNone(lesson.last_out)


class StaffAdminAttendanceHistoryTest(TestCase):
    def setUp(self):
        Cache.clear()
        self.staff_admin = StaffAdmin(Staff, admin_site)
        self.staff = Staff.objects.create(
            pin="S8123S",
            name="Admin",
            surname="History",
        )

    def test_attendance_history_uses_staff_event_day_not_save_day(self):
        event_in = timezone.make_aware(datetime(2026, 3, 10, 9, 5))
        StaffAttendance.objects.create(
            staff=self.staff,
            date_at=datetime(2026, 3, 11).date(),
            first_in=event_in,
            last_out=event_in + timedelta(hours=8),
            area_name_in="цос",
            area_name_out="цос",
        )

        with patch(
            "monitoring_app.admin.timezone.localdate",
            return_value=datetime(2026, 3, 12).date(),
        ):
            html = str(self.staff_admin.attendance_history(self.staff))

        self.assertRegex(
            html,
            r'(?s)data-attendance-day="2026-03-10".*?09:05.*?Выгрузка.*?11\.03\.2026',
        )


class ClassLocationAdminAttendanceStatsTest(TestCase):
    def setUp(self):
        Cache.clear()
        self.factory = RequestFactory()
        self.location_admin = ClassLocationAdmin(ClassLocation, admin_site)
        self.staff = Staff.objects.create(
            pin="S9001S",
            name="Geo",
            surname="Case",
        )
        self.location = ClassLocation.objects.create(
            name="Точка А",
            address="Адрес А",
            latitude=43.2389,
            longitude=76.8897,
            acceptance_radius_m=90,
        )

    def test_attendance_stats_uses_configured_location_radius(self):
        lesson_time = timezone.make_aware(datetime(2026, 3, 5, 9, 0))
        LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="Math",
            tutor_id=1,
            tutor="Tutor",
            first_in=lesson_time,
            last_out=lesson_time + timedelta(hours=1),
            latitude=self.location.latitude,
            longitude=self.location.longitude + 0.0011,
            date_at=lesson_time.date(),
        )
        LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="Math",
            tutor_id=1,
            tutor="Tutor",
            first_in=lesson_time + timedelta(days=1),
            last_out=lesson_time + timedelta(days=1, hours=1),
            latitude=self.location.latitude,
            longitude=self.location.longitude + 0.0020,
            date_at=(lesson_time + timedelta(days=1)).date(),
        )

        fixed_now = timezone.make_aware(datetime(2026, 3, 20, 12, 0))
        with patch("monitoring_app.admin.timezone.now", return_value=fixed_now), patch(
            "monitoring_app.admin.timezone.localdate",
            return_value=fixed_now.date(),
        ):
            html = str(self.location_admin.attendance_stats(self.location))

        self.assertIn("Всего отметок 1", html)
        self.assertIn("аналитический радиус 90 м", html)

    def test_changelist_queryset_annotates_counts_for_sorting_and_filtering(self):
        busy_location = ClassLocation.objects.create(
            name="Точка B",
            address="Адрес B",
            latitude=43.24,
            longitude=76.89,
            acceptance_radius_m=120,
        )
        quiet_location = ClassLocation.objects.create(
            name="Точка C",
            address="Адрес C",
            latitude=43.25,
            longitude=76.90,
            acceptance_radius_m=80,
        )
        lesson_time = timezone.make_aware(datetime(2026, 3, 10, 9, 0))
        for offset in range(3):
            LessonAttendance.objects.create(
                staff=self.staff,
                subject_name=f"Busy {offset}",
                tutor_id=1,
                tutor="Tutor",
                first_in=lesson_time + timedelta(days=offset),
                last_out=lesson_time + timedelta(days=offset, hours=1),
                latitude=busy_location.latitude,
                longitude=busy_location.longitude + 0.0004,
                date_at=(lesson_time + timedelta(days=offset)).date(),
            )
        request = self.factory.get(
            "/admin/monitoring_app/classlocation/",
            {"attendance_period": "180"},
        )

        queryset = self.location_admin.get_queryset(request).order_by(
            "-_attendance_hits_period",
            "id",
        )
        counts_by_id = {
            item.id: getattr(item, "_attendance_hits_period")
            for item in queryset
            if item.id in {busy_location.id, quiet_location.id}
        }

        self.assertEqual(counts_by_id[busy_location.id], 3)
        self.assertEqual(counts_by_id[quiet_location.id], 0)

        zero_qs = queryset.filter(_attendance_hits_period=0)
        self.assertIn(quiet_location.id, list(zero_qs.values_list("id", flat=True)))
        self.assertNotIn(busy_location.id, list(zero_qs.values_list("id", flat=True)))

    def test_changelist_default_period_uses_calendar_month_window(self):
        lesson_in_old_partial_month = timezone.make_aware(datetime(2025, 9, 25, 9, 0))
        lesson_in_default_window = timezone.make_aware(datetime(2025, 10, 5, 9, 0))
        for lesson_time in (lesson_in_old_partial_month, lesson_in_default_window):
            LessonAttendance.objects.create(
                staff=self.staff,
                subject_name=f"Window {lesson_time.date()}",
                tutor_id=1,
                tutor="Tutor",
                first_in=lesson_time,
                last_out=lesson_time + timedelta(hours=1),
                latitude=self.location.latitude,
                longitude=self.location.longitude,
                date_at=lesson_time.date(),
            )

        fixed_now = timezone.make_aware(datetime(2026, 3, 20, 12, 0))
        request = self.factory.get("/admin/monitoring_app/classlocation/")
        with patch("monitoring_app.admin.timezone.now", return_value=fixed_now), patch(
            "monitoring_app.admin.timezone.localdate",
            return_value=fixed_now.date(),
        ):
            queryset = self.location_admin.get_queryset(request)
            location = queryset.get(pk=self.location.pk)

        self.assertEqual(getattr(location, "_attendance_hits_period"), 1)

    def test_changelist_assigns_overlapping_visit_to_nearest_location(self):
        near_location = ClassLocation.objects.create(
            name="Точка B",
            address="Адрес B",
            latitude=43.2389,
            longitude=76.8910,
            acceptance_radius_m=250,
        )
        lesson_time = timezone.make_aware(datetime(2026, 3, 10, 9, 0))
        LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="Nearest",
            tutor_id=1,
            tutor="Tutor",
            first_in=lesson_time,
            last_out=lesson_time + timedelta(hours=1),
            latitude=43.2389,
            longitude=76.8901,
            date_at=lesson_time.date(),
        )
        request = self.factory.get(
            "/admin/monitoring_app/classlocation/",
            {"attendance_period": "180"},
        )

        queryset = self.location_admin.get_queryset(request)
        counts_by_id = {
            item.id: getattr(item, "_attendance_hits_period")
            for item in queryset
            if item.id in {self.location.id, near_location.id}
        }

        self.assertEqual(counts_by_id[self.location.id], 1)
        self.assertEqual(counts_by_id[near_location.id], 0)


class PublicHolidayAdminInitialDataTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = PublicHolidayAdmin(PublicHoliday, admin_site)

    def test_get_changeform_initial_data_sets_typed_defaults(self):
        request = self.factory.get("/admin/monitoring_app/publicholiday/add/")

        with patch(
            "monitoring_app.admin.timezone.localdate",
            return_value=datetime(2026, 3, 20).date(),
        ):
            initial = self.admin.get_changeform_initial_data(request)

        self.assertEqual(initial["date"], datetime(2026, 3, 20).date())
        self.assertIs(initial["is_working_day"], False)


class FetcherViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fetcher_user", password="12345")
        self.api_key = APIKey.objects.create(
            key_name="Fetcher Test Key",
            created_by=self.user,
        )
        self.url = reverse("fetcher")
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_success_response_contains_summary_and_duration(
        self, mock_get_all_attendance
    ):
        mock_get_all_attendance.return_value = {
            "days": 2,
            "source_date": "2026-02-06",
            "save_date": "2026-02-07",
            "total_pins": 10,
            "successful_requests": 10,
            "failed_requests": 0,
            "pins_with_events": 8,
            "pins_without_events": 2,
            "created_records": 5,
            "updated_records": 5,
            "event_time_parse_errors": 0,
            "failed_pins": [],
            "errors": [],
        }

        response = self.client.get(self.url, {"days": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("message"), "Done")
        self.assertIn("duration_seconds", response.data)
        self.assertIn("duration_human_readable", response.data)
        self.assertIn("fetch_summary", response.data)
        self.assertEqual(response.data.get("status"), "success")
        self.assertEqual(response.data["fetch_summary"]["failed_requests"], 0)
        mock_get_all_attendance.assert_awaited_once_with(days=2)

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_partial_errors_returns_207(self, mock_get_all_attendance):
        mock_get_all_attendance.return_value = {
            "days": 2,
            "source_date": "2026-02-06",
            "save_date": "2026-02-07",
            "total_pins": 10,
            "successful_requests": 7,
            "failed_requests": 3,
            "pins_with_events": 6,
            "pins_without_events": 1,
            "created_records": 4,
            "updated_records": 3,
            "event_time_parse_errors": 0,
            "failed_pins": ["T111", "T222", "T333"],
            "errors": [{"pin": "T111", "status": 401}],
        }

        response = self.client.get(self.url, {"days": 2})

        self.assertEqual(response.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertEqual(response.data.get("status"), "partial_error")
        self.assertEqual(response.data.get("message"), "Done with errors.")
        self.assertEqual(response.data["fetch_summary"]["failed_requests"], 3)
        self.assertNotIn("errors", response.data["fetch_summary"])
        self.assertIn("error_statuses", response.data["fetch_summary"])

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_all_failed_returns_502(self, mock_get_all_attendance):
        mock_get_all_attendance.return_value = {
            "days": 2,
            "source_date": "2026-02-06",
            "save_date": "2026-02-07",
            "total_pins": 10,
            "successful_requests": 0,
            "failed_requests": 10,
            "pins_with_events": 0,
            "pins_without_events": 0,
            "created_records": 0,
            "updated_records": 0,
            "event_time_parse_errors": 0,
            "failed_pins": ["T111"],
            "errors": [{"pin": "T111", "status": 401}],
        }

        response = self.client.get(self.url, {"days": 2})

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data.get("status"), "failed")
        self.assertEqual(response.data.get("message"), "Fetcher failed.")

    def test_fetcher_invalid_days_returns_400(self):
        response = self.client.get(self.url, {"days": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("monitoring_app.views.cache.add", return_value=False)
    def test_fetcher_returns_429_when_run_is_already_in_progress(self, _mock_cache_add):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data.get("status"), "busy")

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_response_includes_ambiguous_exit_counters(
        self, mock_get_all_attendance
    ):
        mock_get_all_attendance.return_value = {
            "days": 1,
            "source_date": "2026-03-01",
            "save_date": "2026-03-02",
            "total_pins": 4,
            "successful_requests": 4,
            "failed_requests": 0,
            "pins_with_events": 4,
            "pins_without_events": 0,
            "created_records": 2,
            "updated_records": 2,
            "event_time_parse_errors": 0,
            "ambiguous_exit_candidates": 3,
            "ambiguous_resolved_as_exit": 2,
            "ambiguous_resolved_as_transfer": 1,
            "failed_pins": [],
            "errors": [],
        }

        response = self.client.get(self.url, {"days": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["fetch_summary"]
        self.assertEqual(summary["ambiguous_exit_candidates"], 3)
        self.assertEqual(summary["ambiguous_resolved_as_exit"], 2)
        self.assertEqual(summary["ambiguous_resolved_as_transfer"], 1)


class AppVersionEndpointTest(SimpleTestCase):
    def test_app_version_returns_live_frontend_metadata_with_no_store_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frontend_dir = Path(temp_dir) / "frontend"
            dist_dir = frontend_dir / "dist"
            dist_dir.mkdir(parents=True, exist_ok=True)
            expected_payload = {
                "buildId": "2026-04-01_12-30-45_123",
                "builtAtIso": "2026-04-01T12:30:45.123Z",
                "buildEpochMs": 1775046645123,
            }
            (dist_dir / "app-version.json").write_text(
                json.dumps(expected_payload),
                encoding="utf-8",
            )

            with override_settings(FRONTEND_DIR=frontend_dir):
                response = self.client.get(reverse("app-version"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), expected_payload)
        cache_control = response.get("Cache-Control", "")
        self.assertIn("no-store", cache_control)
        self.assertIn("no-cache", cache_control)
        self.assertIn("must-revalidate", cache_control)
        self.assertIn("max-age=0", cache_control)
        self.assertEqual(response.get("Pragma"), "no-cache")
        self.assertEqual(response.get("Expires"), "0")

    def test_app_version_returns_503_when_metadata_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frontend_dir = Path(temp_dir) / "frontend"
            (frontend_dir / "dist").mkdir(parents=True, exist_ok=True)

            with override_settings(FRONTEND_DIR=frontend_dir):
                response = self.client.get(reverse("app-version"))

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.json(),
            {"error": "Build version metadata is unavailable."},
        )


class SuspiciousLocationPatternsApiTest(APITestCase):
    def setUp(self):
        super().setUp()
        Cache.clear()
        self.user = User.objects.create_user(
            username="suspicious-location-user",
            password="12345",
        )
        self.api_key = APIKey.objects.create(
            key_name="Suspicious Location API Key",
            created_by=self.user,
        )
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)
        self.url = reverse("suspicious-location-patterns")

    def _create_department(
        self, dept_id: str, name: str = "Test Group"
    ) -> ChildDepartment:
        return ChildDepartment.objects.create(id=dept_id, name=name)

    def _create_staff(self, pin_short: str, department: ChildDepartment) -> Staff:
        return Staff.objects.create(
            pin=f"S{pin_short}S",
            name=f"Name{pin_short}",
            surname=f"Surname{pin_short}",
            department=department,
        )

    def _create_lesson(
        self,
        staff: Staff,
        date_value: date,
        *,
        latitude: float,
        longitude: float,
        hour: int,
        minute: int = 0,
    ) -> LessonAttendance:
        first_in = timezone.make_aware(
            datetime(
                date_value.year,
                date_value.month,
                date_value.day,
                hour,
                minute,
            )
        )
        return LessonAttendance.objects.create(
            staff=staff,
            subject_name="Math",
            tutor_id=1,
            tutor="Tutor",
            first_in=first_in,
            last_out=first_in + timedelta(hours=1),
            latitude=latitude,
            longitude=longitude,
            date_at=date_value,
        )

    def _users_index(self, response) -> dict[str, dict[str, Any]]:
        return response.data["usersByPin"]

    def _dates_index(self, response) -> dict[str, dict[str, dict[str, Any]]]:
        return {
            date_value: item["usersByPin"]
            for date_value, item in response.data["datesByDate"].items()
        }

    def test_scattered_day_below_share_threshold_does_not_flag_by_default(self):
        department = self._create_department("9054", "GM22 403 Б а б")
        ClassLocation.objects.create(
            name="Known Campus",
            address="Known Address",
            latitude=43.23235,
            longitude=76.9130,
            acceptance_radius_m=200,
        )
        coordinates = [
            (43.2322502, 76.9129868),
            (43.2322513, 76.9129868),
            (43.2322540, 76.9129868),
            (43.2322502, 76.9129868),
            (43.2324219, 76.9130936),
            (43.2324219, 76.9130936),
            (43.2323952, 76.9129944),
            (43.2327140, 76.8561556),
            (43.2327385, 76.8561020),
        ]
        target_date = datetime(2026, 3, 27).date()
        for index, (lat, lon) in enumerate(coordinates, start=1):
            staff = self._create_staff(str(25800 + index), department)
            self._create_lesson(
                staff,
                target_date,
                latitude=lat,
                longitude=lon,
                hour=9,
            )
            self._create_lesson(
                staff,
                target_date,
                latitude=lat,
                longitude=lon,
                hour=11,
            )

        response = self.client.get(
            self.url,
            {
                "child_department_id": department.id,
                "date_from": "2026-03-27",
                "date_to": "2026-03-27",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["staffAnalyzed"], 9)
        self.assertEqual(response.data["summary"]["staffFlagged"], 0)
        self.assertEqual(response.data["summary"]["datesFlagged"], 0)
        self.assertEqual(response.data["datesByDate"], {})
        self.assertEqual(response.data["usersByPin"], {})

    def test_shared_point_known_location_flags_by_default(self):
        department = self._create_department("9054", "GM22 403 Б а б")
        ClassLocation.objects.create(
            name="Known Campus",
            address="Known Address",
            latitude=43.23235,
            longitude=76.9130,
            acceptance_radius_m=200,
        )
        coordinates_by_day = {
            datetime(2026, 3, 26).date(): [
                (43.2322502, 76.9129868),
                (43.2322513, 76.9129868),
                (43.2322540, 76.9129868),
                (43.2322502, 76.9129868),
                (43.2322520, 76.9129868),
                (43.2322559, 76.9129868),
                (43.2324219, 76.9130936),
                (43.2324219, 76.9130936),
                (43.2323952, 76.9129944),
                (43.2325058, 76.9131012),
            ],
            datetime(2026, 3, 27).date(): [
                (43.2322502, 76.9129868),
                (43.2322388, 76.9129868),
                (43.2322292, 76.9129829),
                (43.2323200, 76.9127800),
                (43.2324219, 76.9130936),
                (43.2324219, 76.9130936),
                (43.2324200, 76.9130900),
                (43.2324240, 76.9130920),
                (43.2324250, 76.9130450),
                (43.2324280, 76.9129510),
            ],
        }
        staff_members = [
            self._create_staff(str(25900 + index), department) for index in range(10)
        ]
        for target_date, coords in coordinates_by_day.items():
            for staff, (lat, lon) in zip(staff_members, coords):
                self._create_lesson(
                    staff,
                    target_date,
                    latitude=lat,
                    longitude=lon,
                    hour=9,
                )

        response = self.client.get(
            self.url,
            {
                "child_department_id": department.id,
                "date_from": "2026-03-26",
                "date_to": "2026-03-27",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["staffAnalyzed"], 10)
        self.assertEqual(response.data["summary"]["staffFlagged"], 10)
        self.assertEqual(response.data["summary"]["datesFlagged"], 2)
        self.assertIn("shared_point", response.data["reasonLegend"])
        self.assertNotIn("group_exact", response.data["reasonLegend"])
        self.assertNotIn("group_near", response.data["reasonLegend"])
        self.assertEqual(
            response.data["reasonLegend"]["multi_day_pattern"],
            "Такой же паттерн повторялся в несколько разных дней.",
        )
        dates_index = self._dates_index(response)
        self.assertEqual(sorted(dates_index.keys()), ["2026-03-26", "2026-03-27"])
        self.assertEqual(len(dates_index["2026-03-26"]), 6)
        self.assertEqual(len(dates_index["2026-03-27"]), 6)
        users_index = self._users_index(response)
        self.assertEqual(len(users_index), 10)
        for item in users_index.values():
            self.assertIn(item["highestSeverity"], {"high", "critical"})
            self.assertGreaterEqual(len(item["datesByDate"]), 1)
            for day_item in item["datesByDate"].values():
                self.assertIn(day_item["severity"], {"high", "critical"})
                self.assertEqual(day_item["reason"][0], "shared_point")

    def test_group_exact_outside_known_location_returns_high_results(self):
        department = self._create_department("D-GROUP-EXACT")
        ClassLocation.objects.create(
            name="Far Campus",
            address="Far Address",
            latitude=43.2000,
            longitude=76.8000,
            acceptance_radius_m=120,
        )
        target_date = datetime(2026, 3, 27).date()
        selected_staff = [
            self._create_staff("1001", department),
            self._create_staff("1002", department),
            self._create_staff("1003", department),
        ]
        for staff in selected_staff:
            self._create_lesson(
                staff,
                target_date,
                latitude=43.2500001,
                longitude=76.9300001,
                hour=10,
            )

        response = self.client.get(
            self.url,
            {
                "staff_pins": "1001,S1002S,1003",
                "date_from": "2026-03-27",
                "date_to": "2026-03-27",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["staffAnalyzed"], 3)
        self.assertEqual(response.data["summary"]["staffFlagged"], 3)
        self.assertEqual(response.data["summary"]["datesFlagged"], 1)
        returned_pins = list(response.data["usersByPin"].keys())
        self.assertEqual(returned_pins, ["1001", "1002", "1003"])
        for item in response.data["usersByPin"].values():
            self.assertEqual(item["highestSeverity"], "high")
            self.assertEqual(
                item["datesByDate"],
                {
                    "2026-03-27": {
                        "severity": "high",
                        "groupDays": 1,
                        "lat": 43.2500001,
                        "lon": 76.9300001,
                        "locationName": "Far Campus",
                        "reason": ["shared_point"],
                    }
                },
            )

    def test_group_exact_multi_day_outside_known_location_returns_critical(self):
        department = self._create_department("D-GROUP-CRITICAL")
        ClassLocation.objects.create(
            name="Far Campus",
            address="Far Address",
            latitude=43.2000,
            longitude=76.8000,
            acceptance_radius_m=120,
        )
        staff_members = [
            self._create_staff("2001", department),
            self._create_staff("2002", department),
            self._create_staff("2003", department),
        ]
        for target_date in (
            datetime(2026, 3, 26).date(),
            datetime(2026, 3, 27).date(),
        ):
            for staff in staff_members:
                self._create_lesson(
                    staff,
                    target_date,
                    latitude=43.2600001,
                    longitude=76.9400001,
                    hour=9,
                )

        response = self.client.get(
            self.url,
            {
                "child_department_id": department.id,
                "date_from": "2026-03-26",
                "date_to": "2026-03-27",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["summary"]["staffFlagged"], 3)
        for item in response.data["usersByPin"].values():
            self.assertEqual(item["highestSeverity"], "critical")
            self.assertEqual(
                list(item["datesByDate"].keys()),
                ["2026-03-26", "2026-03-27"],
            )
            for day_item in item["datesByDate"].values():
                self.assertEqual(day_item["severity"], "critical")
                self.assertEqual(day_item["groupDays"], 2)
                self.assertEqual(
                    day_item["reason"],
                    ["shared_point", "multi_day_pattern"],
                )

    def test_person_repeat_requires_include_medium(self):
        department = self._create_department("D-PERSON-REPEAT")
        ClassLocation.objects.create(
            name="Far Campus",
            address="Far Address",
            latitude=43.2000,
            longitude=76.8000,
            acceptance_radius_m=120,
        )
        staff = self._create_staff("3001", department)
        for index in range(7):
            target_date = datetime(2026, 3, 20 + index).date()
            self._create_lesson(
                staff,
                target_date,
                latitude=43.2700000 + index * 0.0000010,
                longitude=76.9500000 + index * 0.0000010,
                hour=8,
            )

        response_default = self.client.get(
            self.url,
            {
                "child_department_id": department.id,
                "date_from": "2026-03-20",
                "date_to": "2026-03-26",
            },
        )
        self.assertEqual(response_default.status_code, status.HTTP_200_OK)
        self.assertEqual(response_default.data["summary"]["staffFlagged"], 0)
        self.assertEqual(response_default.data["usersByPin"], {})

        response_medium = self.client.get(
            self.url,
            {
                "child_department_id": department.id,
                "date_from": "2026-03-20",
                "date_to": "2026-03-26",
                "include_medium": "1",
            },
        )
        self.assertEqual(response_medium.status_code, status.HTTP_200_OK)
        self.assertEqual(response_medium.data["summary"]["staffFlagged"], 1)
        result = response_medium.data["usersByPin"]["3001"]
        self.assertEqual(result["highestSeverity"], "medium")
        self.assertEqual(result["activeDays"], 7)
        self.assertEqual(result["repeatDays"], 7)
        self.assertEqual(result["repeatPct"], 100.0)
        self.assertEqual(
            result["datesByDate"],
            {
                "2026-03-20": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
                "2026-03-21": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
                "2026-03-22": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
                "2026-03-23": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
                "2026-03-24": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
                "2026-03-25": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
                "2026-03-26": {
                    "severity": "medium",
                    "groupDays": 0,
                    "lat": 43.270003,
                    "lon": 76.950003,
                    "locationName": "Far Campus",
                    "reason": ["person_repeat", "multi_day_pattern"],
                },
            },
        )

    def test_lesson_attendance_save_busts_epoch_cached_response(self):
        department = self._create_department("D-EPOCH-LESSON")
        ClassLocation.objects.create(
            name="Far Campus",
            address="Far Address",
            latitude=43.2000,
            longitude=76.8000,
            acceptance_radius_m=120,
        )
        staff = self._create_staff("4001", department)
        for index in range(6):
            target_date = datetime(2026, 3, 20 + index).date()
            self._create_lesson(
                staff,
                target_date,
                latitude=43.2800000 + index * 0.0000010,
                longitude=76.9600000 + index * 0.0000010,
                hour=8,
            )

        params = {
            "child_department_id": department.id,
            "date_from": "2026-03-20",
            "date_to": "2026-03-26",
            "include_medium": "1",
        }
        initial_response = self.client.get(self.url, params)
        self.assertEqual(initial_response.status_code, status.HTTP_200_OK)
        self.assertEqual(initial_response.data["usersByPin"], {})

        self._create_lesson(
            staff,
            datetime(2026, 3, 26).date(),
            latitude=43.2800060,
            longitude=76.9600060,
            hour=10,
        )

        refreshed_response = self.client.get(self.url, params)
        self.assertEqual(refreshed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed_response.data["summary"]["staffFlagged"], 1)

    def test_class_location_change_busts_epoch_cached_response(self):
        department = self._create_department("D-EPOCH-LOCATION")
        ClassLocation.objects.create(
            name="Far Campus",
            address="Far Address",
            latitude=43.2000,
            longitude=76.8000,
            acceptance_radius_m=120,
        )
        staff = self._create_staff("5001", department)
        suspicious_lat = 43.2900000
        suspicious_lon = 76.9700000
        for index in range(7):
            target_date = datetime(2026, 3, 20 + index).date()
            self._create_lesson(
                staff,
                target_date,
                latitude=suspicious_lat + index * 0.0000010,
                longitude=suspicious_lon + index * 0.0000010,
                hour=8,
            )

        params = {
            "child_department_id": department.id,
            "date_from": "2026-03-20",
            "date_to": "2026-03-26",
            "include_medium": "1",
        }
        initial_response = self.client.get(self.url, params)
        self.assertEqual(initial_response.status_code, status.HTTP_200_OK)
        self.assertEqual(initial_response.data["summary"]["staffFlagged"], 1)

        ClassLocation.objects.create(
            name="Now Known",
            address="Now Known Address",
            latitude=suspicious_lat,
            longitude=suspicious_lon,
            acceptance_radius_m=200,
        )

        refreshed_response = self.client.get(self.url, params)
        self.assertEqual(refreshed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed_response.data["summary"]["staffFlagged"], 1)
        refreshed_result = refreshed_response.data["usersByPin"]["5001"]
        self.assertEqual(
            refreshed_result["datesByDate"]["2026-03-20"]["locationName"],
            "Now Known",
        )
        self.assertEqual(
            refreshed_result["datesByDate"]["2026-03-20"]["reason"],
            ["person_repeat", "multi_day_pattern"],
        )


@override_settings(
    ATTENDANCE_EXIT_DEVICE_SNS=frozenset({"QJT3244400440", "CORL223060005"}),
    ATTENDANCE_AMBIGUOUS_EXIT_DEVICE_SNS=frozenset({"QJT3244400440"}),
    ATTENDANCE_REENTRY_DEVICE_SNS=frozenset(
        {"COVS222560013", "CN3R230260010", "CN3R230260002", "CN3R230260003"}
    ),
    ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES=45,
)
class AttendanceFetcherExitResolutionTest(TestCase):
    def _event(self, hh: int, mm: int, dev_sn: str, area: str) -> Dict[str, str]:
        return {
            "eventTime": f"2026-03-01T{hh:02d}:{mm:02d}:00",
            "devSn": dev_sn,
            "areaName": area,
        }

    def _find_item(
        self,
        sequence: Optional[list[Dict[str, str]]],
        dev_sn: str,
        resolution: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        for item in sequence or []:
            if item.get("devSn") != dev_sn:
                continue
            if resolution is None or item.get("exit_resolution") == resolution:
                return item
        return None

    def test_qjt_with_reentry_in_10_minutes_is_bridge_transfer(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
            self._event(12, 10, "COVS222560013", "Мост из пристройки"),
        ]
        _, _, _, area_sequence, _, _, _, stats = _compute_attendance_from_events(events)

        qjt_item = self._find_item(area_sequence, "QJT3244400440", "bridge_transfer")
        self.assertIsNotNone(qjt_item)
        if qjt_item is None:
            self.fail("Expected QJT event resolved as bridge_transfer")
        self.assertEqual(qjt_item.get("exit_candidate"), "1")
        self.assertNotIn("is_exit", qjt_item)
        self.assertEqual(stats["ambiguous_exit_candidates"], 1)
        self.assertEqual(stats["ambiguous_resolved_as_transfer"], 1)
        self.assertEqual(stats["ambiguous_resolved_as_exit"], 0)

    def test_qjt_without_reentry_in_45_minutes_is_exit(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
        ]
        _, _, effective, area_sequence, intervals, _, _, stats = (
            _compute_attendance_from_events(events)
        )
        qjt_item = self._find_item(area_sequence, "QJT3244400440", "exit")

        self.assertIsNotNone(qjt_item)
        if qjt_item is None:
            self.fail("Expected QJT event resolved as exit")
        self.assertEqual(qjt_item.get("is_exit"), "1")
        self.assertEqual(effective, 3 * 3600)
        self.assertEqual(len(intervals or []), 1)
        self.assertEqual(stats["ambiguous_resolved_as_exit"], 1)

    def test_qjt_with_reentry_after_50_minutes_is_exit(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
            self._event(12, 50, "COVS222560013", "Мост из пристройки"),
        ]
        _, _, _, area_sequence, _, _, _, stats = _compute_attendance_from_events(events)
        qjt_item = self._find_item(area_sequence, "QJT3244400440", "exit")

        self.assertIsNotNone(qjt_item)
        if qjt_item is None:
            self.fail("Expected QJT event resolved as exit")
        self.assertEqual(qjt_item.get("is_exit"), "1")
        self.assertEqual(stats["ambiguous_resolved_as_exit"], 1)
        self.assertEqual(stats["ambiguous_resolved_as_transfer"], 0)

    def test_regular_exit_device_still_works_as_exit(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(18, 0, "CORL223060005", "Выход турникет"),
        ]
        _, _, _, area_sequence, _, _, _, _ = _compute_attendance_from_events(events)
        regular_exit_item = self._find_item(area_sequence, "CORL223060005", "exit")

        self.assertIsNotNone(regular_exit_item)
        if regular_exit_item is None:
            self.fail("Expected regular exit device to be marked as exit")
        self.assertEqual(regular_exit_item.get("is_exit"), "1")
        self.assertEqual(regular_exit_item.get("exit_candidate"), "1")

    def test_first_event_on_exit_device_is_not_exit(self):
        events = [self._event(9, 0, "QJT3244400440", "Переход в пристройку")]
        _, _, _, area_sequence, _, _, _, stats = _compute_attendance_from_events(events)
        first_item = next(iter(area_sequence or []), None)
        if first_item is None:
            self.fail("Expected non-empty area_sequence")
        self.assertNotIn("is_exit", first_item)
        self.assertNotIn("exit_candidate", first_item)
        self.assertEqual(stats["ambiguous_exit_candidates"], 0)

    def test_mixed_intervals_total_seconds_is_merged_correctly(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
            self._event(12, 10, "COVS222560013", "Мост из пристройки"),
            self._event(13, 0, "CORL223060005", "Выход турникет"),
            self._event(14, 0, "CN3R230260003", "Главный вход"),
            self._event(18, 0, "QJT3244400440", "Переход в пристройку"),
        ]
        _, _, effective, _, intervals, _, _, _ = _compute_attendance_from_events(events)
        self.assertEqual(effective, 8 * 3600)
        self.assertEqual(len(intervals or []), 2)


_FIXTURE_PHOTO = Path(__file__).resolve().parent / "fixtures" / "test_photo.jpg"
_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c \x24.' \",#\x1c\x1c(7),0144\x1f';=82<.32"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
    b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?"
    b"\x00{\x1f+\x0f\xf0\xff\xd9"
)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_STORE_EAGER_RESULT=True,
    DEBUG=True,
    MEDIA_ROOT=tempfile.gettempdir(),
)
class LessonAttendanceCreateThenPutPhotoTest(APITestCase):
    """
    Интеграционный сценарий "POST создать -> GET task_status -> PUT добавить фото".
    Для теста берём существующие данные БД:
    - первый активный staff-пользователь;
    - первый активный APIKey;
    - Staff с pin=T861T и его фото.
    Запуск одного теста: ...LessonAttendanceCreateThenPutPhotoTest.test_create_then_put_photo_base64
    или ...LessonAttendanceCreateThenPutPhotoTest.test_create_then_put_photo_file
    """

    LAT = 43.26498756460276
    LON = 76.93992733955383

    def setUp(self):
        self.user = (
            User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
        )
        if self.user is None:
            self.user = User.objects.create_user(
                username="lesson-photo-admin",
                password="test-pass-123",
            )
            self.user.is_staff = True
            self.user.is_active = True
            self.user.save(update_fields=["is_staff", "is_active"])
        self.api_key = (
            APIKey.objects.filter(is_active=True, created_by=self.user)
            .order_by("id")
            .first()
            or APIKey.objects.filter(is_active=True).order_by("id").first()
        )
        if self.api_key is None:
            self.api_key = APIKey.objects.create(
                key_name="Lesson Photo Test Key",
                created_by=self.user,
            )
        self.staff = Staff.objects.filter(pin__iexact="T861T").first()
        if self.staff is None:
            self.staff = Staff.objects.create(
                pin="T861T",
                name="Matrix",
                surname="Student",
            )
        if self.staff and self.staff.avatar:
            with self.staff.avatar.open("rb") as f:
                self._photo_bytes = f.read()
        elif _FIXTURE_PHOTO.exists():
            self._photo_bytes = _FIXTURE_PHOTO.read_bytes()
        else:
            self._photo_bytes = _MINIMAL_JPEG
        self.assertTrue(self._photo_bytes, "Не удалось прочитать фото для теста")
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)

    def _post_attendance_get_lesson_id(self):
        first_in = timezone.now().isoformat()
        payload = {
            "attendance_data": [
                {
                    "staff_pin": self.staff.pin,
                    "subject_name": "Matrix 101: Красная таблетка",
                    "tutor_id": 101,
                    "tutor": "Морфеус",
                    "first_in": first_in,
                    "latitude": self.LAT,
                    "longitude": self.LON,
                }
            ]
        }
        response = self.client.post(
            reverse("create_lesson_attendance_json"),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        task_id = response.data["task_id"]
        task_status_url = reverse(
            "check_lesson_task_status", kwargs={"task_id": task_id}
        )
        for _ in range(10):
            response = self.client.get(task_status_url)
            if (
                response.status_code == status.HTTP_200_OK
                and response.data.get("status") == "Success"
            ):
                break
            if response.status_code == status.HTTP_202_ACCEPTED:
                time.sleep(0.2)
                continue
            self.fail(
                f"Неожиданный ответ check_lesson_task_status: "
                f"{response.status_code} {response.data}"
            )
        else:
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                lesson = (
                    LessonAttendance.objects.filter(
                        staff=self.staff,
                        subject_name="Matrix 101: Красная таблетка",
                    )
                    .order_by("-id")
                    .first()
                )
                self.assertIsNotNone(lesson)
                return lesson.id
            self.fail(f"task_id={task_id} не перешёл в Success за отведённое время")

        lesson_ids = response.data.get("lesson_ids") or []
        self.assertGreaterEqual(len(lesson_ids), 1, response.data)
        self.assertIn("id", lesson_ids[0], response.data)
        return lesson_ids[0]["id"]

    def test_create_then_put_photo_base64(self):
        lesson_id = self._post_attendance_get_lesson_id()
        image_b64 = base64.b64encode(self._photo_bytes).decode("ascii")
        payload: Any = {"image": image_b64}
        response = self.client.put(
            reverse("update_lesson_attendance", kwargs={"id": lesson_id}),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data.get("lesson_id"), lesson_id)
        record = LessonAttendance.objects.get(id=lesson_id)
        self.assertTrue(bool(record.staff_image_path))

    def test_create_then_put_photo_file(self):
        lesson_id = self._post_attendance_get_lesson_id()
        photo_file = SimpleUploadedFile(
            "photo.jpg",
            self._photo_bytes,
            content_type="image/jpeg",
        )
        payload_multipart: Any = {"image": photo_file}
        response = self.client.put(
            reverse("update_lesson_attendance", kwargs={"id": lesson_id}),
            payload_multipart,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data.get("lesson_id"), lesson_id)
        record = LessonAttendance.objects.get(id=lesson_id)
        self.assertTrue(bool(record.staff_image_path))


class TestablePhotoConsumer(PhotoConsumer):
    async def send_batched_events_for_test(self, *, message_type, events):
        await self._send_batched_events(message_type=message_type, events=events)

    def set_update_buffer_for_test(self, buffer_payload):
        self._photo_update_buffer = buffer_payload

    def get_update_buffer_keys_for_test(self):
        return sorted(getattr(self, "_photo_update_buffer", {}).keys())

    def queue_photo_event_for_test(self, event):
        self._queue_photo_event(event)

    def set_risk_only_for_test(self, enabled: bool):
        self._risk_only = enabled

    async def flush_photo_updates_for_test(self):
        await self._flush_photo_updates()

    async def send_initial_snapshot_for_test(self):
        await self._send_initial_snapshot()


class PhotoConsumerProtocolTest(SimpleTestCase):
    def test_batched_events_are_chunked_and_versioned(self):
        consumer = TestablePhotoConsumer()
        consumer.send_json = AsyncMock()
        events = [
            {
                "id": idx + 1,
                "hasPhoto": False,
                "staffPin": f"T{idx + 1:04d}",
                "staffFullName": f"User {idx + 1}",
                "department": "Dept",
                "photoUrl": "",
                "attendanceTime": timezone.now().isoformat(),
                "tutorInfo": "Morpheus (TutorID: 101)",
                "op": "updated",
                "stateCode": "UPDATED_META",
                "versionTs": timezone.now().isoformat(),
            }
            for idx in range(401)
        ]

        async_to_sync(consumer.send_batched_events_for_test)(
            message_type="photos_updated",
            events=events,
        )

        self.assertEqual(consumer.send_json.await_count, 3)
        payloads = [call.args[0] for call in consumer.send_json.await_args_list]
        batch_ids = {payload["batchId"] for payload in payloads}
        self.assertEqual(len(batch_ids), 1)
        self.assertEqual([payload["chunkIndex"] for payload in payloads], [1, 2, 3])
        self.assertTrue(all(payload["totalChunks"] == 3 for payload in payloads))
        self.assertTrue(
            all(payload["protocol"] == PHOTO_WS_PROTOCOL for payload in payloads)
        )

    def test_deleted_event_is_sent_without_photo_payload(self):
        consumer = TestablePhotoConsumer()
        consumer.send_json = AsyncMock()
        consumer.get_photo_data_bulk = AsyncMock(return_value=[])
        consumer.set_update_buffer_for_test(
            {
                42: {
                    "id": 42,
                    "op": "deleted",
                    "stateCode": STATE_DELETED,
                    "versionTs": timezone.now().isoformat(),
                }
            }
        )

        async_to_sync(consumer.flush_photo_updates_for_test)()

        self.assertEqual(consumer.send_json.await_count, 1)
        payload = consumer.send_json.await_args_list[0].args[0]
        self.assertEqual(payload["type"], "photos_updated")
        self.assertEqual(payload["events"][0]["id"], 42)
        self.assertEqual(payload["events"][0]["stateCode"], STATE_DELETED)
        self.assertEqual(payload["events"][0]["op"], "deleted")
        self.assertEqual(payload["photos"], [])

    def test_queue_photo_event_supports_attendance_ids_bulk(self):
        consumer = TestablePhotoConsumer()
        event = {
            "attendance_ids": [11, "12", 12, "bad", 13],
            "op": "updated",
            "stateCode": "UPDATED_META",
            "versionTs": timezone.now().isoformat(),
        }

        async def _run():
            consumer.queue_photo_event_for_test(event)
            await asyncio.sleep(0)

        async_to_sync(_run)()

        self.assertEqual(consumer.get_update_buffer_keys_for_test(), [11, 12, 13])

    def test_risk_only_snapshot_keeps_manual_suspicious_not_actionable(self):
        consumer = TestablePhotoConsumer()
        consumer.set_risk_only_for_test(True)
        consumer.send_json = AsyncMock()
        consumer.get_photos_for_date = AsyncMock(
            return_value=[
                {
                    "id": 101,
                    "hasPhoto": True,
                    "staffPin": "S0101S",
                    "staffFullName": "Risk Manual",
                    "department": "Dept",
                    "photoUrl": "/media/a.jpg",
                    "attendanceTime": timezone.now().isoformat(),
                    "tutorInfo": "",
                    "photoSpoofStatus": "suspicious",
                    "photoManualVerdict": "suspicious",
                    "photoCanSetManualVerdict": False,
                },
                {
                    "id": 102,
                    "hasPhoto": True,
                    "staffPin": "S0102S",
                    "staffFullName": "Clean",
                    "department": "Dept",
                    "photoUrl": "/media/b.jpg",
                    "attendanceTime": timezone.now().isoformat(),
                    "tutorInfo": "",
                    "photoSpoofStatus": "clean",
                    "photoManualVerdict": "none",
                    "photoCanSetManualVerdict": False,
                },
            ]
        )

        async_to_sync(consumer.send_initial_snapshot_for_test)()

        self.assertEqual(consumer.send_json.await_count, 1)
        payload = consumer.send_json.await_args_list[0].args[0]
        events = payload["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], 101)

    def test_risk_only_updates_keep_manual_suspicious_not_actionable(self):
        consumer = TestablePhotoConsumer()
        consumer.set_risk_only_for_test(True)
        consumer.send_json = AsyncMock()
        consumer.get_photo_data_bulk = AsyncMock(
            return_value=[
                {
                    "id": 201,
                    "hasPhoto": True,
                    "staffPin": "S0201S",
                    "staffFullName": "Risk Manual",
                    "department": "Dept",
                    "photoUrl": "/media/c.jpg",
                    "attendanceTime": timezone.now().isoformat(),
                    "tutorInfo": "",
                    "photoSpoofStatus": "suspicious",
                    "photoManualVerdict": "suspicious",
                    "photoCanSetManualVerdict": False,
                }
            ]
        )
        consumer.set_update_buffer_for_test(
            {
                201: {
                    "id": 201,
                    "op": "updated",
                    "stateCode": STATE_UPDATED_META,
                    "versionTs": timezone.now().isoformat(),
                }
            }
        )

        async_to_sync(consumer.flush_photo_updates_for_test)()

        self.assertEqual(consumer.send_json.await_count, 1)
        payload = consumer.send_json.await_args_list[0].args[0]
        self.assertEqual(payload["type"], "photos_updated")
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["id"], 201)


class LessonAttendancePhotoPadHourlyTaskTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(
            pin="S4400S",
            name="Hourly",
            surname="Pad",
            department=None,
        )
        self.now = timezone.now()

    def _create_lesson(
        self,
        *,
        image_path: str,
        auto_status: str = LessonAttendance.PHOTO_SPOOF_STATUS_PENDING,
        manual_verdict: str = LessonAttendance.PHOTO_MANUAL_VERDICT_NONE,
    ) -> LessonAttendance:
        return LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="PAD",
            tutor_id=1,
            tutor="Tutor",
            first_in=self.now,
            latitude=43.238949,
            longitude=76.889709,
            date_at=timezone.localdate(),
            staff_image_path=image_path,
            photo_spoof_status=auto_status,
            photo_manual_verdict=manual_verdict,
        )

    @staticmethod
    def _mock_pad_result(
        *,
        status_value: str,
        trust_confirmed: bool | None,
        risk_score: float,
        tags: list[str],
    ) -> Mock:
        result = Mock()
        result.status = status_value
        result.elapsed_ms = 12.5
        result.to_update_kwargs.return_value = {
            "photo_trust_confirmed": trust_confirmed,
            "photo_spoof_status": status_value,
            "photo_spoof_score": risk_score,
            "photo_spoof_tags": tags,
            "photo_spoof_checked_at": timezone.now(),
            "photo_spoof_model_version": "pad_v3",
        }
        return result

    @patch("monitoring_app.tasks.get_channel_layer")
    @patch("monitoring_app.photo_pad.check_photo")
    def test_hourly_scan_invalidates_cache_and_broadcasts_clean_update(
        self,
        mock_check_photo,
        mock_get_channel_layer,
    ):
        lesson = self._create_lesson(image_path="/tmp/hourly-pad-clean.jpg")
        cache_key = f"photos_for_{lesson.date_at}"
        cache.set(cache_key, {"cached": True}, timeout=60)

        mock_check_photo.return_value = self._mock_pad_result(
            status_value=LessonAttendance.PHOTO_SPOOF_STATUS_CLEAN,
            trust_confirmed=True,
            risk_score=0.04,
            tags=["face_ok"],
        )
        channel_layer = Mock()
        channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = channel_layer

        result = monitoring_tasks.scan_lesson_attendance_photos_hourly(
            batch_size=10,
            max_records=10,
            only_today=True,
        )

        lesson.refresh_from_db()

        self.assertEqual(
            lesson.photo_spoof_status,
            LessonAttendance.PHOTO_SPOOF_STATUS_CLEAN,
        )
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["clean"], 1)
        self.assertIsNone(cache.get(cache_key))
        channel_layer.group_send.assert_awaited_once()

        group_name, payload = channel_layer.group_send.await_args.args
        self.assertEqual(group_name, f"photos_{lesson.date_at.isoformat()}")
        self.assertEqual(payload["type"], "new_photo")
        self.assertEqual(payload["op"], "updated")
        self.assertEqual(payload["stateCode"], "UPDATED_META")
        self.assertEqual(payload["attendance_ids"], [lesson.id])
        self.assertEqual(payload["attendance_id"], lesson.id)

    @patch("monitoring_app.tasks.get_channel_layer")
    @patch("monitoring_app.photo_pad.check_photo")
    def test_hourly_scan_skips_manual_verdict_without_live_updates(
        self,
        mock_check_photo,
        mock_get_channel_layer,
    ):
        lesson = self._create_lesson(
            image_path="/tmp/hourly-pad-manual.jpg",
            manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_SUSPICIOUS,
        )
        cache_key = f"photos_for_{lesson.date_at}"
        cache.set(cache_key, "keep-me", timeout=60)

        result = monitoring_tasks.scan_lesson_attendance_photos_hourly(
            batch_size=10,
            max_records=10,
            only_today=True,
        )

        self.assertEqual(result["checked"], 0)
        mock_check_photo.assert_not_called()
        mock_get_channel_layer.assert_not_called()
        self.assertEqual(cache.get(cache_key), "keep-me")


class LessonAttendanceSignalStateTest(SimpleTestCase):
    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_new_photo_created_without_image_emits_created_no_photo(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        created_lesson = DummyLesson(lesson_id=1001, staff_image_path=None)
        lesson_signals.send_new_photo(
            sender=LessonAttendance,
            instance=created_lesson,
            created=True,
            update_fields=None,
        )
        mock_send_photo_event.assert_called_once_with(
            created_lesson,
            op="created",
            state_code=STATE_CREATED_NO_PHOTO,
        )

    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_new_photo_with_image_update_emits_photo_attached(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        updated_lesson = DummyLesson(lesson_id=1002, staff_image_path="/tmp/ws1002.jpg")
        lesson_signals.send_new_photo(
            sender=LessonAttendance,
            instance=updated_lesson,
            created=False,
            update_fields={"staff_image_path"},
        )
        mock_send_photo_event.assert_called_once_with(
            updated_lesson,
            op="updated",
            state_code=STATE_PHOTO_ATTACHED,
        )

    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_deleted_photo_emits_deleted_state(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        deleted_lesson = DummyLesson(lesson_id=1003, staff_image_path="/tmp/ws1003.jpg")
        lesson_signals.send_deleted_photo(
            sender=LessonAttendance,
            instance=deleted_lesson,
        )
        mock_send_photo_event.assert_called_once_with(
            deleted_lesson,
            op="deleted",
            state_code=STATE_DELETED,
        )

    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_new_photo_meta_update_without_image_emits_updated_meta(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        updated_lesson = DummyLesson(lesson_id=1004, staff_image_path=None)
        lesson_signals.send_new_photo(
            sender=LessonAttendance,
            instance=updated_lesson,
            created=False,
            update_fields={"first_in"},
        )
        mock_send_photo_event.assert_called_once_with(
            updated_lesson,
            op="updated",
            state_code="UPDATED_META",
        )


class DepartmentConfirmationCacheRotationTaskTest(SimpleTestCase):
    @patch("monitoring_app.cache_conf.invalidate_cache_pattern", return_value=17)
    @patch("monitoring_app.cache_conf.Cache.set")
    def test_rotate_department_confirmation_cache_epoch_sets_epoch_and_invalidates(
        self,
        mock_cache_set,
        mock_invalidate_pattern,
    ):
        result = monitoring_tasks.rotate_department_confirmation_cache_epoch()

        self.assertIn("epoch", result)
        self.assertRegex(result["epoch"], r"^\d{10}$")
        self.assertEqual(result["deleted_keys"], 17)
        mock_cache_set.assert_called_once_with(
            monitoring_tasks.DEPARTMENT_CONFIRMATION_EPOCH_CACHE_KEY,
            result["epoch"],
            monitoring_tasks.DEPARTMENT_CONFIRMATION_EPOCH_TTL,
        )
        mock_invalidate_pattern.assert_called_once_with("department_confirmation_*")


class LessonAttendanceMediaAccessTest(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.attendance_root = Path(self.temp_dir.name)
        self.override = override_settings(
            ATTENDANCE_ROOT=self.attendance_root,
            ATTENDANCE_URL="/attendance_media/",
            MEDIA_ROOT=self.attendance_root / "media",
            MEDIA_URL="/media/",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.staff = Staff(pin="T3587T", name="John", surname="Doe")

    def _build_record(self, image_path: str | None) -> LessonAttendance:
        now_dt = timezone.now()
        return LessonAttendance(
            staff=self.staff,
            subject_name="Math",
            tutor_id=1,
            tutor="Tutor",
            first_in=now_dt,
            last_out=now_dt + timedelta(hours=1),
            latitude=43.2389,
            longitude=76.8897,
            date_at=now_dt.date(),
            staff_image_path=image_path,
        )

    def test_image_url_uses_attendance_media_path_for_attendance_root_files(self):
        file_path = self.attendance_root / "t3587t/2026-04-01/sample.jpg"
        record = self._build_record(str(file_path))

        self.assertEqual(
            record.image_url,
            "/attendance_media/t3587t/2026-04-01/sample.jpg",
        )

    def test_attendance_media_endpoint_serves_existing_photo(self):
        file_path = self.attendance_root / "t3587t/2026-04-01/sample.jpg"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        expected_content = b"\xff\xd8\xff\xd9"
        file_path.write_bytes(expected_content)

        response = self.client.get(
            reverse(
                "attendance-media",
                kwargs={"path": "t3587t/2026-04-01/sample.jpg"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.get("Content-Type"), "image/jpeg")
        self.assertEqual(response.get("Cache-Control"), "private, max-age=300")
        self.assertEqual(b"".join(response.streaming_content), expected_content)

    def test_attendance_media_endpoint_returns_404_for_missing_photo(self):
        response = self.client.get(
            reverse(
                "attendance-media",
                kwargs={"path": "t3587t/2026-04-01/missing.jpg"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
