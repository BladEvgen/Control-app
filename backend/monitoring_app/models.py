import os
import shutil
from contextlib import AbstractContextManager
from decimal import Decimal
from datetime import date, datetime
from typing import Any, Optional, cast

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.db.models.fields.files import FieldFile
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import get_random_string
from django_admin_geomap import GeoItem
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AtomicBlock(AbstractContextManager[None]):
    def __init__(self) -> None:
        self._context = transaction.atomic()

    def __enter__(self) -> None:
        self._context.__enter__()
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        return self._context.__exit__(exc_type, exc_value, traceback)


def atomic_block() -> AtomicBlock:
    return AtomicBlock()


def boolean_field(default_value: bool, **kwargs: Any) -> models.BooleanField:
    field = models.BooleanField(**kwargs)
    field.default = default_value
    return field


class PasswordResetTokenManager(models.Manager):
    def mark_as_used(self, token):
        token_obj = self.filter(token=token, _used=False).first()
        if token_obj and token_obj.is_valid():
            token_obj.used = True
            token_obj.save(update_fields=["_used"])
            return True
        return False


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name="Пользователь"
    )
    token = models.CharField(max_length=64, unique=True, verbose_name="Токен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    _used = boolean_field(False, verbose_name="Статус использования")

    objects = PasswordResetTokenManager()

    @property
    def used(self):
        return self._used

    def is_valid(self):
        expiration_time = timezone.now() - timezone.timedelta(hours=1)
        return self.created_at > expiration_time and not self._used

    @used.setter
    def used(self, value: bool) -> None:
        self._used = value

    @staticmethod
    def generate_token(user):
        token = get_random_string(64)
        PasswordResetToken.objects.create(user=user, token=token)
        return token

    def save(self, *args, **kwargs):
        if self.pk:
            original = PasswordResetToken.objects.get(pk=self.pk)
            if original.token != self.token:
                self.token = original.token
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Токен для сброса пароля"
        verbose_name_plural = "Токены для сброса паролей"


class PasswordResetRequestLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь"
    )
    ip_address = models.GenericIPAddressField(verbose_name="IP-адрес")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Время запроса")

    @staticmethod
    def is_recent_request(user, ip_address):
        five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
        return PasswordResetRequestLog.objects.filter(
            user=user, ip_address=ip_address, requested_at__gte=five_minutes_ago
        ).exists()

    @staticmethod
    def get_last_request_time(user, ip_address):
        last_request = (
            PasswordResetRequestLog.objects.filter(user=user, ip_address=ip_address)
            .order_by("-requested_at")
            .first()
        )
        return last_request.requested_at if last_request else None

    @staticmethod
    def log_request(user, ip_address):
        PasswordResetRequestLog.objects.create(user=user, ip_address=ip_address)

    @staticmethod
    def can_request_again(user, ip_address):
        last_request_time = PasswordResetRequestLog.get_last_request_time(
            user, ip_address
        )
        if not last_request_time:
            return True
        return timezone.now() >= last_request_time + timezone.timedelta(minutes=5)

    class Meta:
        verbose_name = "Лог запросов на сброс пароля"
        verbose_name_plural = "Логи запросов на сброс пароля"


class APIKey(models.Model):

    key_name = models.CharField(
        max_length=100, null=False, blank=False, verbose_name="Название ключа"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Создатель",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    key = models.CharField(max_length=256, editable=False, verbose_name="Ключ")
    is_active = boolean_field(True, editable=True, verbose_name="Статус активности")

    def __str__(self):
        status = "Активен" if self.is_active else "Деактивирован"

        return f"Ключ: {self.key_name}  Статус активности: {status}"

    def save(self, *args, **kwargs):
        from monitoring_app import utils

        if not self.key:
            encrypted_key, _secret_key = utils.APIKeyUtility.generate_api_key(
                self.key_name, self.created_by
            )
            self.key = encrypted_key
        super(APIKey, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "API Ключ"
        verbose_name_plural = "API Ключи"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )
    is_banned = boolean_field(False, verbose_name="Статус Блокировки")
    phonenumber = models.CharField(max_length=20, verbose_name="Номер телефона")
    last_login_ip = models.GenericIPAddressField(
        verbose_name="Последний IP-адрес входа", null=True, blank=True
    )

    def __str__(self):
        return f"{self.user.username} Profile"

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    _ = sender
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=UserProfile)
def update_user_active_status(sender, instance, **kwargs):
    _ = sender
    if instance.is_banned:
        instance.user.is_active = False
    else:
        instance.user.is_active = True
    instance.user.save()


@receiver(post_delete, sender=UserProfile)
def delete_user_on_profile_delete(sender, instance, **kwargs):
    _ = sender
    user = instance.user
    user.delete()


@receiver(post_save, sender=UserProfile)
@receiver(post_delete, sender=UserProfile)
def update_jwt_token(sender, instance, **kwargs):
    _ = sender
    user = instance.user
    RefreshToken.for_user(user)


class FileCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название шаблона")
    slug = models.SlugField(unique=True, verbose_name="Ссылка")

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = "Категория файла"
        verbose_name_plural = "Категории файлов"


class ParentDepartment(models.Model):
    id = models.CharField(primary_key=True, verbose_name="Номер отдела", max_length=10)
    name = models.CharField(max_length=255, unique=True, verbose_name="Название отдела")
    date_of_creation = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата создания"
    )

    def __str__(self) -> str:
        return str(self.name)

    @classmethod
    def len_parent_departments(cls) -> int:
        return cls.objects.count()

    class Meta:
        verbose_name = "Родительский отдел"
        verbose_name_plural = "Родительские отделы"


class ChildDepartment(models.Model):
    id = models.CharField(primary_key=True, verbose_name="Номер отдела", max_length=10)
    name = models.CharField(max_length=255, verbose_name="Название отдела")
    date_of_creation = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата создания"
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительский отдел",
    )

    def __str__(self) -> str:
        return str(self.name)

    @classmethod
    def len_child_departments(cls) -> int:
        return cls.objects.count()

    def save(self, *args, **kwargs):
        if not self.id:
            existing_child_department = ChildDepartment.objects.filter(
                name=self.name
            ).first()
            if existing_child_department:
                self.id = existing_child_department.id
                self.parent = existing_child_department.parent

        super().save(*args, **kwargs)

    def get_all_child_departments(self):
        children = self.children.all()
        all_children = list(children)
        for child in children:
            all_children.extend(child.get_all_child_departments())
        return all_children

    class Meta:
        verbose_name = "Подотдел"
        verbose_name_plural = "Подотделы"
        indexes = [
            models.Index(fields=["parent"]),
            models.Index(fields=["name"]),
        ]


class Position(models.Model):
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        verbose_name="Профессия",
        default="Сотрудник",
    )
    rate = models.DecimalField(
        max_digits=4, decimal_places=2, verbose_name="Ставка", default=Decimal("1")
    )

    def __str__(self):
        return f"{self.name} Ставка: {self.rate}"

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"


def user_avatar_path(instance, filename):
    return f"user_images/{instance.pin}/{instance.pin}.{filename.split('.')[-1]}"


class Staff(models.Model):
    pin = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        unique=True,
        verbose_name="Id сотрудника",
        editable=False,
    )
    name = models.CharField(max_length=255, blank=False, null=False, verbose_name="Имя")
    surname = models.CharField(
        max_length=255, blank=False, null=False, verbose_name="Фамилия"
    )
    department = models.ForeignKey(
        ChildDepartment, on_delete=models.SET_NULL, null=True, verbose_name="Отдел"
    )
    date_of_creation = models.DateTimeField(
        default=timezone.now, editable=False, verbose_name="Дата добавления"
    )

    positions = models.ManyToManyField(Position, verbose_name="Должность")
    avatar = models.ImageField(
        upload_to=user_avatar_path,
        null=True,
        blank=True,
        verbose_name="Фото Пользователя",
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png"])],
    )
    needs_training = boolean_field(
        True, verbose_name="Требуется обучение модели распознавания лиц"
    )

    def __str__(self):
        return f"{self.surname} {self.name}"

    def save(self, *args, **kwargs):
        if self.pk:
            old_avatar = Staff.objects.filter(pk=self.pk).values("avatar").first()
            avatar_field = cast(Optional[FieldFile], self.avatar)
            if (
                old_avatar
                and avatar_field is not None
                and avatar_field.name
                and old_avatar["avatar"] != avatar_field.name
            ):
                try:
                    old_avatar_path = os.path.join(
                        settings.MEDIA_ROOT, old_avatar["avatar"]
                    )
                    if os.path.exists(old_avatar_path):
                        os.remove(old_avatar_path)
                except Exception as e:
                    print(f"Ошибка при удалении старой аватарки: {e}")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        avatar_field = cast(Optional[FieldFile], self.avatar)
        if avatar_field is not None and avatar_field.name:
            avatar_path = getattr(avatar_field, "path", "")
            if avatar_path:
                avatar_dir = os.path.dirname(avatar_path)
                if os.path.exists(avatar_dir):
                    try:
                        shutil.rmtree(avatar_dir)
                    except Exception as e:
                        print(f"Ошибка при удалении директории с аватаркой: {e}")
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        indexes = [
            models.Index(fields=["department"]),
            models.Index(fields=["pin"]),
        ]


@receiver(post_delete, sender=Staff)
def delete_avatar_on_staff_delete(sender, instance, **kwargs):
    _ = sender
    avatar_field = cast(Optional[FieldFile], instance.avatar)
    if avatar_field is not None and avatar_field.name:
        avatar_path = getattr(avatar_field, "path", "")
        if avatar_path:
            avatar_dir = os.path.dirname(avatar_path)
            if os.path.exists(avatar_dir):
                try:
                    shutil.rmtree(avatar_dir)
                except Exception as e:
                    print(
                        f"Ошибка при удалении директории с аватаркой после удаления сотрудника: {e}"
                    )
            return
    print("Аватар отсутствует, ничего не удаляется.")


class StaffFaceMask(models.Model):
    staff = models.OneToOneField(
        Staff, on_delete=models.CASCADE, related_name="face_mask"
    )
    mask_encoding = models.JSONField(
        verbose_name="Вектор лица", blank=False, null=False
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Маска лица сотрудника"
        verbose_name_plural = "Маски лиц сотрудников"

    def __str__(self):
        return f"Face mask for {self.staff.name} {self.staff.surname} {self.staff.pin}"


class AbsentReason(models.Model):

    ABSENT_REASON_CHOICES = [
        ("business_trip", "Командировка"),
        ("sick_leave", "Болезнь"),
        ("other", "Другая причина"),
    ]

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="absences",
        verbose_name="Сотрудник",
    )
    reason = models.CharField(
        max_length=20, choices=ABSENT_REASON_CHOICES, verbose_name="Причина отсутствия"
    )
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата окончания")
    approved = boolean_field(False, verbose_name="Утверждено")
    document = models.FileField(
        upload_to="absence_documents/",
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])
        ],
        verbose_name="Документ",
    )

    def save(self, *args, **kwargs):
        from monitoring_app import utils

        if self.reason == "business_trip":
            self.approved = True
        elif self.reason == "sick_leave" and self.document:
            self.approved = True

        if self.document:
            self.document.name = utils.transliterate(self.document.name)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff} - {self.get_reason_display()} ({self.start_date} - {self.end_date})"

    class Meta:
        indexes = [
            models.Index(fields=["staff", "start_date", "end_date"]),
            models.Index(fields=["approved"]),
        ]
        verbose_name = "Уважительная причина отсутствия"
        verbose_name_plural = "Уважительные причины отсутствия"


class RemoteWork(models.Model):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="remote_work",
        verbose_name="Сотрудник",
    )
    start_date = models.DateField(verbose_name="Дата начала", null=True, blank=True)
    end_date = models.DateField(verbose_name="Дата окончания", null=True, blank=True)
    permanent_remote = boolean_field(
        False, verbose_name="Постоянная дистанционная работа"
    )

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Дата начала не может быть больше даты окончания.")
        if self.permanent_remote and (self.start_date or self.end_date):
            raise ValidationError(
                "Постоянная дистанционная работа не требует указания дат."
            )

    def __str__(self):
        return f"{self.staff} - {self.get_remote_status()}"

    def get_remote_status(self):
        return (
            "Постоянная дистанционная работа"
            if self.permanent_remote
            else f"Дистанционная работа ({self.start_date} - {self.end_date})"
        )

    class Meta:
        indexes = [
            models.Index(fields=["staff", "start_date", "end_date"]),
            models.Index(fields=["permanent_remote"]),
        ]
        verbose_name = "Дистанционная работа"
        verbose_name_plural = "Дистанционная работа"


class StaffAttendance(models.Model):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="attendance",
        verbose_name="Сотрудник",
        editable=False,
    )
    date_at = models.DateField(
        verbose_name="Дата добавления записи в Таблицу",
        editable=False,
    )
    first_in = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время первого входа",
        editable=True,
        default=None,
    )
    last_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время последнего выхода",
        editable=True,
        default=None,
    )

    absence_reason = models.ForeignKey(
        AbsentReason,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="Причина отсутствия",
    )

    area_name_in = models.CharField(
        null=True, blank=True, max_length=300, verbose_name="Зона входа"
    )
    area_name_out = models.CharField(
        null=True, blank=True, max_length=300, verbose_name="Зона выхода"
    )

    def __str__(self) -> str:
        attendance_value = self.date_at
        formatted_date = (
            attendance_value.strftime("%d-%m-%Y")
            if isinstance(attendance_value, date)
            else str(attendance_value)
        )
        return f"{self.staff} {formatted_date}"

    def save(self, *args, **kwargs):
        if "force_insert" in kwargs:
            kwargs.pop("force_insert")

        if self.pk and not self._state.adding:
            orig = StaffAttendance.objects.get(pk=self.pk)
            if (
                self.first_in != orig.first_in or self.last_out != orig.last_out
            ) and "admin" in kwargs:
                raise ValidationError(
                    "Нельзя изменять поля first_in и last_out через админку."
                )

        super().save(*args, **kwargs)

    class Meta:
        unique_together = [["staff", "date_at"]]
        indexes = [
            models.Index(fields=["staff", "date_at"]),
            models.Index(fields=["date_at", "staff"], name="stfatt_date_staff_idx"),
            models.Index(fields=["date_at"]),
            models.Index(fields=["first_in"]),
            models.Index(fields=["last_out"]),
        ]
        verbose_name = "Посещаемость сотрудника"
        verbose_name_plural = "Посещаемость сотрудников"


class LessonAttendance(models.Model, GeoItem):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="lesson_attendance",
        verbose_name="Сотрудник",
    )
    subject_name = models.CharField(
        verbose_name="Название предмета",
        max_length=300,
    )
    tutor_id = models.IntegerField(verbose_name="Id преподавателя")
    tutor = models.CharField(verbose_name="ФИО преподавателя", max_length=300)
    first_in = models.DateTimeField(verbose_name="Время начала занятия", null=False)
    last_out = models.DateTimeField(
        verbose_name="Время окончания занятия", null=True, blank=True
    )
    latitude = models.FloatField(
        verbose_name="Широта",
        help_text="Примерные координаты в радиусе 300 метров",
    )
    longitude = models.FloatField(
        verbose_name="Долгота",
        help_text="Примерные координаты в радиусе 300 метров",
    )
    date_at = models.DateField(verbose_name="Дата занятия", default=timezone.now)
    staff_image_path = models.CharField(
        max_length=500,
        verbose_name="Путь к фотографии сотрудника",
        null=True,
        blank=True,
    )

    @property
    def image_url(self):
        if self.staff_image_path:
            path_value = str(self.staff_image_path)
            if path_value.startswith(str(settings.ATTENDANCE_ROOT)):
                relative_path = path_value.replace(str(settings.ATTENDANCE_ROOT), "")
                return f"{settings.ATTENDANCE_URL}{relative_path}"
            media_tail = path_value.split("media/")[-1]
            return f"{settings.MEDIA_URL}{media_tail}"
        return "/static/media/images/no-avatar.png"

    def is_photo_expired(self):
        lesson_date = cast(date, self.date_at)
        return (timezone.now().date() - lesson_date).days > 31

    @property
    def geomap_longitude(self):
        return str(self.longitude)

    @property
    def geomap_latitude(self):
        return str(self.latitude)

    @property
    def formatted_first_in(self):
        first_in_value = self.first_in
        if isinstance(first_in_value, datetime):
            return first_in_value.strftime("%Y-%m-%d %H:%M:%S")
        return "-"

    @property
    def formatted_last_out(self):
        last_out_value = self.last_out
        if isinstance(last_out_value, datetime):
            return last_out_value.strftime("%Y-%m-%d %H:%M:%S")
        return "Ongoing"

    @property
    def tutor_info(self):
        return f"{self.tutor} (TutorID: {self.tutor_id})"

    def __str__(self):
        return f"{self.subject_name} ({self.staff}) [{self.date_at}]"

    class Meta:
        indexes = [
            models.Index(fields=["staff", "date_at"]),
            models.Index(fields=["date_at", "first_in"], name="lsnatt_date_first_idx"),
            models.Index(fields=["staff", "first_in"], name="lsnatt_staff_first_idx"),
            models.Index(fields=["date_at"]),
            models.Index(fields=["first_in"]),
            models.Index(fields=["last_out"]),
            models.Index(fields=["tutor_id"]),
        ]
        verbose_name = "Посещаемость занятия"
        verbose_name_plural = "Посещаемость занятий"


class ClassLocation(models.Model, GeoItem):
    name = models.CharField(
        max_length=255, verbose_name="Название учебного места", editable=True
    )
    address = models.CharField(max_length=255, verbose_name="Адрес", editable=True)
    latitude = models.FloatField(
        verbose_name="Широта",
        help_text="Введите широту для отображения на карте",
        editable=True,
    )
    longitude = models.FloatField(
        verbose_name="Долгота",
        help_text="Введите долготу для отображения на карте",
        editable=True,
    )
    acceptance_radius_m = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Приёмный радиус (м)",
        help_text="Переопределение: если задано, используется вместо вычисленного по соседям. 20–30 м — кабинет, 50–100 м — здание/двор. Подберите по кругу на карте в админке.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата создания", editable=False
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Дата обновления", editable=False
    )

    class Meta:
        verbose_name = "Локация для занятий"
        verbose_name_plural = "Локации для занятий"
        indexes = [
            models.Index(fields=["latitude", "longitude"], name="cloc_lat_lon_idx"),
            models.Index(fields=["acceptance_radius_m"], name="cloc_accept_r_idx"),
        ]

    def __str__(self):
        return f"{self.name}, {self.address} ({self.latitude}, {self.longitude})"

    @property
    def geomap_latitude(self):
        return str(self.latitude)

    @property
    def geomap_longitude(self):
        return str(self.longitude)


class Salary(models.Model):
    CONTRACT_TYPE_CHOICES = [
        ("full_time", "Полная занятость"),
        ("part_time", "Частичная занятость"),
        ("gph", "ГПХ"),
    ]
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="salaries",
        verbose_name="Сотрудник",
    )

    net_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=False,
        null=False,
        verbose_name="Чистая зарплата",
    )
    total_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False,
        verbose_name="Итоговая зарплата",
    )
    contract_type = models.CharField(
        max_length=20,
        choices=CONTRACT_TYPE_CHOICES,
        default="full_time",
        verbose_name="Тип контракта",
    )

    class Meta:
        indexes = [
            models.Index(fields=["staff"]),
            models.Index(fields=["contract_type"]),
        ]
        verbose_name = "Зарплата"
        verbose_name_plural = "Зарплаты"

    def clean(self):
        total_rate = sum(
            position.rate for position in Position.objects.filter(staff=self.staff)
        )
        if total_rate > 1.5:
            raise ValidationError(
                "Суммарная ставка не может превышать 1.5. Пожалуйста, измените ставки должностей."
            )

    @staticmethod
    def calculate_total_salary(net_salary, rate):
        return net_salary * rate

    def calculate_salaries(self):
        self.clean()
        total_rate = sum(
            position.rate for position in Position.objects.filter(staff=self.staff)
        )
        self.total_salary = self.calculate_total_salary(self.net_salary, total_rate)

    def save(self, *args, **kwargs):
        try:
            with atomic_block():
                self.calculate_salaries()
                super().save(*args, **kwargs)
        except ValidationError:
            request_context = getattr(self, "request_context", None)
            if request_context:
                messages.error(
                    request_context,
                    "Суммарная ставка не может превышать 1.5. Изменения не сохранены.",
                )
            previous_instance = Salary.objects.get(pk=self.pk)
            self.total_salary = previous_instance.total_salary


@receiver(pre_save, sender=Salary)
def calculate_salaries(sender, instance, **kwargs):
    _ = sender
    instance.calculate_salaries()


@receiver(m2m_changed, sender=Staff.positions.through)
def update_salary_on_position_change(sender, instance, action, **kwargs):
    _ = sender
    if action in ["post_add", "post_remove", "post_clear"]:
        for salary in instance.salaries.all():
            try:
                with atomic_block():
                    salary.calculate_salaries()
                    salary.save(update_fields=["total_salary"])
            except ValidationError:
                request_context = getattr(salary, "request_context", None)
                if request_context:
                    messages.error(
                        request_context,
                        "Суммарная ставка не может превышать 1.5. Изменения не сохранены.",
                    )
                previous_instance = Salary.objects.get(pk=salary.pk)
                salary.total_salary = previous_instance.total_salary


class PublicHoliday(models.Model):
    date = models.DateField(unique=True, verbose_name="Дата праздника")
    name = models.CharField(max_length=255, verbose_name="Название праздника")
    is_working_day = boolean_field(False, verbose_name="Рабочий день")

    def __str__(self):
        return f"{self.name} ({self.date})"

    class Meta:
        verbose_name = "Праздничный день"
        verbose_name_plural = "Праздничные дни"


class PerformanceBonusRule(models.Model):
    min_days = models.PositiveIntegerField(
        verbose_name="Минимальное количество рабочих дней"
    )
    max_days = models.PositiveIntegerField(
        verbose_name="Максимальное количество рабочих дней"
    )
    min_attendance_percent = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Минимальный процент посещаемости"
    )
    max_attendance_percent = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Максимальный процент посещаемости"
    )
    bonus_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="Бонус (в процентах)"
    )

    class Meta:
        verbose_name = "Правило бонуса"
        verbose_name_plural = "Правила бонуса"
        ordering = ["min_days"]

    def __str__(self):
        return (
            f"{self.min_days}-{self.max_days} дней, "
            f"{self.min_attendance_percent}-{self.max_attendance_percent}% -> "
            f"{self.bonus_percentage}%"
        )
