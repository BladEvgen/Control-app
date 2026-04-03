import contextlib
import io
import logging
import os
import sys
import warnings
from typing import Dict, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from monitoring_app import augment, models


@contextlib.contextmanager
def _suppress_stdout():
    """InsightFace/onnxruntime печатают в stdout; логи Django идут в stderr/handlers."""
    buf = io.StringIO()
    prev = sys.stdout
    sys.stdout = buf
    try:
        yield
    finally:
        sys.stdout = prev


def _quiet_third_party_logs(verbose: bool) -> None:
    if verbose:
        return
    os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")
    for name in (
        "insightface",
        "onnxruntime",
        "onnxruntime.capi",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        module="insightface.utils.transform",
    )


class Command(BaseCommand):
    help = (
        "Augment face crops into AUGMENT_ROOT (…/user_images/{pin}/augmented_images/). "
        "По умолчанию только сотрудники с needs_training=True и непустым avatar. "
        "Режимы: --all | --department-id | --staff-pin."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--department-id",
            type=int,
            dest="department_id",
            help="Only staff in this ChildDepartment (and its subtree, same as API).",
        )
        group.add_argument(
            "--all",
            action="store_true",
            help="All staff matching needs_training and avatar (same as default queryset).",
        )
        group.add_argument(
            "--staff-pin",
            type=str,
            dest="staff_pin",
            help="Один сотрудник по PIN (регистр не важен). Нужен avatar.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="С --staff-pin: аугментировать даже при needs_training=False (для проверки).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many staff would be processed and exit.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Полный вывод (InsightFace/onnx, предупреждения).",
        )

    def _write_augment_report(
        self, qs, pin_notes: Optional[Dict[str, str]] = None
    ) -> None:
        pin_notes = pin_notes or {}
        self.stdout.write("")
        self.stdout.write("Каталоги аугментации (после прогона):")
        for staff in qs:
            root = str(settings.AUGMENT_ROOT).format(staff_pin=staff.pin)
            n_files = 0
            if os.path.isdir(root):
                n_files = sum(
                    1
                    for name in os.listdir(root)
                    if not name.startswith(".")
                    and os.path.isfile(os.path.join(root, name))
                )
            line = f"  PIN {staff.pin}: {n_files} файлов → {root}"
            if n_files == 0:
                self.stdout.write(self.style.WARNING(line))
                reason = pin_notes.get(staff.pin)
                if reason:
                    self.stdout.write(
                        self.style.WARNING(f"    причина: {reason}")
                    )
            else:
                self.stdout.write(line)

    def handle(self, *args, **options):
        department_id = options.get("department_id")
        staff_pin_arg = (options.get("staff_pin") or "").strip()
        force = options.get("force", False)
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        if force and not staff_pin_arg:
            raise CommandError("--force допустим только вместе с --staff-pin.")

        base_qs = (
            models.Staff.objects.filter(needs_training=True)
            .exclude(avatar__isnull=True)
            .exclude(avatar="")
        )

        if staff_pin_arg:
            try:
                staff = models.Staff.objects.get(pin__iexact=staff_pin_arg)
            except models.Staff.DoesNotExist as exc:
                raise CommandError(
                    f"Сотрудник с PIN «{staff_pin_arg}» не найден."
                ) from exc
            if not staff.avatar or not staff.avatar.name:
                raise CommandError(f"У сотрудника {staff.pin} нет файла аватара.")
            if not staff.needs_training and not force:
                raise CommandError(
                    f"У {staff.pin} needs_training=False — не попадает в аугментацию. "
                    "Включите «Требуется обучение» в админке или добавьте --force."
                )
            qs = models.Staff.objects.filter(pk=staff.pk)
            scope_label = (
                f"staff pin={staff.pin} (single)"
                + (" [force]" if force and not staff.needs_training else "")
            )
        elif options.get("all"):
            qs = base_qs
            scope_label = "all matching staff"
        else:
            assert department_id is not None
            try:
                child = models.ChildDepartment.objects.get(id=department_id)
            except models.ChildDepartment.DoesNotExist as exc:
                raise CommandError(
                    f"ChildDepartment id={department_id} does not exist."
                ) from exc
            subtree = [child] + child.get_all_child_departments()
            qs = base_qs.filter(department__in=subtree)
            scope_label = f"department id={department_id} ({child.name})"

        count = qs.count()
        self.stdout.write(f"Scope: {scope_label}, staff count: {count}")
        if staff_pin_arg and count == 1:
            s = qs.first()
            assert s is not None
            self.stdout.write(
                f"  (needs_training={s.needs_training}, "
                f"department_id={s.department_id}, avatar={s.avatar.name})"
            )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run — no augmentation started."))
            return

        if count == 0:
            self.stdout.write(self.style.WARNING("No staff to process."))
            return

        _quiet_third_party_logs(verbose)
        if verbose:
            pin_notes = augment.run_staff_avatar_augmentation(staff_queryset=qs)
        else:
            with _suppress_stdout():
                pin_notes = augment.run_staff_avatar_augmentation(staff_queryset=qs)
        self.stdout.write(self.style.SUCCESS("Augmentation finished."))
        self._write_augment_report(qs, pin_notes)
        self.stdout.write(
            self.style.NOTICE(
                "Галочка «Требуется обучение» здесь не меняется: её снимает "
                "generate_encoding_train_model после успешного обучения модели по сотруднику."
            )
        )
