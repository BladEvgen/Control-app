from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

app = Celery('django_settings')

app.conf.update(
    broker_url='redis://localhost:6379/0',  
    result_backend='redis://localhost:6379/0',  
)
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
