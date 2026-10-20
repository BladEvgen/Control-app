"""Пара staff-JWT по PIN без проверки лица — для интеграций и тестов, только с доступом к серверу.

Токены те же, что выдаёт вход по лицу: access 15 мин, одноразовый refresh, потолок сессии.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from monitoring_app.custom_jwt import issue_staff_tokens
from monitoring_app.models import Staff


class Command(BaseCommand):
    help = "Выдаёт пару JWT сотрудника (access/refresh) по staff.pin."

    def add_arguments(self, parser):
        parser.add_argument("--pin", required=True)

    def handle(self, *args, **opts):
        _ = args
        staff_id = (
            Staff.objects.filter(pin__iexact=opts["pin"]).values_list("id", flat=True).first()
        )
        if staff_id is None:
            raise CommandError(f"Активный сотрудник {opts['pin']} не найден")
        self.stdout.write(json.dumps(issue_staff_tokens(staff_id), ensure_ascii=False))
