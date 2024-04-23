import os
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.db.models.signals import pre_save, m2m_changed, post_save, post_delete


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )
    is_banned = models.BooleanField(default=False, verbose_name="Статус Блокировки")
    phonenumber = models.CharField(max_length=20, verbose_name="Номер телефона")
    address = models.TextField(verbose_name="Адрес")

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
        ParentDepartment,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Родительский отдел",
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        existing_child_department = ChildDepartment.objects.filter(
            name=self.name
        ).exists()
        if existing_child_department:
            pass
        else:
            super().save(*args, **kwargs)

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
        return f"{self.surname} {self.name}  {self.department.name if self.department else 'N/A'}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"


@receiver(pre_save, sender=Staff)
def delete_old_avatar(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Staff.objects.get(pk=instance.pk)
            old_avatar = old_instance.avatar
            if old_avatar:
                if os.path.exists(old_avatar.path):
                    os.remove(old_avatar.path)
        except Staff.DoesNotExist:
            pass

    new_avatar = instance.avatar
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
        auto_now_add=True,
        editable=False,
    )
    first_in = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время первого входа",
        editable=False,
        default=None,
    )
    last_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время последнего выхода",
        editable=False,
        default=None,
    )

    def __str__(self) -> str:
        return f"{self.staff} {self.date_at.strftime('%d-%m-%Y')}"

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
        ipn_percentage = Decimal("0.10")  # ИПН - 10%
        opv_percentage = Decimal("0.10")  # ОПВ - 10%
        vosms_percentage = Decimal("0.02")  # ВОСМС - 2%

        deduction_percentage = ipn_percentage + opv_percentage + vosms_percentage

        mrp = 3692
        taxable_amount = clean_salary - mrp

        deduction = taxable_amount * deduction_percentage

        dirty_salary = taxable_amount + deduction

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
