import os
import shutil
import logging
import datetime

import cv2
import joblib
import numpy as np
from sklearn import svm
import albumentations as A
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from sklearn.preprocessing import StandardScaler

from monitoring_app import models, utils


@shared_task
def get_all_attendance_task():
    """
    Задача Celery для выполнения функции get_all_attendance.
    """
    utils.get_all_attendance()


logger = logging.getLogger(__name__)
LOG_FILE_MAX_SIZE = 100 * 1024 * 1024
LOG_DIR = os.path.join(settings.BASE_DIR, 'logs')
error_log_file = os.path.join(LOG_DIR, 'photo_errors.log')


@shared_task
def update_lesson_attendance_last_out():
    """
    Периодическая задача Celery для обновления поля last_out в LessonAttendance.
    
    Условия выполнения:
    - last_out не установлен (last_out is null).
    - Прошло более 3 часов с момента first_in.
    
    Процесс:
    1. Определяет все записи, которые соответствуют условиям.
    2. Для каждой записи рассчитывает значение last_out:
       - Устанавливает last_out как first_in + 3 часа.
       - Если first_in + 3 часа выходит за пределы текущего дня, устанавливает last_out
         на максимально допустимое время в пределах дня (23:59:59).
    3. Изменяет записи в БД.

    Логирует информацию, предупреждения и ошибки для отслеживания процесса.
    """
    try:
        three_hours_ago = timezone.now() - datetime.timedelta(hours=3)

        lessons = models.LessonAttendance.objects.filter(last_out__isnull=True, first_in__lte=three_hours_ago)

        if not lessons.exists():
            logger.warning("Нет записей для обновления Lesson Attendance last_out.")
            return

        updated_lessons = []
        for lesson in lessons:
            first_in = lesson.first_in
            end_of_day = first_in.replace(hour=23, minute=59, second=59, microsecond=0)

            lesson.last_out = min(first_in + datetime.timedelta(hours=3), end_of_day)
            updated_lessons.append(lesson)

        models.LessonAttendance.objects.bulk_update(updated_lessons, ['last_out'])

        logger.warning(f"Обновлено {len(updated_lessons)} записей: last_out установлен успешно.")

    except Exception as e:
        logger.error(f"Ошибка при выполнении update_lesson_attendance_last_out: {e}")



@shared_task
def process_lesson_attendance_batch(attendance_data, image_name, image_content):
    """
    Асинхронная задача для создания записей посещаемости с сохранением фотографий сотрудников.

    Функция обрабатывает список посещаемости и создает соответствующие записи в базе данных.
    Если фотография предоставлена, она сохраняется в файловой системе. Добавлены расширенные
    логирования для отслеживания ошибок и предупреждений.

    Args:
        attendance_data (list): Данные посещаемости, где каждый элемент содержит:
            - staff_pin (str): Уникальный PIN сотрудника.
            - tutor_id (int): Идентификатор преподавателя.
            - tutor (str): ФИО преподавателя.
            - first_in (str): Дата и время начала занятия в формате ISO 8601.
            - latitude (float): Географическая широта места занятия.
            - longitude (float): Географическая долгота места занятия.
        image_name (str): Название файла для сохранения фотографии.
        image_content (bytes): Содержимое изображения в формате байтов.

    Returns:
        dict: Результат обработки задачи с информацией об успешных и неудачных записях:
            - "success_records" (list): ID успешно созданных записей.
            - "error_records" (list): Ошибки с описанием проблемы.

    Raises:
        Exception: Логирует подробные ошибки при сохранении записи или изображения.
    """
    success_records = []
    error_records = []

    for record in attendance_data:
        try:
            staff_pin = record.get("staff_pin")
            tutor_id = record.get("tutor_id")
            tutor = record.get("tutor")
            first_in = record.get("first_in")
            latitude = record.get("latitude")
            longitude = record.get("longitude")

            timestamp = int(timezone.now().timestamp())
            image_name = f"{staff_pin}_{timestamp}.jpg"

            staff = models.Staff.objects.get(pin=staff_pin)
            logger.info(f"Найден сотрудник с PIN: {staff_pin}")

            date_path = timezone.now().strftime("%Y-%m-%d")
            base_path = (
                f"{settings.MEDIA_ROOT}/control_image/{staff_pin}/{date_path}"
                if settings.DEBUG
                else f"{settings.ATTENDANCE_ROOT}/{staff_pin}/{date_path}"
            )

            os.makedirs(base_path, exist_ok=True)
            logger.info(f"Создан путь для сохранения изображений: {base_path}")

            file_path = os.path.join(base_path, image_name)

            try:
                with open(file_path, "wb") as destination:
                    destination.write(image_content)
                logger.info(f"Фотография успешно сохранена: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении файла изображения: {str(e)}")
                raise

            lesson_attendance = models.LessonAttendance.objects.create(
                staff=staff,
                tutor_id=tutor_id,
                tutor=tutor,
                first_in=first_in,
                latitude=latitude,
                longitude=longitude,
                date_at=timezone.now().date(),
                staff_image_path=file_path,
            )
            logger.info(f"Запись посещаемости успешно создана с ID: {lesson_attendance.id}")

            success_records.append({"id": lesson_attendance.id})

        except models.Staff.DoesNotExist:
            error_message = f"Сотрудник с PIN {staff_pin} не найден."
            logger.warning(error_message)
            error_records.append({"staff_pin": staff_pin, "error": error_message})
        except Exception as e:
            logger.error(f"Общая ошибка при обработке записи посещаемости: {str(e)}")
            error_records.append({"staff_pin": staff_pin, "error": str(e)})

    logger.info(f"Итоговые успешные записи: {success_records}")
    logger.warning(f"Итоговые ошибки записи: {error_records}")

    return {"success_records": success_records, "error_records": error_records}


def generate_negative_samples(staff, neighbors_count=6):
    staff_list = np.array(models.Staff.objects.filter(avatar__isnull=False).order_by('pin'))

    staff_index = np.where(staff_list == staff)[0][0]

    indices = [(staff_index - i) % len(staff_list) for i in range(1, neighbors_count + 1)] + [
        (staff_index + i) % len(staff_list) for i in range(1, neighbors_count + 1)
    ]

    neighbors = staff_list[indices]

    negative_embeddings = []

    for neighbor in neighbors:
        try:
            image_path = os.path.join(settings.MEDIA_ROOT, neighbor.avatar.path)
            image = cv2.imread(image_path)
            if image is not None:
                encoding = utils.create_face_encoding(image)
                negative_embeddings.append(encoding)
        except Exception:
            logger.warning(f"Failed to create encoding for negative sample from {neighbor.pin}")

    return negative_embeddings


@shared_task
def augment_user_images(remove_old_files=False):
    augmentations = A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.RandomBrightnessContrast(p=0.5),
            A.GaussianBlur(p=0.3),
            A.Rotate(limit=40, p=0.7),
            A.ShiftScaleRotate(shift_limit=0.0625, scale_limit=0.2, rotate_limit=30, p=0.5),
            A.HueSaturationValue(p=0.5),
            A.Sharpen(p=0.3),
            A.Perspective(p=0.3),
            A.RandomResizedCrop(112, 112, scale=(0.8, 1.0), p=0.5),
        ]
    )

    staff_members = models.Staff.objects.filter(avatar__isnull=False, needs_training=True)
    success_count = 0
    error_count = 0
    error_logs = []

    for staff in staff_members:
        try:
            if not staff.avatar or not staff.avatar.name:
                raise ValueError(f"Staff {staff.pin} does not have an avatar associated with it.")

            image_path = os.path.join(settings.MEDIA_ROOT, staff.avatar.path)

            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image for {staff.pin} not found at {image_path}")

            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Failed to load image for {staff.pin}")

            output_dir = (
                os.path.join(settings.AUGMENT_ROOT, staff.pin)
                if not settings.DEBUG
                else os.path.join(os.path.dirname(image_path), 'augmented_images')
            )
            os.makedirs(output_dir, exist_ok=True)

            if remove_old_files:
                logger.info(f"Removing old augmented images and model for {staff.pin}")

                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                    os.makedirs(output_dir, exist_ok=True)

                model_path = os.path.join(
                    os.path.dirname(staff.avatar.path), f'{staff.pin}_model.pkl'
                )
                if os.path.exists(model_path):
                    os.remove(model_path)
                    logger.info(f"Removed old model file for {staff.pin}: {model_path}")

            augmented_images = []
            for i in range(10):
                augmented_image = augmentations(image=image)["image"]
                augmented_images.append(augmented_image)

            for i, aug_image in enumerate(augmented_images):
                augmented_filename = f'{staff.pin}_augmented_{i}.jpg'
                augmented_path = os.path.join(output_dir, augmented_filename)
                cv2.imwrite(augmented_path, aug_image)

            embeddings = [utils.create_face_encoding(image) for image in augmented_images]

            negative_embeddings = generate_negative_samples(staff)

            train_machine_learning_model(staff, embeddings, negative_embeddings)

            staff.needs_training = False
            staff.save()
            success_count += 1
        except Exception as e:
            error_logs.append(f"Error for {staff.pin}: {str(e)}")
            logger.error(f"Error for {staff.pin}: {str(e)}")
            log_photo_error(f"Error for {staff.pin}: {str(e)}")
            error_count += 1

    return {
        "status": "Completed",
        "successful_augmentations": success_count,
        "failed_augmentations": error_count,
        "error_log": error_logs,
    }


def train_machine_learning_model(staff, embeddings, negative_embeddings):
    try:
        avatar_dir = os.path.dirname(staff.avatar.path)
        model_path = os.path.join(avatar_dir, f'{staff.pin}_model.pkl')

        if os.path.exists(model_path):
            model = joblib.load(model_path)
            logger.info(f"Loading existing model for {staff.pin}")
        else:
            model = svm.SVC(kernel='linear', probability=True)
            logger.info(f"Creating new model for {staff.pin}")

        scaler = StandardScaler()
        embeddings = scaler.fit_transform(embeddings)
        negative_embeddings = scaler.fit_transform(negative_embeddings)

        labels = [1] * len(embeddings) + [0] * len(negative_embeddings)
        embeddings_combined = np.vstack([embeddings, negative_embeddings])

        if len(set(labels)) < 2:
            raise ValueError("The number of classes has to be greater than one; got 1 class")

        model.fit(embeddings_combined, labels)

        joblib.dump(model, model_path)
        logger.info(f"Model for {staff.pin} saved at {model_path}")

    except Exception as e:
        logger.error(f"Error training model for {staff.pin}: {str(e)}")
        raise e


def initialize_log_file():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    if os.path.exists(error_log_file) and os.path.getsize(error_log_file) > LOG_FILE_MAX_SIZE:
        os.remove(error_log_file)

    with open(error_log_file, "a") as log_file:
        log_file.write(f"========== Лог начат {timezone.localtime(timezone.now())} ==========\n")


def log_photo_error(message):
    initialize_log_file()
    current_time = timezone.localtime(timezone.now())
    with open(error_log_file, "a") as log_file:
        log_file.write(f"{current_time}: {message}\n")
    logger.warning(message)
