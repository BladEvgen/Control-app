import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring_app.models import Staff, StaffAttendance


class Command(BaseCommand):
    help = "Generate random attendance times for staff members for debugging"

    def add_arguments(self, parser):
        parser.add_argument(
            "date_at",
            type=str,
            help="Дата для которой генерировать данные в формате ДД.ММ.ГГГГ",
        )

    def handle(self, *args, **kwargs):
        input_date = kwargs["date_at"]
        try:
            date_at = timezone.datetime.strptime(input_date, "%d.%m.%Y").date()
        except ValueError:
            self.stdout.write(
                self.style.ERROR("Неправильный формат даты. Используйте ДД.ММ.ГГГГ")
            )
            return

        previous_day = date_at - timedelta(days=1)
        staff_members = Staff.objects.select_related("department").all()

        attendance_records = []
        for staff in staff_members:
            department_id = staff.department.id if staff.department else None

            if department_id == "04958":
                first_in, last_out = self.generate_time_in_range(9, 18, previous_day)
            else:
                first_in, last_out = self.generate_random_time(previous_day)

            attendance_records.append(
                StaffAttendance(
                    staff=staff, date_at=date_at, first_in=first_in, last_out=last_out
                )
            )

        StaffAttendance.objects.bulk_create(attendance_records)
        self.stdout.write(
            self.style.SUCCESS(
                f"Данные сгенерированы для {date_at.strftime('%d.%m.%Y')}"
            )
        )

    def generate_time_in_range(self, start_hour, end_hour, previous_day):
        first_in_offset = random.randint(-60, 60)
        last_out_offset = random.randint(-60, 60)

        base_first_in = timezone.make_aware(
            timezone.datetime(
                previous_day.year, previous_day.month, previous_day.day, start_hour, 0
            )
        )
        base_last_out = timezone.make_aware(
            timezone.datetime(
                previous_day.year, previous_day.month, previous_day.day, end_hour, 0
            )
        )

        first_in = base_first_in + timedelta(minutes=first_in_offset)
        last_out = base_last_out + timedelta(minutes=last_out_offset)

        if last_out <= first_in:
            last_out = first_in + timedelta(hours=1)

        return first_in, last_out

    def generate_random_time(self, previous_day):
        base_day = timezone.make_aware(
            timezone.datetime(previous_day.year, previous_day.month, previous_day.day)
        )
        first_in_hour = random.randint(9, 16)
        last_out_hour = random.randint(first_in_hour + 1, 18)

        first_in = base_day + timedelta(
            hours=first_in_hour, minutes=random.randint(0, 59)
        )
        last_out = base_day + timedelta(
            hours=last_out_hour, minutes=random.randint(0, 59)
        )

        return first_in, last_out
