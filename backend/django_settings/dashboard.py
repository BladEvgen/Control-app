"""Unfold admin: sidebar navigation and the index-page dashboard (settings.UNFOLD)."""

from django.apps import apps
from django.urls import reverse
from django.utils import timezone

ADMIN_MODEL_GROUPS = (
    (
        "Посещаемость и локации",
        (
            ("attendancesettings", "tune"),
            ("staffattendance", "door_front"),
            ("lessonattendance", "photo_camera"),
            ("classlocation", "location_on"),
            ("publicholiday", "event"),
        ),
    ),
    (
        "Персонал и отделы",
        (
            ("staff", "badge"),
            ("position", "work"),
            ("stafffacemask", "face"),
            ("absentreason", "event_busy"),
            ("remotework", "home_work"),
            ("remoteactivityday", "laptop_chromebook"),
            ("parentdepartment", "corporate_fare"),
            ("childdepartment", "account_tree"),
        ),
    ),
    (
        "Авторизация и настройки",
        (
            ("passwordresettoken", "password"),
            ("passwordresetrequestlog", "history"),
            ("apikey", "key"),
            ("userprofile", "manage_accounts"),
            ("filecategory", "folder"),
            ("performancebonusrule", "military_tech"),
        ),
    ),
)


def _changelist(model_name: str) -> str:
    return reverse(f"monitoring_admin:monitoring_app_{model_name}_changelist")


def sidebar_navigation(request):
    """Groups for UNFOLD["SIDEBAR"]["navigation"]; links the user cannot open are hidden."""
    _ = request
    return [
        {
            "title": title,
            "collapsible": True,
            "items": [
                {
                    "title": apps.get_model("monitoring_app", model)._meta.verbose_name_plural,
                    "icon": icon,
                    "link": _changelist(model),
                    "permission": lambda req, m=model: req.user.has_perm(
                        f"monitoring_app.view_{m}"
                    ),
                }
                for model, icon in items
            ],
        }
        for title, items in ADMIN_MODEL_GROUPS
    ]


def dashboard_callback(request, context):
    """KPI cards for templates/admin/index.html. Each figure is one indexed COUNT."""
    from monitoring_app import models
    from monitoring_app.services import attendance_day

    _ = request
    today = timezone.localdate()
    la = models.LessonAttendance.objects.filter(date_at=today)
    context["kpis"] = [
        {
            "title": "Сотрудники",
            "value": models.Staff.objects.count(),
            "icon": "badge",
            "href": _changelist("staff"),
        },
        {
            "title": "Отметки СКУД сегодня",
            "value": models.StaffAttendance.objects.filter(
                date_at=attendance_day.sa_date_at(today)
            ).count(),
            "icon": "door_front",
            "href": _changelist("staffattendance"),
        },
        {
            "title": "Отметки занятий сегодня",
            "value": la.count(),
            "icon": "photo_camera",
            "href": _changelist("lessonattendance"),
        },
        {
            "title": "Фото на проверке",
            "value": la.filter(
                photo_spoof_status=models.LessonAttendance.PHOTO_SPOOF_STATUS_REVIEW,
                photo_manual_verdict=models.LessonAttendance.PHOTO_MANUAL_VERDICT_NONE,
            ).count(),
            "icon": "fact_check",
            "href": _changelist("lessonattendance"),
        },
        {
            "title": "На удалёнке",
            "value": models.RemoteWork.objects.values("staff").distinct().count(),
            "icon": "home_work",
            "href": _changelist("remotework"),
        },
    ]
    return context
