from django.core.management.base import BaseCommand

from monitoring_app.attendance_fetcher import REPORT_MODES, apply_report_mode


class Command(BaseCommand):
    help = (
        "Переписывает отчётные поля StaffAttendance (first_in/last_out/время) из "
        "report_variants под режим AttendanceSettings.turnstile_only — один UPDATE, без API."
    )

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=REPORT_MODES, help="По умолчанию — из настроек.")

    def handle(self, *args, **options):
        updated = apply_report_mode(mode=options.get("mode"))
        self.stdout.write(self.style.SUCCESS(f"Обновлено записей: {updated}"))
