from django.apps import AppConfig
from typing import ClassVar


class MonitoringAppConfig(AppConfig):
    default_auto_field: ClassVar[str] = "django.db.models.BigAutoField"
    name = "monitoring_app"
    verbose_name = "Система мониторинга"

    def ready(self):
        import importlib

        importlib.import_module("monitoring_app.signals")
