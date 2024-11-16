import asyncio
import logging
from datetime import datetime
from urllib.parse import parse_qs

from django.conf import settings
from django.utils import timezone
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class PhotoConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        logger.info(f"WebSocket connection requested from {self.scope['client']}")
        try:
            query_string = self.scope["query_string"].decode()
            query_params = parse_qs(query_string)
            date = query_params.get("date", [timezone.now().date().isoformat()])[0]
            self.date = date
            logger.debug(f"Client requested date: {self.date}")

            self.group_name = f"photos_{self.date}"
            logger.debug(f"Joining group: {self.group_name}")

            await self.channel_layer.group_add(self.group_name, self.channel_name)

            await self.accept()
            logger.info(f"WebSocket connection accepted: {self.channel_name}")

            self.ping_task = asyncio.create_task(self.send_pings())
            logger.debug("Started ping task to keep the connection alive.")

            await self.send_photos_for_date(self.date)
        except Exception as e:
            logger.error(f"Error during WebSocket connection: {e}", exc_info=True)
            await self.close()

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected: {self.channel_name}, Code: {close_code}")
        if hasattr(self, "ping_task"):
            self.ping_task.cancel()
            logger.debug("Ping task cancelled.")

        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await super().disconnect(close_code)

    async def receive_json(self, content):
        logger.debug(f"Received message: {content}")
        try:
            if "date" in content:
                self.date = content["date"]
                self.group_name = f"photos_{self.date}"
                logger.debug(f"Switching to group: {self.group_name}")

                await self.channel_layer.group_add(self.group_name, self.channel_name)
                await self.send_photos_for_date(self.date)
        except Exception as e:
            logger.error(f"Error processing received message: {e}", exc_info=True)

    async def get_photos_for_date(self, date_str):
        try:
            from monitoring_app import models

            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            logger.debug(f"Fetching photos for date: {date}")

            attendances_qs = (
                models.LessonAttendance.objects.filter(date_at=date)
                .select_related("staff__department")
                .values(
                    "id",
                    "first_in",
                    "staff_image_path",
                    "tutor",
                    "tutor_id",
                    "staff__pin",
                    "staff__surname",
                    "staff__name",
                    "staff__department__name",
                )
            )

            photos = []
            from asgiref.sync import sync_to_async

            async_attendances_qs = await sync_to_async(list)(attendances_qs)

            for att in async_attendances_qs:
                staff_full_name = f"{att['staff__surname']} {att['staff__name']}"
                department = att["staff__department__name"] or "No Department"
                attendance_time = timezone.localtime(att["first_in"]).isoformat()
                photo_url = await self.get_image_url(att["staff_image_path"])

                photo_data = {
                    "staffPin": att["staff__pin"],
                    "staffFullName": staff_full_name,
                    "department": department,
                    "photoUrl": photo_url,
                    "attendanceTime": attendance_time,
                    "tutorInfo": f"{att['tutor']}",
                }
                photos.append(photo_data)

            logger.info(f"Retrieved {len(photos)} photos for date {date_str}")
            return photos
        except Exception as e:
            logger.error(f"Error fetching photos for date {date_str}: {e}", exc_info=True)
            return []

    async def send_photos_for_date(self, date_str):
        try:
            photos = await self.get_photos_for_date(date_str)
            await self.send_json(
                {
                    "date": date_str,
                    "photos": photos,
                }
            )
            logger.debug(f"Sent photos for date {date_str}")
        except Exception as e:
            logger.error(f"Error sending photos for date {date_str}: {e}", exc_info=True)

    async def new_photo(self, event):
        logger.debug(f"Received new photo event: {event}")
        try:
            attendance_id = event.get("attendance_id")
            attendance_data = await self.get_attendance_data_by_id(attendance_id)

            if attendance_data:
                staff_full_name = f"{attendance_data['staff__surname']} {attendance_data['staff__name']}"
                department = attendance_data["staff__department__name"] or "No Department"
                attendance_time = timezone.localtime(attendance_data["first_in"]).isoformat()
                photo_url = await self.get_image_url(attendance_data["staff_image_path"])

                photo_data = {
                    "staffPin": attendance_data["staff__pin"],
                    "staffFullName": staff_full_name,
                    "department": department,
                    "photoUrl": photo_url,
                    "attendanceTime": attendance_time,
                    "tutorInfo": f"{attendance_data['tutor']}",
                }

                await self.send_json({"newPhoto": photo_data})
                logger.info(f"Sent new photo to client: {attendance_data['staff__pin']}")
            else:
                logger.warning(f"Attendance with ID {attendance_id} not found.")
        except Exception as e:
            logger.error(f"Error sending new photo: {e}", exc_info=True)

    async def get_attendance_data_by_id(self, attendance_id):
        try:
            from monitoring_app import models

            attendances_qs = (
                models.LessonAttendance.objects.filter(id=attendance_id)
                .select_related("staff__department")
                .values(
                    "id",
                    "first_in",
                    "staff_image_path",
                    "tutor",
                    "tutor_id",
                    "staff__pin",
                    "staff__surname",
                    "staff__name",
                    "staff__department__name",
                )
            )
            from asgiref.sync import sync_to_async

            attendance_data = await sync_to_async(attendances_qs.first)()
            return attendance_data
        except models.LessonAttendance.DoesNotExist:
            return None

    async def get_image_url(self, staff_image_path):
        if staff_image_path:
            if staff_image_path.startswith(str(settings.ATTENDANCE_ROOT)):
                relative_path = staff_image_path.replace(str(settings.ATTENDANCE_ROOT), "")
                return f"{settings.ATTENDANCE_URL}{relative_path}".replace("//", "/")
            return f"{settings.MEDIA_URL}{staff_image_path.split('media/')[-1]}".replace("//", "/")
        return "/static/media/images/no-avatar.png"

    async def send_pings(self):
        """Sends periodic ping messages to keep the WebSocket connection alive."""
        logger.debug("Ping task started.")
        try:
            while True:
                await asyncio.sleep(120)
                await self.send_json({"type": "ping"})
                logger.debug("Sent ping to client.")
        except asyncio.CancelledError:
            logger.debug("Ping task cancelled.")
        except Exception as e:
            logger.error(f"Error in ping task: {e}", exc_info=True)
