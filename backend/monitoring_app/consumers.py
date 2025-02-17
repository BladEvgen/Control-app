import logging
from datetime import datetime
from django.utils import timezone
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache

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

        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        logger.info(f"Client connected and joined group {self.group_name}")

        photos = await self.get_photos_for_date(self.date)
        await self.send_json({"type": "initial_photos", "photos": photos})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"Client disconnected and left group {self.group_name}")

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
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
        """
        Получаем список фотографий для заданной даты.
        Используем кэш, чтобы снизить нагрузку при повторных запросах.
        """
        cache_key = f"photos_for_{date}"
        photos = cache.get(cache_key)
        if photos is None:
            from monitoring_app import models

            qs = models.LessonAttendance.objects.filter(date_at=date).select_related(
                "staff__department"
            )
            photos = [
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
                for record in qs
            ]
            cache.set(cache_key, photos, timeout=5)
        return photos

    async def new_photo(self, event):
        """
        Обработчик события, которое должно приходить извне через channel_layer.group_send.
        Ожидается, что в event передаётся "attendance_id".
        """
        attendance_id = event.get("attendance_id")
        if not attendance_id:
            logger.error("attendance_id не найден в событии new_photo")
            return

        photo_data = await self.get_photo_data(attendance_id)
        if photo_data:
            await self.send_json({"type": "new_photo", "newPhoto": photo_data})
            logger.info("Sent new photo data to client.")

    @sync_to_async
    def get_photo_data(self, attendance_id):
        from monitoring_app import models

        try:
            record = models.LessonAttendance.objects.select_related(
                "staff__department"
            ).get(id=attendance_id)
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
            logger.error(f"LessonAttendance with id {attendance_id} does not exist")
            return None
