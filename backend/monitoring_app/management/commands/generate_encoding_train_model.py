import logging
import traceback
import warnings

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from monitoring_app import models
from monitoring_app.augment import run_staff_avatar_augmentation
from monitoring_app.ml import create_face_encoding

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create face masks for staff and refresh their augmented gallery images"

    def add_arguments(self, parser):
        parser.add_argument(
            "--department-id",
            type=int,
            default=None,
            help=(
                "Only staff in this ChildDepartment and subtree: создание масок, аугментация и обучение. "
                "Без флага — по всем отделам."
            ),
        )

    def handle(self, *args, **options):
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            message=r".*\brcond\b.*",
        )
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            module=r"insightface\.utils\.transform",
        )

        department_id = options.get("department_id")

        dept_subtree = None
        dept_child = None
        if department_id is not None:
            try:
                dept_child = models.ChildDepartment.objects.get(id=department_id)
            except models.ChildDepartment.DoesNotExist as exc:
                raise CommandError(f"ChildDepartment id={department_id} does not exist.") from exc
            dept_subtree = dept_child.subtree_ids()

        staffs_without_mask = models.Staff.objects.filter(avatar__isnull=False).exclude(
            face_mask__isnull=False
        )
        if dept_subtree is not None:
            staffs_without_mask = staffs_without_mask.filter(department__in=dept_subtree)

        total_created = 0
        success_count = 0
        error_count = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Found {staffs_without_mask.count()} staff without masks"
                + (
                    f" (dept id={department_id}, {dept_child.name})"
                    if dept_child
                    else " (all departments)"
                )
                + "."
            )
        )

        for staff in staffs_without_mask:
            try:
                if not staff.avatar or not staff.avatar.path:
                    logger.warning(f"Staff {staff.pin} has no associated avatar file. Skipping.")
                    continue

                avatar_path = staff.avatar.path
                encoding = create_face_encoding(avatar_path)

                if encoding is None:
                    logger.warning(f"Failed to create encoding for {staff.pin}. Skipping.")
                    continue

                models.StaffFaceMask.objects.create(staff=staff, mask_encoding=encoding)
                total_created += 1
                success_count += 1

            except ObjectDoesNotExist:
                logger.error(f"Avatar not found for staff {staff.pin}\n{traceback.format_exc()}")
                error_count += 1
            except Exception as e:
                logger.error(
                    f"Error creating mask for staff {staff.pin}: {str(e)}\n{traceback.format_exc()}"
                )
                error_count += 1

        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully created {total_created} masks for staff members.")
            )

        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"Errors encountered while processing {error_count} staff members. Check logs for details."
                )
            )

        staff_needing_training = models.Staff.objects.filter(
            needs_training=True, avatar__isnull=False
        )
        if dept_subtree is not None and dept_child is not None:
            staff_needing_training = staff_needing_training.filter(department__in=dept_subtree)
            self.stdout.write(
                self.style.NOTICE(
                    f"Training scope: id={department_id} ({dept_child.name}), "
                    f"staff to train: {staff_needing_training.count()}"
                )
            )

        if staff_needing_training.exists():
            self.stdout.write(self.style.SUCCESS("Starting image augmentation..."))
            try:
                train_pks = list(staff_needing_training.order_by("pk").values_list("pk", flat=True))
                run_staff_avatar_augmentation(
                    staff_queryset=models.Staff.objects.filter(pk__in=train_pks)
                )
                done = models.Staff.objects.filter(pk__in=train_pks).update(needs_training=False)
                self.stdout.write(self.style.SUCCESS(f"Augmentation completed for {done} staff."))
            except Exception as e:
                logger.error(f"Error during augmentation: {str(e)}\n{traceback.format_exc()}")
                self.stdout.write(self.style.ERROR(f"Error during augmentation: {str(e)}"))
        else:
            self.stdout.write(
                self.style.WARNING("No staff members require augmentation. Skipping.")
            )
