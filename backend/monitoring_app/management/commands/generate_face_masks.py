import logging
from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from monitoring_app.models import Staff, StaffFaceMask
from monitoring_app.augment import run_dali_augmentation_for_all_staff
from monitoring_app.utils import create_face_encoding, train_face_recognition_model

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Создать маски для сотрудников, у которых они отсутствуют, и запустить обучение модели для нуждающихся"

    def handle(self, *args, **kwargs):
        staffs_without_mask = Staff.objects.filter(avatar__isnull=False).exclude(
            face_mask__isnull=False
        )

        total_created = 0
        success_count = 0
        error_count = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Обнаружено {staffs_without_mask.count()} сотрудников без масок."
            )
        )

        for staff in staffs_without_mask:
            try:
                avatar_path = staff.avatar.path
                encoding = create_face_encoding(avatar_path)

                StaffFaceMask.objects.create(staff=staff, mask_encoding=encoding)
                total_created += 1
                success_count += 1

            except ObjectDoesNotExist:
                logger.error(f"Не удалось найти аватар для {staff.pin}")
                error_count += 1
            except Exception as e:
                logger.error(f"Ошибка при создании маски для {staff.pin}: {str(e)}")
                error_count += 1

        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Успешно создано {total_created} масок для сотрудников."
                )
            )

        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"Ошибки при обработке {error_count} сотрудников. Подробности сохранены в логах."
                )
            )

        staff_needing_training = Staff.objects.filter(
            needs_training=True, avatar__isnull=False
        )

        if staff_needing_training.exists():
            self.stdout.write(
                self.style.SUCCESS("Запуск аугментации изображений и обучения...")
            )
            try:
                run_dali_augmentation_for_all_staff()
                for staff in staff_needing_training:
                    self.stdout.write(
                        f"Тренировка модели для {staff.name} {staff.surname} (PIN: {staff.pin})"
                    )
                    try:
                        train_face_recognition_model(staff)
                        staff.needs_training = False
                        staff.save()
                        logger.info(f"Successfully trained model for {staff.pin}")
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Model trained successfully for {staff.pin}"
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error training model for {staff.pin}: {str(e)}")
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error training model for {staff.pin}: {str(e)}"
                            )
                        )
                self.stdout.write(
                    self.style.SUCCESS("Аугментация изображений и обучение завершены.")
                )
            except Exception as e:
                logger.error(f"Ошибка при выполнении аугментации: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Ошибка при выполнении аугментации: {str(e)}")
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Новых масок не было создано или нет сотрудников, требующих обучения, аугментация и обучение не запущены."
                )
            )
