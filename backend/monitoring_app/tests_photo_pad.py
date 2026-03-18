import datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from monitoring_app.models import LessonAttendance, Staff
from monitoring_app.photo_pad import (
    STATUS_CLEAN,
    STATUS_ERROR,
    STATUS_REVIEW,
    STATUS_SUSPICIOUS,
    DecisionInputs,
    _decide,
)


class PadDecisionTests(SimpleTestCase):
    def test_low_quality_without_device_goes_to_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.92,
                device_score=0.0,
                frame_score=0.05,
                quality_penalty=0.7,
                tags=["fasnet_fake", "quality_poor"],
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)

    def test_device_plus_frame_and_fake_goes_to_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.88,
                device_score=0.62,
                frame_score=0.52,
                quality_penalty=0.1,
                tags=["fasnet_fake", "device_present:cell phone", "screen_frame"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)

    def test_very_high_deepfake_without_screen_signal_goes_to_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.98,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.1,
                tags=["fasnet_fake"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)

    def test_mid_deepfake_with_mid_screen_signal_goes_to_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.84,
                device_score=0.24,
                frame_score=0.26,
                quality_penalty=0.1,
                tags=["fasnet_fake", "device_present:laptop"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)

    def test_tagged_deepfake_with_device_only_goes_to_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.52,
                device_score=0.22,
                frame_score=0.03,
                quality_penalty=0.1,
                tags=["fasnet_fake", "device_present:cell phone"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)

    def test_strong_device_only_signal_goes_to_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.56,
                frame_score=0.0,
                quality_penalty=0.1,
                tags=["device_present:tv"],
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)

    def test_quality_poor_with_screen_signal_stays_in_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.22,
                frame_score=0.26,
                quality_penalty=0.6,
                tags=["quality_poor"],
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)

    def test_clean_signal_goes_to_clean(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[],
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)

    def test_decode_error_goes_to_error(self):
        result = _decide(
            DecisionInputs(
                decode_error=True,
                has_face=False,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["decode_error"],
            )
        )
        self.assertEqual(result.status, STATUS_ERROR)


class LessonAttendancePhotoResetTests(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(
            pin="S998877S",
            name="Pad",
            surname="Tester",
            department=None,
        )
        self.user = get_user_model().objects.create_user(
            username="pad_admin",
            password="test-pass-123",
        )

    def test_photo_change_resets_manual_override(self):
        lesson = LessonAttendance.objects.create(
            staff=self.staff,
            subject_name="PAD",
            tutor_id=1,
            tutor="Tutor",
            first_in=timezone.now(),
            latitude=43.24,
            longitude=76.95,
            date_at=datetime.date.today(),
            staff_image_path="/tmp/pad_old.jpg",
            photo_spoof_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            photo_spoof_score=0.91,
            photo_spoof_tags=["fasnet_fake", "device_present:cell phone"],
            photo_spoof_checked_at=timezone.now(),
            photo_spoof_model_version="pad_v2",
            photo_trust_confirmed=False,
            photo_manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_SUSPICIOUS,
            photo_manual_comment="manual suspicious",
            photo_manual_by=self.user,
            photo_manual_at=timezone.now(),
        )

        lesson.staff_image_path = "/tmp/pad_new.jpg"
        lesson.save(update_fields=["staff_image_path"])
        lesson.refresh_from_db()

        self.assertEqual(
            lesson.photo_spoof_status, LessonAttendance.PHOTO_SPOOF_STATUS_PENDING
        )
        self.assertIsNone(lesson.photo_spoof_score)
        self.assertEqual(lesson.photo_spoof_tags, [])
        self.assertIsNone(lesson.photo_spoof_checked_at)
        self.assertEqual(lesson.photo_spoof_model_version, "")
        self.assertIsNone(lesson.photo_trust_confirmed)
        self.assertEqual(
            lesson.photo_manual_verdict, LessonAttendance.PHOTO_MANUAL_VERDICT_NONE
        )
        self.assertEqual(lesson.photo_manual_comment, "")
        self.assertIsNone(lesson.photo_manual_by)
        self.assertIsNone(lesson.photo_manual_at)
