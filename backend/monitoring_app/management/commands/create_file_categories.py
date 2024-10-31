from monitoring_app.models import FileCategory
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates initial file categories in the FileCategory model"

    def handle(self, *args, **kwargs):
        categories = [
            {"name": "Отделы", "slug": "departments"},
            {"name": "Сотрудники", "slug": "staff"},
            {"name": "Удаление сотрудников", "slug": "delete_staff"},
            {"name": "Фото", "slug": "photo"},
        ]

        for category_data in categories:
            name = category_data["name"]
            slug = category_data["slug"]

            if FileCategory.objects.filter(slug=slug).exists():
                self.stdout.write(
                    self.style.WARNING(
                        f'Category with slug "{slug}" already exists. Skipping.'
                    )
                )
                continue

            FileCategory.objects.create(name=name, slug=slug)
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created category "{name}"')
            )

        self.stdout.write(self.style.SUCCESS("Initial categories creation complete"))
