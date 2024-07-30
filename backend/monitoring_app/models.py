import os
import shutil
from django.utils import timezone
from django.contrib import messages
from django.dispatch import receiver
from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.validators import FileExtensionValidator
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save

from monitoring_app import utils


class APIKey(models.Model):
    key_name = models.CharField(
        max_length=100, null=False, blank=False, verbose_name="Название ключа"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name="Создатель"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    key = models.CharField(max_length=256, editable=False, verbose_name="Ключ")
    is_active = models.BooleanField(
        default=True, editable=True, verbose_name="Статус активности"
    )

    def __str__(self):
        status = "Активен" if self.is_active else "Деактивирован"

        return f"Ключ: {self.key_name}  Статус активности: {status}"

    def save(self, *args, **kwargs):
        if not self.key:
            encrypted_key, secret_key = utils.APIKeyUtility.generate_api_key(
                self.key_name, self.created_by
            )
            self.key = encrypted_key
        super(APIKey, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "API Ключ"
        verbose_name_plural = "API Ключи"


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )
    is_banned = models.BooleanField(default=False, verbose_name="Статус Блокировки")
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
    UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=UserProfile)
def update_user_active_status(sender, instance, **kwargs):
    if instance.is_banned:
        instance.user.is_active = False
    else:
        instance.user.is_active = True
    instance.user.save()


@receiver(post_delete, sender=UserProfile)
def delete_user_on_profile_delete(sender, instance, **kwargs):
    user = instance.user
    user.delete()


@receiver(post_save, sender=UserProfile)
@receiver(post_delete, sender=UserProfile)
def update_jwt_token(sender, instance, **kwargs):
    user = instance.user
    RefreshToken.for_user(user)


class FileCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название шаблона")
    slug = models.SlugField(unique=True, verbose_name="Ссылка")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Категория файла"
        verbose_name_plural = "Категории файлов"


class ParentDepartment(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="Номер отдела")
    name = models.CharField(max_length=255, unique=True, verbose_name="Название отдела")
    date_of_creation = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата создания"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Родительский отдел"
        verbose_name_plural = "Родительские отделы"


class ChildDepartment(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="Номер отдела")
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

    def __str__(self):
        return self.name

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


class Position(models.Model):
    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        verbose_name="Профессия",
        default="Сотрудник",
    )
    rate = models.DecimalField(
        max_digits=4, decimal_places=2, verbose_name="Ставка", default=1
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
        validators=[FileExtensionValidator(allowed_extensions=["jpg"])],
    )

    def __str__(self):
        return f"{self.surname} {self.name}"

    def save(self, *args, **kwargs):
        if self.pk:
            old_avatar = Staff.objects.filter(pk=self.pk).values("avatar").first()
            if old_avatar and old_avatar["avatar"] != self.avatar and self.avatar:
                try:
                    old_avatar_path = old_avatar["avatar"]
                    if os.path.exists(old_avatar_path):
                        os.remove(old_avatar_path)
                except Exception as e:
                    print(f"Ошибка при удалении старой аватарки: {e}")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        avatar_dir = os.path.dirname(self.avatar.path)
        if os.path.exists(avatar_dir):
            try:
                shutil.rmtree(avatar_dir)
            except Exception as e:
                print(f"Ошибка при удалении директории с аватаркой: {e}")
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"


@receiver(post_delete, sender=Staff)
def delete_avatar_on_staff_delete(sender, instance, **kwargs):
    avatar_dir = os.path.dirname(instance.avatar.path)
    if os.path.exists(avatar_dir):
        try:
            shutil.rmtree(avatar_dir)
        except Exception as e:
            print(
                f"Ошибка при удалении директории с аватаркой после удаления сотрудника: {e}"
            )


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

    def __str__(self) -> str:
        return f"{self.staff} {self.date_at.strftime('%d-%m-%Y')}"

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

        verbose_name = "Посещаемость сотрудника"
        verbose_name_plural = "Посещаемость сотрудников"


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
        verbose_name = "Зарплата"
        verbose_name_plural = "Зарплаты"

    def clean(self):
        total_rate = sum(self.staff.positions.values_list("rate", flat=True))
        if total_rate > 1.5:
            raise ValidationError(
                "Суммарная ставка не может превышать 1.5. Пожалуйста, измените ставки должностей."
            )

    @staticmethod
    def calculate_total_salary(net_salary, rate):
        return net_salary * rate

    def calculate_salaries(self):
        self.clean()
        total_rate = sum(self.staff.positions.values_list("rate", flat=True))
        self.total_salary = self.calculate_total_salary(self.net_salary, total_rate)

    def save(self, *args, **kwargs):
        try:
            with transaction.atomic():
                self.calculate_salaries()
                super().save(*args, **kwargs)
        except ValidationError:
            if hasattr(self, "_request"):
                messages.error(
                    self._request,
                    "Суммарная ставка не может превышать 1.5. Изменения не сохранены.",
                )
            previous_instance = Salary.objects.get(pk=self.pk)
            self.total_salary = previous_instance.total_salary


@receiver(pre_save, sender=Salary)
def calculate_salaries(sender, instance, **kwargs):
    instance.calculate_salaries()


@receiver(m2m_changed, sender=Staff.positions.through)
def update_salary_on_position_change(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        for salary in instance.salaries.all():
            try:
                with transaction.atomic():
                    salary.calculate_salaries()
                    salary.save(update_fields=["total_salary"])
            except ValidationError:
                if hasattr(salary, "_request"):
                    messages.error(
                        salary._request,
                        "Суммарная ставка не может превышать 1.5. Изменения не сохранены.",
                    )
                previous_instance = Salary.objects.get(pk=salary.pk)
                salary.total_salary = previous_instance.total_salary


class PublicHoliday(models.Model):
    date = models.DateField(unique=True, verbose_name="Дата праздника")
    name = models.CharField(max_length=255, verbose_name="Название праздника")
    is_working_day = models.BooleanField(default=False, verbose_name="Рабочий день")

    def __str__(self):
        return f"{self.name} ({self.date})"

    class Meta:
        verbose_name = "Праздничный день"
        verbose_name_plural = "Праздничные дни"
