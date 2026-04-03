"""Теги шаблона админки для StaffAttendance (группировка строк по date_at)."""

from datetime import timedelta

from django import template
from django.contrib.admin.templatetags.admin_list import (
    items_for_result,
    result_headers,
    result_list as build_result_list_context,
)
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def staffattendance_grouped_tbody(cl):
    """Строки таблицы changelist с разделителями по дате выгрузки (date_at)."""
    headers = list(result_headers(cl))
    ncol = len(headers)
    parts: list[str] = []
    prev_date = object()
    row_idx = 0
    for res in cl.result_list:
        if getattr(res, "date_at", None) != prev_date:
            prev_date = res.date_at
            if res.date_at:
                shift = res.date_at - timedelta(days=1)
                label = (
                    f"Смена {shift.strftime('%d.%m.%Y')} · запись в БД "
                    f"{res.date_at.strftime('%d.%m.%Y')}"
                )
            else:
                label = "—"
            parts.append(
                f'<tr class="staffatt-day-divider grp-row">'
                f'<td colspan="{ncol}" class="staffatt-day-divider__cell">'
                f"{escape(label)}</td></tr>"
            )
        cells = items_for_result(cl, res, None)
        parity = "grp-row-even" if row_idx % 2 == 0 else "grp-row-odd"
        row_idx += 1
        parts.append(
            f'<tr class="grp-row {parity}">' + "".join(str(c) for c in cells) + "</tr>"
        )
    return mark_safe("".join(parts))


@register.inclusion_tag("admin/monitoring_app/staffattendance/change_list_results_grouped.html")
def staffattendance_grouped_result_list(cl):
    """Таблица changelist как у Django admin, но tbody с группами по date_at."""
    return build_result_list_context(cl)
