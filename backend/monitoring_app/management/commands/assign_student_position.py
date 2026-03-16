import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from monitoring_app.models import Position, Staff

logger = logging.getLogger("django")

STUDENT_POSITION_NAME = "Студент"


def student_predicate(pin: str, pattern: str) -> bool:
    """pin содержит pattern (например 'S')."""
    return (pattern or "") in (pin or "")


class Command(BaseCommand):
    help = (
        "Назначает должность «Студент» всем Staff, у которых pin совпадает с шаблоном; "
        "у таких сотрудников все прежние должности заменяются на одну — Студент. "
        "Если должности «Студент» нет — создаётся. Пины вроде T861T не трогаем."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pattern",
            type=str,
            default="S",
            help="Строка, по которой определяем студента (по умолчанию: pin содержит 'S').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, кому будет назначена должность, без изменений в БД.",
        )

    def handle(self, *args, **options):
        pattern = (options.get("pattern") or "S").strip()
        dry_run = options.get("dry_run", False)

        with transaction.atomic():  # type: ignore[operator]
            student_position = Position.objects.filter(
                name__icontains="студент"
            ).first()
            if student_position is None:
                student_position = Position.objects.create(name=STUDENT_POSITION_NAME)
                created = True
            else:
                created = False
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Создана должность: {student_position.name} (id={student_position.id})")
                )
            else:
                self.stdout.write(
                    f"Используется должность: {student_position.name} (id={student_position.id})"
                )

            staff_ids = list(
                Staff.objects.filter(pin__icontains=pattern).values_list("id", flat=True)
            )

        if not staff_ids:
            self.stdout.write(
                self.style.WARNING(f"Нет сотрудников с pin, содержащим '{pattern}'.")
            )
            return

        self.stdout.write(
            f"Найдено сотрудников по шаблону '{pattern}': {len(staff_ids)}"
        )
        for s in Staff.objects.filter(id__in=staff_ids).only("pin", "surname", "name")[:20]:
            self.stdout.write(f"  {s.pin} — {s.surname} {s.name}")
        if len(staff_ids) > 20:
            self.stdout.write(f"  ... и ещё {len(staff_ids) - 20}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: изменений в БД не вносилось."))
            return

        through = Staff.positions.through
        with transaction.atomic():  # type: ignore[operator]
            through.objects.filter(staff_id__in=staff_ids).delete()
            through.objects.bulk_create(
                [
                    through(staff_id=sid, position_id=student_position.pk)
                    for sid in staff_ids
                ]
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Должность «{student_position.name}» назначена {len(staff_ids)} сотрудникам (прежние должности сняты)."
            )
        )
