from __future__ import absolute_import, unicode_literals

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_settings.settings")

try:
    from monitoring_app.ml_log_quiet import (
        apply_ml_third_party_log_quiet,
        ml_third_party_stdout_verbose,
    )

    apply_ml_third_party_log_quiet(verbose=ml_third_party_stdout_verbose())
except Exception:
    pass

app = Celery("django_settings")

_redis_host = os.getenv("REDIS_HOST", "localhost")
_redis_port = os.getenv("REDIS_PORT", "6379")
_redis_url = f"redis://{_redis_host}:{_redis_port}/0"

app.conf.update(
    broker_url=_redis_url,
    result_backend=_redis_url,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=21600,
    task_time_limit=21660,
    worker_max_memory_per_child=2048000,
)

app.conf.task_serializer = "json"
app.conf.accept_content = ["json"]
app.conf.result_serializer = "json"
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_default_queue = "control_app_queue"
app.autodiscover_tasks()
