"""Теги шаблона админки для StaffAttendance (группировка строк по date_at)."""

from django import template
from unfold.templatetags import unfold_list

from monitoring_app.services import attendance_day

register = template.Library()


def _day_label(date_at) -> str:
    if not date_at:
        return "—"
    shift = attendance_day.event_day(date_at)
    return f"Смена {shift:%d.%m.%Y} · запись в БД {date_at:%d.%m.%Y}"


@register.inclusion_tag(
    "admin/monitoring_app/staffattendance/change_list_results_grouped.html", takes_context=True
)
def staffattendance_grouped_result_list(context, cl):
    """Таблица changelist unfold с разделителем перед каждой новой датой выгрузки."""
    ctx = unfold_list.result_list(context, cl)
    rows, prev = [], object()
    for record, row in zip(cl.result_list, ctx["results"]):
        label = None if record.date_at == prev else _day_label(record.date_at)
        prev = record.date_at
        rows.append((label, row))
    ctx["grouped_rows"] = rows
    return ctx
