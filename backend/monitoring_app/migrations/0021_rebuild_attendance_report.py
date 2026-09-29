"""Досчитывает report_variants для старых записей StaffAttendance из area_sequence и переписывает
отчётные колонки по исправленной логике в режиме AttendanceSettings. Без обращения к API.

area_sequence хранит только HH:MM: секунды берутся из старых колонок, если минута совпала;
если приход и уход одно событие, уход не раньше прихода. Неатомарная коммитит пачками.
"""

from datetime import timedelta

from django.db import migrations

BATCH = 1000


def _events_from_sequence(sequence, work_day):
    day = work_day.isoformat()
    return [
        {"eventTime": f"{day}T{item['t']}:00", "areaName": item.get("area"), "devSn": item.get("devSn")}
        for item in sequence
        if item.get("t")
    ]


def _keep_stored_seconds(variant, row):
    for field in ("first_in", "last_out"):
        stored = getattr(row, field)
        if variant[field] and stored and stored.replace(second=0, microsecond=0) == variant[field]:
            variant[field] = stored
    if variant["first_in"] and variant["last_out"] and variant["last_out"] < variant["first_in"]:
        variant["last_out"] = variant["first_in"]
    return variant


def rebuild(apps, schema_editor):
    from monitoring_app.attendance_fetcher import (
        REPORT_FIELDS,
        DeviceRules,
        compute_day,
        variant_from_json,
        variant_to_json,
    )

    model = apps.get_model("monitoring_app", "StaffAttendance")
    settings_row = apps.get_model("monitoring_app", "AttendanceSettings").objects.first()
    mode = "all" if settings_row and not settings_row.turnstile_only else "turnstile"
    rules = DeviceRules.from_settings()
    fields = [*REPORT_FIELDS, "report_variants", "area_sequence"]
    pending, done = [], 0

    qs = (
        model.objects.filter(report_variants__isnull=True)
        .exclude(area_sequence__isnull=True)
        .only("id", "date_at", "area_sequence", "report_variants", *REPORT_FIELDS)
    )
    for row in qs.iterator(chunk_size=BATCH):
        day = compute_day(
            _events_from_sequence(row.area_sequence, row.date_at - timedelta(days=1)), rules
        )
        row.report_variants = {
            m: variant_to_json(_keep_stored_seconds(v, row)) for m, v in day.variants.items()
        }
        row.area_sequence = day.area_sequence
        for field, value in variant_from_json(row.report_variants[mode]).items():
            setattr(row, field, value)
        pending.append(row)
        if len(pending) >= BATCH:
            model.objects.bulk_update(pending, fields)
            done += len(pending)
            pending.clear()
    if pending:
        model.objects.bulk_update(pending, fields)
        done += len(pending)
    print(f"\n  backfilled report_variants (mode={mode}): {done}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("monitoring_app", "0020_attendance_report_mode"),
    ]

    operations = [
        migrations.RunPython(rebuild, migrations.RunPython.noop),
    ]
