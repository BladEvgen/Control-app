from django.core.management.base import BaseCommand
from monitoring_app.models import ClassLocation


class Command(BaseCommand):
    help = 'Устанавливает acceptance_radius_m для всех локаций'

    def add_arguments(self, parser):
        parser.add_argument(
            '--radius', type=int, required=True, help='Радиус в метрах для установки всем локациям'
        )

    def handle(self, *args, **options):
        radius = options['radius']

        total_count = ClassLocation.objects.count()

        self.stdout.write(f'Обновление {total_count} записей с радиусом {radius}м...')

        updated = ClassLocation.objects.update(acceptance_radius_m=radius)

        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Успешно обновлено {updated} записей. ' f'Радиус установлен: {radius}м'
            )
        )
