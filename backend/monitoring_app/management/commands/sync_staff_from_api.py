import logging
from typing import Any, Dict

from django.core.management.base import BaseCommand

from monitoring_app.staff_sync import sync_staff_from_external

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = (
        "Синхронизирует Staff с API СКУД: по pin из БД запрашивает get/{pin}, "
        "удаляет тех, по кого API вернул code=-22 (Сотрудник не существует)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, кого удалят, без изменений в БД.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        self.stdout.write("Загрузка персон из API (get/{pin})...")
        self.stdout.flush()

        try:
            result = self._run_sync(dry_run)
        except KeyboardInterrupt:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Прервано (Ctrl+C)."))
            raise SystemExit(130)

        deleted = result.get("deleted", 0)
        for err in result.get("errors", []):
            self.stdout.write(self.style.ERROR(f"Ошибка: {err}"))
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry-run: удалить {deleted} сотрудников (БД не менялась)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Удалено сотрудников: {deleted}."))
        self.stdout.write("Готово.")

    def _run_sync(self, dry_run: bool) -> Dict[str, Any]:
        return sync_staff_from_external(dry_run=dry_run)
