import os
from django.conf import settings
from monitoring_app.models import Staff
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Django management command to clean up unused .jpg files from the user_images directory.

    This command identifies all .jpg files in the `user_images` directory that are not referenced
    in the `avatar` field of the `Staff` model and deletes them in one operation to minimize I/O.

    Attributes:
        help (str): Description of the command for help output.
    """

    help = "Removes unused .jpg files in the user_images directory."

    def handle(self, *args, **kwargs):
        """
        Executes the cleanup command.

        1. Scans the `user_images` directory for all .jpg files.
        2. Collects the list of .jpg files in the `avatar` field of the `Staff` model.
        3. Deletes files not referenced in the database in a single batch operation.

        Raises:
            Exception: If an error occurs during file deletion.
        """
        media_root = settings.MEDIA_ROOT
        base_path = os.path.join(media_root, "user_images")

        if not os.path.exists(base_path):
            self.stdout.write(
                self.style.ERROR(f"Directory {base_path} does not exist.")
            )
            return

        used_files = set(
            os.path.join(media_root, avatar)
            for avatar in Staff.objects.filter(avatar__isnull=False).values_list(
                "avatar", flat=True
            )
        )

        all_files = [
            os.path.join(root, file)
            for root, _, files in os.walk(base_path)
            for file in files
            if file.lower().endswith(".jpg")
        ]

        unused_files = set(all_files) - used_files

        if not unused_files:
            self.stdout.write(self.style.SUCCESS("No unused .jpg files found."))
            return

        try:
            for file_path in unused_files:
                os.remove(file_path)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully removed {len(unused_files)} unused .jpg files."
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during file removal: {e}"))
