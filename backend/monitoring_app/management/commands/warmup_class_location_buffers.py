from django.core.management.base import BaseCommand
from monitoring_app.tasks import warmup_class_location_buffers


class Command(BaseCommand):
    help = (
        "Прогревает кэш ClassLocation: список (API) + приёмные радиусы R_loc (Redis). "
        "Запускать при деплое; Celery Beat — раз в 30 мин."
    )

    def handle(self, *args, **options):
        result = warmup_class_location_buffers()
        self.stdout.write(
            self.style.SUCCESS(
                f"Кэш локаций прогрет: список={result.get('list_count', 0)}, радиусов={result.get('radii_count', 0)}"
            )
        )
