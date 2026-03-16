from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from grappelli.dashboard import modules, Dashboard
from grappelli.dashboard.utils import get_admin_site_name


class CustomIndexDashboard(Dashboard):
    """Дашборд главной страницы админки с моделями и ссылками."""

    def init_with_context(self, context):
        site_name = get_admin_site_name(context)

        self.children.append(
            modules.LinkList(
                _("Быстрые ссылки"),
                column=1,
                collapsible=False,
                children=[
                    [_("На главную"), "/"],
                    [_("Сменить пароль"), reverse("%s:password_change" % site_name)],
                    [_("Выйти"), reverse("%s:logout" % site_name)],
                ],
            )
        )


        self.children.append(
            modules.ModelList(
                _("Посещаемость и локации"),
                column=1,
                collapsible=True,
                models=(
                    "monitoring_app.models.StaffAttendance",
                    "monitoring_app.models.LessonAttendance",
                    "monitoring_app.models.ClassLocation",
                    "monitoring_app.models.PublicHoliday",
                ),
            )
        )

        self.children.append(
            modules.ModelList(
                _("Персонал и отделы"),
                column=1,
                collapsible=True,
                models=(
                    "monitoring_app.models.Staff",
                    "monitoring_app.models.Position",
                    "monitoring_app.models.StaffFaceMask",
                    "monitoring_app.models.Salary",
                    "monitoring_app.models.AbsentReason",
                    "monitoring_app.models.RemoteWork",
                    "monitoring_app.models.ParentDepartment",
                    "monitoring_app.models.ChildDepartment",
                ),
            )
        )

        self.children.append(
            modules.ModelList(
                _("Авторизация и настройки"),
                column=1,
                collapsible=True,
                models=(
                    "monitoring_app.models.PasswordResetToken",
                    "monitoring_app.models.PasswordResetRequestLog",
                    "monitoring_app.models.APIKey",
                    "monitoring_app.models.UserProfile",
                    "monitoring_app.models.FileCategory",
                    "monitoring_app.models.PerformanceBonusRule",
                ),
            )
        )

        self.children.append(
            modules.AppList(
                _("Администрирование"),
                column=1,
                collapsible=True,
                models=("django.contrib.*",),
            )
        )

        self.children.append(
            modules.RecentActions(
                _("Последние действия"),
                limit=10,
                column=2,
                collapsible=False,
            )
        )

        self.children.append(
            modules.LinkList(
                _("Ссылки"),
                column=2,
                collapsible=True,
                children=[
                    {
                        "title": _("Django документация"),
                        "url": "https://docs.djangoproject.com/",
                        "external": True,
                        "target": "_blank",
                    },
                    {
                        "title": _("Grappelli документация"),
                        "url": "https://django-grappelli.readthedocs.io/",
                        "external": True,
                        "target": "_blank",
                    },
                ],
            )
        )
