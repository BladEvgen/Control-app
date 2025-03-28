from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

app = Celery('django_settings')

app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=21600,
    task_time_limit=21660,
    worker_max_memory_per_child=2048000,
)

app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'control_app_queue'
app.autodiscover_tasks()
