import re
import datetime
import requests

from django.conf import settings
from monitoring_app import models
from concurrent.futures import ThreadPoolExecutor


def get_attendance(pin: str):
    session = requests.Session()

    prev_date = datetime.datetime.now() - datetime.timedelta(days=10)
    eventTime_first = prev_date.strftime("%Y-%m-%d 00:00:00")
    eventTime_last = prev_date.strftime("%Y-%m-%d 23:59:59")
    access_token = settings.API_KEY

    try:
        params = {
            "endDate": eventTime_last,
            "pageNo": "1",
            "pageSize": "1000",
            "personPin": pin,
            "startDate": eventTime_first,
            "access_token": access_token,
        }
        response = session.get(
            settings.API_URL + "/api/transaction/listAttTransaction",
            params=params,
        )
        response.raise_for_status()
        response_json = response.json()
        data: list = response_json.get("data", [])
        staff = models.Staff.objects.get(pin=pin)

        if data:
            first_event_time = data[-1]["eventTime"]

            if len(data) == 1:
                last_event_time = first_event_time
            else:
                last_event_time = data[0]["eventTime"]

            staff_attendance = models.StaffAttendance.objects.create(staff=staff)

            if staff_attendance:
                staff_attendance.first_in = first_event_time
                staff_attendance.last_out = last_event_time
                staff_attendance.date_at = prev_date + datetime.timedelta(
                    days=1
                )  #! Debug  fill with test data
                staff_attendance.save()
        else:
            staff_attendance: models.StaffAttendance = (
                models.StaffAttendance.objects.create(staff=staff)
            )
            if staff_attendance:
                staff_attendance.save()
    except Exception as e:
        print(f"Error, Pin: {pin}, Error: {e}")


def get_all_attendance():
    pins = models.Staff.objects.values_list("pin", flat=True)
    with ThreadPoolExecutor(max_workers=6) as executor:
        executor.map(get_attendance, pins)


def password_check(password: str) -> bool:
    """
    Checks if a password meets the system's complexity requirements.

    This function validates a password string based on the following criteria:

    - Minimum length of 8 characters
    - Contains at least one uppercase letter (A-Z)
    - Contains at least one lowercase letter (a-z)
    - Contains at least one digit (0-9)
    - Contains at least one special character from the following set: #?!@$%^&*-

    Args:
        password (str): The password string to be validated.

    Returns:
        bool: True if the password meets all complexity requirements, False otherwise.
    """
    return bool(
        re.match(
            r"^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$", password
        )
    )
