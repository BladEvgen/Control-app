# generate_face_masks.py
import logging
import traceback
from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from monitoring_app.models import Staff, StaffFaceMask
from monitoring_app.augment import run_dali_augmentation_for_all_staff
from monitoring_app.ml import (
    train_general_model,
    create_face_encoding,
    train_face_recognition_model,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Create masks for staff, augment images, generate embeddings, and train models"
    )

    def handle(self, *args, **kwargs):
        # Step 1: Create masks for staff without them
        staffs_without_mask = Staff.objects.filter(avatar__isnull=False).exclude(
            face_mask__isnull=False
        )

        total_created = 0
        success_count = 0
        error_count = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Found {staffs_without_mask.count()} staff members without masks."
            )
        )

        for staff in staffs_without_mask:
            try:
                if not staff.avatar or not staff.avatar.path:
                    logger.warning(
                        f"Staff {staff.pin} has no associated avatar file. Skipping."
                    )
                    continue

                avatar_path = staff.avatar.path
                encoding = create_face_encoding(avatar_path)

                if encoding is None:
                    logger.warning(
                        f"Failed to create encoding for {staff.pin}. Skipping."
                    )
                    continue

                StaffFaceMask.objects.create(staff=staff, mask_encoding=encoding)
                total_created += 1
                success_count += 1

            except ObjectDoesNotExist:
                logger.error(
                    f"Avatar not found for staff {staff.pin}\n{traceback.format_exc()}"
                )
                error_count += 1
            except Exception as e:
                logger.error(
                    f"Error creating mask for staff {staff.pin}: {str(e)}\n{traceback.format_exc()}"
                )
                error_count += 1

        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully created {total_created} masks for staff members."
                )
            )

        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"Errors encountered while processing {error_count} staff members. Check logs for details."
                )
            )

        # Step 2: Augment images and train models for staff needing training
        staff_needing_training = Staff.objects.filter(
            needs_training=True, avatar__isnull=False
        )

        if staff_needing_training.exists():
            self.stdout.write(
                self.style.SUCCESS("Starting image augmentation and training...")
            )
            try:
                run_dali_augmentation_for_all_staff()
                for staff in staff_needing_training:
                    self.stdout.write(
                        f"Training model for {staff.name} {staff.surname} (PIN: {staff.pin})"
                    )
                    try:
                        # Check if avatar exists before training
                        if not staff.avatar or not staff.avatar.path:
                            logger.warning(
                                f"Staff {staff.pin} has no associated avatar file. Skipping training."
                            )
                            continue

                        # Train individual model
                        train_face_recognition_model(staff)
                        staff.needs_training = False
                        staff.save()
                        logger.info(f"Successfully trained model for {staff.pin}")
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Successfully trained model for {staff.pin}"
                            )
                        )
                    except Exception as e:
                        logger.error(
                            f"Error training model for {staff.pin}: {str(e)}\n{traceback.format_exc()}"
                        )
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error training model for {staff.pin}: {str(e)}"
                            )
                        )
                self.stdout.write(
                    self.style.SUCCESS("Image augmentation and training completed.")
                )

                self.stdout.write(
                    self.style.SUCCESS("Starting training of the general model...")
                )
                try:
                    train_general_model()
                    self.stdout.write(
                        self.style.SUCCESS(
                            "General model successfully trained and saved."
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Error training the general model: {str(e)}\n{traceback.format_exc()}"
                    )
                    self.stdout.write(
                        self.style.ERROR(f"Error training the general model: {str(e)}")
                    )
            except Exception as e:
                logger.error(
                    f"Error during augmentation: {str(e)}\n{traceback.format_exc()}"
                )
                self.stdout.write(
                    self.style.ERROR(f"Error during augmentation: {str(e)}")
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "No staff members require training. Skipping augmentation and training."
                )
            )
