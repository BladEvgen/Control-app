from django.core.management.base import BaseCommand
from monitoring_app.models import PerformanceBonusRule

class Command(BaseCommand):
    help = 'Создает или обновляет правила бонуса согласно заданным условиям'

    RULES = [
        {'min_days': 21, 'max_days': 23, 'min_attendance_percent': 87.0, 'max_attendance_percent': 92.0, 'bonus_percentage': 3.5},
        {'min_days': 24, 'max_days': 26, 'min_attendance_percent': 92.1, 'max_attendance_percent': 96.0, 'bonus_percentage': 5.5},
        {'min_days': 27, 'max_days': 29, 'min_attendance_percent': 96.1, 'max_attendance_percent': 100.0, 'bonus_percentage': 8.5},
        {'min_days': 27, 'max_days': 32, 'min_attendance_percent': 100.1, 'max_attendance_percent': 105.0, 'bonus_percentage': 10.5},
        {'min_days': 29, 'max_days': 32, 'min_attendance_percent': 105.1, 'max_attendance_percent': 150.0, 'bonus_percentage': 12.0},
    ]

    def handle(self, *args, **options):
        self.stdout.write("\nНачинается создание/обновление правил бонуса...\n")

        updated_count, created_count = 0, 0
        for rule_data in self.RULES:
            rule, created = PerformanceBonusRule.objects.update_or_create(
                min_days=rule_data['min_days'],
                max_days=rule_data['max_days'],
                min_attendance_percent=rule_data['min_attendance_percent'],
                max_attendance_percent=rule_data['max_attendance_percent'],
                defaults={'bonus_percentage': rule_data['bonus_percentage']}
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Создано правило: {rule}"))
            else:
                updated_count += 1
                self.stdout.write(f"Обновлено правило: {rule}")

        self.stdout.write(self.style.SUCCESS(f"\nГотово! Создано: {created_count}, обновлено: {updated_count}.\n"))