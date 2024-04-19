from decimal import Decimal

from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save


class FileCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class ParentDepartment(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    date_of_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ChildDepartment(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    date_of_creation = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(ParentDepartment, on_delete=models.CASCADE)

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


class Position(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    rate = models.DecimalField(max_digits=4, decimal_places=2)

    def __str__(self):
        return f"{self.name} Ставка: {self.rate}"


class Staff(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False)
    surname = models.CharField(max_length=255, blank=False, null=False)
    patronymic = models.CharField(max_length=255, blank=True, null=True)
    cart_id = models.IntegerField(unique=True, null=True, blank=True)
    department = models.ForeignKey(
        ChildDepartment, on_delete=models.SET_NULL, null=True
    )
    date_of_creation = models.DateTimeField(auto_now_add=True, editable=False)
    positions = models.ManyToManyField(Position)

    def __str__(self):
        return f"ФИО {self.surname} {self.name}  {self.department.name if self.department else 'N/A'}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Salary(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="salaries")

    clean_salary = models.DecimalField(
        max_digits=10, decimal_places=2, blank=False, null=False
    )  # Чистая зарплата после вычетов
    dirty_salary = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, editable=False
    )  # Грязная зарплата до вычетов
    total_salary = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True, editable=False
    )

    @staticmethod
    def calculate_dirty_salary(clean_salary):
        ipn_percentage = Decimal("0.10")  # ИПН - 10%
        opv_percentage = Decimal("0.10")  # ОПВ - 10%
        vosms_percentage = Decimal("0.02")  # ВОСМС - 2%

        deduction_percentage = ipn_percentage + opv_percentage + vosms_percentage

        return clean_salary / (Decimal("1") - deduction_percentage)

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


@receiver(post_save, sender=Staff)
def update_salary(sender, instance, **kwargs):
    for salary in instance.salaries.all():
        salary.calculate_salaries()
        salary.save(update_fields=["total_salary"])
