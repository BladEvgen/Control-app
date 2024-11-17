import os
import logging
from datetime import datetime

from django.utils import timezone
from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist

from monitoring_app.models import LessonAttendance, Staff

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create a LessonAttendance record for testing purposes."
    """
    Command to create a LessonAttendance record in the database for testing purposes.

    This command helps in creating a test record in the `LessonAttendance` model with various
    attributes like subject name, tutor, location coordinates, and a photo file associated with
    a specific staff member. It can be used to simulate lesson attendance for testing and development.

    Usage:
        python manage.py create_lesson_attendance <photo_path> <pin> [--subject_name <subject_name>] [--tutor_id <tutor_id>]
                                                   [--tutor <tutor>] [--latitude <latitude>] [--longitude <longitude>]
                                                   [--date_at <date_at>]

    Required arguments:
        photo_path (str): The path to the photo file representing the staff member's attendance.
        pin (str): The PIN associated with the staff member in the database.

    Optional arguments:
        --subject_name (str): The name of the subject for the lesson attendance (default: 'Test Subject').
        --tutor_id (int): The ID of the tutor associated with the lesson (default: 1).
        --tutor (str): The name of the tutor for the lesson attendance (default: 'Test Tutor').
        --latitude (float): The latitude coordinate for the attendance location (default: 0.0).
        --longitude (float): The longitude coordinate for the attendance location (default: 0.0).
        --date_at (str): The date of the attendance in YYYY-MM-DD format (default: today's date).

    How it works:
        1. Parses the required and optional arguments.
        2. Validates the `photo_path` to ensure the file exists at the specified location.
        3. Validates and converts the `date_at` parameter to a date object, ensuring it follows the YYYY-MM-DD format.
        4. Retrieves the `Staff` object associated with the provided `pin`. If the staff member does not exist, the
           command exits with an error message.
        5. Creates a `LessonAttendance` record in the database with the specified attributes:
            - staff: The retrieved `Staff` instance.
            - subject_name: The specified subject name.
            - tutor_id: The tutor's ID.
            - tutor: The tutor's name.
            - first_in: The current timestamp when the command is run.
            - latitude: The specified latitude.
            - longitude: The specified longitude.
            - date_at: The specified date of attendance.
            - staff_image_path: The path to the photo file.

        If the record is successfully created, it outputs a success message along with the ID of the new `LessonAttendance`
        record. Otherwise, it logs any errors and outputs an error message.

    Example:
        To create a new lesson attendance record with a specific subject and tutor:

            python manage.py create_lesson_attendance "/path/to/photo.jpg" "1234" --subject_name "Mathematics" --tutor_id 5 --tutor "Mr. Smith" --latitude 51.509865 --longitude -0.118092 --date_at 2024-01-15

    """

    def add_arguments(self, parser):
        parser.add_argument("photo_path", type=str, help="Path to the photo file.")
        parser.add_argument(
            "pin", type=str, help="Staff PIN associated with the photo."
        )
        parser.add_argument(
            "--subject_name", type=str, default="Test Subject", help="Subject name."
        )
        parser.add_argument("--tutor_id", type=int, default=1, help="Tutor ID.")
        parser.add_argument(
            "--tutor", type=str, default="Test Tutor", help="Tutor name."
        )
        parser.add_argument("--latitude", type=float, default=0.0, help="Latitude.")
        parser.add_argument("--longitude", type=float, default=0.0, help="Longitude.")
        parser.add_argument(
            "--date_at",
            type=str,
            default=timezone.now().date().isoformat(),
            help="Date of the attendance in YYYY-MM-DD format.",
        )

    def handle(self, *args, **options):
        photo_path = options["photo_path"]
        pin = options["pin"]
        subject_name = options["subject_name"]
        tutor_id = options["tutor_id"]
        tutor = options["tutor"]
        latitude = options["latitude"]
        longitude = options["longitude"]
        date_at_str = options["date_at"]

        try:
            date_at = datetime.strptime(date_at_str, "%Y-%m-%d").date()
        except ValueError:
            self.stderr.write(self.style.ERROR("Invalid date format. Use YYYY-MM-DD."))
            return

        if not os.path.isfile(photo_path):
            self.stderr.write(self.style.ERROR(f"Photo file not found at {photo_path}"))
            return

        try:
            staff = Staff.objects.get(pin=pin)
        except ObjectDoesNotExist:
            self.stderr.write(self.style.ERROR(f"Staff with pin {pin} does not exist."))
            return

        try:
            attendance = LessonAttendance.objects.create(
                staff=staff,
                subject_name=subject_name,
                tutor_id=tutor_id,
                tutor=tutor,
                first_in=timezone.now(),
                latitude=latitude,
                longitude=longitude,
                date_at=date_at,
                staff_image_path=photo_path,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully created LessonAttendance with ID: {attendance.id}"
                )
            )
            logger.info(f"LessonAttendance created with ID: {attendance.id}")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error creating LessonAttendance: {e}"))
            logger.error(f"Error creating LessonAttendance: {e}", exc_info=True)
