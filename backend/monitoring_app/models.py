from django.db import models


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
