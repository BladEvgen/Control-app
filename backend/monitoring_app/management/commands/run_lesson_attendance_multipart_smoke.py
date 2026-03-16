import json
import os
import time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from monitoring_app.models import APIKey, LessonAttendance, Staff

User = get_user_model()

_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c \x24.\' \",#\x1c\x1c(7),0144\x1f\';=82<.32"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
    b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?"
    b"\x00{\x1f+\x0f\xf0\xff\xd9"
)


class Command(BaseCommand):
    help = (
        "Runs live DB smoke flow via API views: "
        "POST /api/lesson_attendance/ (multipart, no image) -> "
        "GET task_status -> PUT /api/lesson_attendance/<id>/ (multipart image)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--staff-pin", default="T861T")
        parser.add_argument("--subject-name", default="Matrix 101: Красная таблетка")
        parser.add_argument("--tutor", default="Морфеус")
        parser.add_argument("--tutor-id", type=int, default=101)
        parser.add_argument("--latitude", type=float, default=43.26498756460276)
        parser.add_argument("--longitude", type=float, default=76.93992733955383)
        parser.add_argument("--poll-tries", type=int, default=20)
        parser.add_argument("--poll-sleep", type=float, default=0.3)
        parser.add_argument(
            "--pre-put-sleep",
            type=float,
            default=2.5,
            help="Sleep in seconds between successful task_status and PUT update.",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Delete created LessonAttendance row and saved photo after success.",
        )
        parser.add_argument(
            "--skip-put",
            action="store_true",
            help="Stop after POST/GET and do not upload photo via PUT.",
        )

    def _load_photo_bytes(self, staff: Staff) -> bytes:
        if staff.avatar:
            try:
                with staff.avatar.open("rb") as src:
                    content = src.read()
                    if content:
                        return content
            except Exception:
                pass
        fixture = Path(__file__).resolve().parents[2] / "fixtures" / "test_photo.jpg"
        if fixture.exists():
            return fixture.read_bytes()
        return _MINIMAL_JPEG

    def handle(self, *args, **options):
        staff_pin = options["staff_pin"]
        subject_name = options["subject_name"]
        tutor = options["tutor"]
        tutor_id = options["tutor_id"]
        latitude = options["latitude"]
        longitude = options["longitude"]
        poll_tries = options["poll_tries"]
        poll_sleep = options["poll_sleep"]
        pre_put_sleep = options["pre_put_sleep"]
        cleanup = options["cleanup"]
        skip_put = options["skip_put"]
        if pre_put_sleep < 0:
            raise CommandError("--pre-put-sleep cannot be negative")
        if cleanup and skip_put:
            raise CommandError("--cleanup cannot be used together with --skip-put")

        user = User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
        if not user:
            raise CommandError("No active staff user found (is_staff=True, is_active=True).")

        api_key_obj = (
            APIKey.objects.filter(is_active=True, created_by=user).order_by("id").first()
            or APIKey.objects.filter(is_active=True).order_by("id").first()
        )
        if not api_key_obj:
            raise CommandError("No active APIKey found.")

        staff = Staff.objects.filter(pin__iexact=staff_pin).first()
        if not staff:
            raise CommandError(f"Staff with pin={staff_pin} not found.")

        photo_bytes = self._load_photo_bytes(staff)
        if not photo_bytes:
            raise CommandError("Could not load photo bytes from staff avatar/fixture.")

        client = APIClient()
        client.credentials(HTTP_X_API_KEY=api_key_obj.key)

        attendance_payload = [
            {
                "staff_pin": staff.pin,
                "subject_name": subject_name,
                "tutor_id": tutor_id,
                "tutor": tutor,
                "first_in": timezone.now().isoformat(),
                "latitude": latitude,
                "longitude": longitude,
            }
        ]

        create_resp = client.post(
            reverse("create_lesson_attendance"),
            {"attendance_data": json.dumps(attendance_payload, ensure_ascii=False)},
            format="multipart",
        )
        if create_resp.status_code != status.HTTP_202_ACCEPTED:
            raise CommandError(
                f"POST create failed: {create_resp.status_code} {getattr(create_resp, 'data', None)}"
            )

        task_id = create_resp.data.get("task_id")
        if not task_id:
            raise CommandError(f"POST create returned no task_id: {create_resp.data}")

        task_status_url = reverse("check_lesson_task_status", kwargs={"task_id": task_id})
        status_resp = None
        for _ in range(poll_tries):
            status_resp = client.get(task_status_url)
            if (
                status_resp.status_code == status.HTTP_200_OK
                and status_resp.data.get("status") == "Success"
            ):
                break
            if status_resp.status_code == status.HTTP_202_ACCEPTED:
                time.sleep(poll_sleep)
                continue
            raise CommandError(
                f"GET task_status failed: {status_resp.status_code} {status_resp.data}"
            )
        else:
            raise CommandError(
                f"Task {task_id} did not reach Success in time. Last={getattr(status_resp, 'data', None)}"
            )

        lesson_ids = status_resp.data.get("lesson_ids") or []
        if not lesson_ids or "id" not in lesson_ids[0]:
            raise CommandError(f"No lesson id in task result: {status_resp.data}")
        lesson_id = int(lesson_ids[0]["id"])
        if skip_put:
            self.stdout.write(
                self.style.WARNING(
                    f"SKIPPED PUT: lesson_id={lesson_id} task_id={task_id}. "
                    "Запись создана без фото."
                )
            )
            return
        if pre_put_sleep > 0:
            self.stdout.write(
                f"Waiting {pre_put_sleep:.1f}s before PUT for lesson_id={lesson_id}..."
            )
            time.sleep(pre_put_sleep)

        put_resp = client.put(
            reverse("update_lesson_attendance", kwargs={"id": lesson_id}),
            {
                "image": SimpleUploadedFile(
                    "t861t.jpg",
                    photo_bytes,
                    content_type="image/jpeg",
                )
            },
            format="multipart",
        )
        if put_resp.status_code != status.HTTP_200_OK:
            raise CommandError(
                f"PUT update failed: {put_resp.status_code} {getattr(put_resp, 'data', None)}"
            )

        record = LessonAttendance.objects.get(id=lesson_id)
        if not record.staff_image_path:
            raise CommandError(
                f"PUT returned 200 but staff_image_path is empty for lesson_id={lesson_id}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"OK lesson_id={lesson_id} task_id={task_id} image_path={record.staff_image_path}"
            )
        )

        if cleanup:
            image_path = record.staff_image_path
            record.delete()
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
            self.stdout.write(self.style.WARNING("Cleanup done: created row deleted."))
