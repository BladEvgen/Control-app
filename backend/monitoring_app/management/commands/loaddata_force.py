import os
import json

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load data from a JSON file and overwrite existing entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path", type=str, help="Path to the JSON file to load data from."
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]
        if not os.path.exists(file_path):
            self.stderr.write(f"The file {file_path} does not exist.")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for entry in data:
            model_name = entry["model"]
            pk = entry["pk"]

            model = apps.get_model(model_name)

            try:
                obj = model.objects.get(pk=pk)
                obj.delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"Deleted existing object with PK {pk} in {model_name}."
                    )
                )
            except model.DoesNotExist:
                pass

        call_command("loaddata", file_path)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully loaded data from {file_path}.")
        )
