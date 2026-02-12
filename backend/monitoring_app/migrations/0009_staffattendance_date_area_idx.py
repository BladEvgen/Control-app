# Generated for StaffAttendance changelist filter optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring_app", "0008_lessonattendance_lsnatt_lat_lon_first_idx"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="staffattendance",
            index=models.Index(
                fields=["date_at", "area_name_in", "area_name_out"],
                name="stfatt_date_area_idx",
            ),
        ),
    ]
