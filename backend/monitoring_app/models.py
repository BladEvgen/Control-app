import os
from decimal import Decimal
from django.db import models
from monitoring_app import utils
from django.utils import timezone
from django.dispatch import receiver
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.validators import FileExtensionValidator
from django.db.models.signals import pre_save, m2m_changed, post_save, post_delete


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
        default=True, editable=False, verbose_name="Статус активности"
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
    refresh = RefreshToken.for_user(user)


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
        return f"{self.surname} {self.name} {self.department.name if self.department else 'N/A'}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"


@receiver(pre_save, sender=Staff)
def delete_old_avatar(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_instance = Staff.objects.get(pk=instance.pk)
    except Staff.DoesNotExist:
        return

    old_avatar = old_instance.avatar
    new_avatar = instance.avatar

    if old_avatar and old_avatar != new_avatar:
        if os.path.exists(old_avatar.path):
            os.remove(old_avatar.path)

    if new_avatar:
        new_avatar.name = user_avatar_path(instance, new_avatar.name)


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
        existing_record = StaffAttendance.objects.filter(
            staff=self.staff, date_at=self.date_at
        ).exists()
        if existing_record:
            return
        else:
            super().save(*args, **kwargs)

    class Meta:
        unique_together = [["staff", "date_at"]]

        verbose_name = "Посещаемость сотрудника"
        verbose_name_plural = "Посещаемость сотрудников"


class Salary(models.Model):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="salaries",
        verbose_name="Сотрудник",
    )

    clean_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=False,
        null=False,
        verbose_name="Чистая зарплата",
    )
    dirty_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False,
        verbose_name="Грязная зарплата",
    )
    total_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False,
        verbose_name="Итогавая зарплата",
    )

    class Meta:
        verbose_name = "Зарплата"
        verbose_name_plural = "Зарплаты"

    @staticmethod
    def calculate_dirty_salary(clean_salary):
        # Percentages
        opvr_percentage = Decimal("0.015")  # ОПВР - 1.5%
        vosms_percentage = Decimal("0.02")  # ВОСМС - 2%
        oosms_percentage = Decimal("0.03")  # ООСМС - 3%
        so_percentage = Decimal("0.035")  # СО - 3.5%
        sn_percentage = Decimal("0.095")  # СН - 9.5%

        # Limits
        min_sn_limit = 14 * 3692  # 14 МРП = 51 688 тенге
        max_opv_limit = 50 * 85000  # 50 МЗП = 4 250 000 тенге
        max_vosms_limit = 10 * 85000  # 10 МЗП = 850 000 тенге
        max_oosms_limit = 10 * 85000  # 10 МЗП = 850 000 тенге
        max_so_limit = 7 * 85000  # 7 МЗП = 595 000 тенге

        # Calculate deductions
        opvr_deduction = min(clean_salary, max_opv_limit) * opvr_percentage
        vosms_deduction = min(clean_salary, max_vosms_limit) * vosms_percentage
        oosms_deduction = min(clean_salary, max_oosms_limit) * oosms_percentage
        so_deduction = min(max(clean_salary, 85000), max_so_limit) * so_percentage
        sn_deduction = max(clean_salary, min_sn_limit) * sn_percentage

        # Total deductions
        total_deductions = (
            opvr_deduction
            + vosms_deduction
            + oosms_deduction
            + so_deduction
            + sn_deduction
        )

        # Calculate dirty salary
        dirty_salary = clean_salary + total_deductions

        return dirty_salary

    @staticmethod
    def calculate_total_salary(clean_salary, rate):
        return clean_salary * rate

    def calculate_salaries(self):
        total_rate = sum(self.staff.positions.values_list("rate", flat=True))
        self.dirty_salary = self.calculate_dirty_salary(self.clean_salary)
        self.total_salary = self.calculate_total_salary(self.clean_salary, total_rate)


@receiver(pre_save, sender=Salary)
def calculate_salaries(sender, instance, **kwargs):
    instance.calculate_salaries()


@receiver(m2m_changed, sender=Staff.positions.through)
def update_salary_on_position_change(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        for salary in instance.salaries.all():
            salary.calculate_salaries()
            salary.save(update_fields=["total_salary"])


class PublicHoliday(models.Model):
    date = models.DateField(unique=True, verbose_name="Дата праздника")
    name = models.CharField(max_length=255, verbose_name="Название праздника")
    is_working_day = models.BooleanField(default=False, verbose_name="Рабочий день")

    def __str__(self):
        return f"{self.name} ({self.date})"

    class Meta:
        verbose_name = "Праздничный день"
        verbose_name_plural = "Праздничные дни"
