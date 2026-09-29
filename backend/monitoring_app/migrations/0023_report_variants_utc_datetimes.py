"""report_variants: first_in/last_out → 'YYYY-MM-DD HH:MM:SS' в UTC (как DATETIME в БД при USE_TZ).

Так смена режима отчёта — один UPDATE, переносящий значения из JSON в колонки без CAST.
Неатомарная, пачками; повторный запуск ничего не меняет.
"""

from datetime import datetime, timezone

from django.db import migrations

BATCH = 1000


def _to_utc_naive(value):
    if not value:
        return value
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return value
    return parsed.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def convert(apps, schema_editor):
    model = apps.get_model("monitoring_app", "StaffAttendance")
    pending, done = [], 0
    qs = model.objects.exclude(report_variants__isnull=True).only("id", "report_variants")
    for row in qs.iterator(chunk_size=BATCH):
        changed = False
        for variant in row.report_variants.values():
            for field in ("first_in", "last_out"):
                converted = _to_utc_naive(variant.get(field))
                if converted != variant.get(field):
                    variant[field] = converted
                    changed = True
        if changed:
            pending.append(row)
            if len(pending) >= BATCH:
                model.objects.bulk_update(pending, ["report_variants"])
                done += len(pending)
                pending.clear()
    if pending:
        model.objects.bulk_update(pending, ["report_variants"])
        done += len(pending)
    print(f"\n  report_variants converted to UTC: {done}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("monitoring_app", "0022_fix_same_event_last_out"),
    ]

    operations = [
        migrations.RunPython(convert, migrations.RunPython.noop),
    ]
