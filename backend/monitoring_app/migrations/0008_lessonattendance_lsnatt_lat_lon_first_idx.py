# Generated for attendance_stats query optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring_app", "0007_lessonattendance_lsnatt_date_first_idx_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="lessonattendance",
            index=models.Index(
                fields=["latitude", "longitude", "first_in"],
                name="lsnatt_lat_lon_first_idx",
            ),
        ),
    ]
