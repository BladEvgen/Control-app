"""Исправляет записи, где после 0021 уход оказался раньше прихода.

Причина: в режиме «только турникеты» приход и уход — одно событие; приходу вернулись
секунды из старой колонки, а уходу нет (area_sequence хранит HH:MM). Уход = приход.
"""

from datetime import datetime

from django.db import migrations
from django.db.models import F


def fix(apps, schema_editor):
    from django.utils import timezone

    model = apps.get_model("monitoring_app", "StaffAttendance")
    rows = list(
        model.objects.filter(last_out__lt=F("first_in")).only(
            "id", "first_in", "last_out", "report_variants"
        )
    )
    for row in rows:
        row.last_out = row.first_in
        for variant in (row.report_variants or {}).values():
            first_in, last_out = variant.get("first_in"), variant.get("last_out")
            if first_in and last_out:
                first_dt = datetime.fromisoformat(first_in)
                if datetime.fromisoformat(last_out) < first_dt:
                    variant["last_out"] = timezone.localtime(first_dt).isoformat()
    model.objects.bulk_update(rows, ["last_out", "report_variants"], batch_size=1000)
    print(f"\n  fixed last_out < first_in: {len(rows)}")


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring_app", "0021_rebuild_attendance_report"),
    ]

    operations = [
        migrations.RunPython(fix, migrations.RunPython.noop),
    ]
