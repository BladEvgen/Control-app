import logging

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from monitoring_app.utils import create_face_encoding
from monitoring_app.models import Staff, StaffFaceMask
from monitoring_app.augment import run_dali_augmentation_for_all_staff  

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Создать маски для всех сотрудников и запустить обучение модели'

    def handle(self, *args, **kwargs):
        staffs = Staff.objects.filter(avatar__isnull=False)
        total_created = 0
        total_updated = 0
        success_count = 0
        error_count = 0

        for staff in staffs:
            try:
                avatar_path = staff.avatar.path
                encoding = create_face_encoding(avatar_path)

                face_mask, created = StaffFaceMask.objects.update_or_create(
                    staff=staff, defaults={"mask_encoding": encoding}
                )

                if created:
                    total_created += 1
                else:
                    total_updated += 1

                success_count += 1

            except ObjectDoesNotExist:
                logger.error(f'Не удалось найти аватар для {staff.pin}')
                error_count += 1

            except Exception as e:
                error_count += 1

        if success_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f'Успешно обработано {success_count} сотрудников: создано {total_created}, обновлено {total_updated}.'
            ))

        if error_count > 0:
            self.stdout.write(self.style.ERROR(
                f'Ошибки при обработке {error_count} сотрудников. Подробности сохранены в логах.'
            ))

        if total_created > 0 or total_updated > 0:
            self.stdout.write(self.style.SUCCESS('Запуск аугментации изображений...'))
            try:
                run_dali_augmentation_for_all_staff()  
                self.stdout.write(self.style.SUCCESS('Аугментация изображений успешно завершена.'))
            except Exception as e:
                logger.error(f'Ошибка при выполнении аугментации: {str(e)}')
                self.stdout.write(self.style.ERROR(f'Ошибка при выполнении аугментации: {str(e)}'))
        else:
            self.stdout.write(self.style.WARNING('Маски не были созданы или обновлены, аугментация не запущена.'))
