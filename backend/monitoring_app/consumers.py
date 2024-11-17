import logging
from datetime import datetime
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class PhotoConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query_params = self.scope["query_string"].decode()
        params = dict(
            param.split("=") for param in query_params.split("&") if "=" in param
        )
        date_str = params.get("date")
        if date_str:
            try:
                self.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                self.date = timezone.now().date()
        else:
            self.date = timezone.now().date()

        self.group_name = f"photos_{self.date}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()
        photos = await self.get_photos_for_date(self.date)
        await self.send_json({"type": "initial_photos", "photos": photos})

        logger.info(f"Client connected and joined group {self.group_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"Client disconnected and left group {self.group_name}")

    async def receive_json(self, content, **kwargs):
        if "type" in content:
            if content["type"] == "ping":
                await self.send_json({"type": "pong"})
                logger.info("Received ping, sent pong")
                return

        if "date" in content:
            new_date_str = content["date"]
            try:
                new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            except ValueError:
                await self.send_json({"error": "Invalid date format"})
                return

            await self.channel_layer.group_discard(self.group_name, self.channel_name)

            self.group_name = f"photos_{new_date}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)

            self.date = new_date

            photos = await self.get_photos_for_date(self.date)
            await self.send_json({"type": "initial_photos", "photos": photos})

            logger.info(f"Client switched to group {self.group_name}")

    @sync_to_async
    def get_photos_for_date(self, date):
        from monitoring_app import models
        attendance_records = models.LessonAttendance.objects.filter(
            date_at=date
        ).select_related("staff__department")
        photos = []
        for record in attendance_records:
            photos.append(
                {
                    "staffPin": record.staff.pin,
                    "staffFullName": f"{record.staff.surname} {record.staff.name}",
                    "department": (
                        record.staff.department.name
                        if record.staff.department
                        else "Unknown"
                    ),
                    "photoUrl": record.image_url,
                    "attendanceTime": timezone.localtime(record.first_in).isoformat(),
                    "tutorInfo": record.tutor_info,
                }
            )
        return photos

    async def new_photo(self, event):
        attendance_id = event["attendance_id"]
        photo_data = await self.get_photo_data(attendance_id)
        if photo_data:
            await self.send_json({"type": "new_photo", "newPhoto": photo_data})

    @sync_to_async
    def get_photo_data(self, attendance_id):
        from monitoring_app import models
        try:
            record = models.LessonAttendance.objects.select_related("staff__department").get(
                id=attendance_id
            )
            return {
                "staffPin": record.staff.pin,
                "staffFullName": f"{record.staff.surname} {record.staff.name}",
                "department": (
                    record.staff.department.name
                    if record.staff.department
                    else "Unknown"
                ),
                "photoUrl": record.image_url,
                "attendanceTime": timezone.localtime(record.first_in).isoformat(),
                "tutorInfo": record.tutor_info,
            }
        except models.LessonAttendance.DoesNotExist:
            logger.error(f"models.LessonAttendance with id {attendance_id} does not exist")
            return None
