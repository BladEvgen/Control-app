from datetime import datetime
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from django.utils import timezone
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from monitoring_app.views import get_staff_detail
from rest_framework.authtoken.models import Token
from monitoring_app.models import Staff, RemoteWork, LessonAttendance, APIKey


# Unit Test for RemoteWorkAdmin
class RemoteWorkAdminTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name="John", surname="Doe")
        self.remote_work = RemoteWork.objects.create(
            staff=self.staff, permanent_remote=True
        )

    def test_get_remote_status(self):
        self.assertEqual(
            self.remote_work.get_remote_status(), "Постоянная дистанционная работа"
        )


# Integration Test for get_staff_detail
class StaffDetailTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name="John", surname="Doe")

    def test_get_staff_detail(self):
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)
        detail = get_staff_detail(self.staff, start_date, end_date)
        self.assertIn("contract_type", detail)
        self.assertIn("salary", detail)


# API Test for check_lesson_task_status
class LessonTaskStatusTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.staff = Staff.objects.create(name="John", surname="Doe", pin="st1234")
        self.lesson_attendance = LessonAttendance.objects.create(
            staff=self.staff,
            tutor_id=1,
            first_in=timezone.now(),
            latitude=43.207674,
            longitude=76.851377,
        )
        self.task_id = "some-task-id"
        self.api_key = APIKey.objects.create(key_name="Test Key", created_by=self.user)
        self.token = Token.objects.create(user=self.user)

    def test_check_lesson_task_status(self):
        url = reverse("check_lesson_task_status", args=[self.task_id])
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)
        response = self.client.get(url)
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_202_ACCEPTED]
        )
        if response.status_code == status.HTTP_200_OK:
            self.assertIn("status", response.data)
        elif response.status_code == status.HTTP_202_ACCEPTED:
            self.assertIn("message", response.data)
