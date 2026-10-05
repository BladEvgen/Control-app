"""День посещаемости сотрудника: StaffAttendance + LessonAttendance в одном месте.

Даты:
    StaffAttendance.date_at — день выгрузки = рабочий день + 1 (строка за 02.10 лежит
    с date_at 03.10). LessonAttendance.date_at — сам день занятия. Сдвиг делают только
    sa_date_at() и event_day(); больше нигде «+ timedelta(days=1)» для SA не пишется.

Присутствие:
    SA-строка — присутствие, если есть first_in ИЛИ last_out (SA_PRESENT). В режиме
    «только турникеты» вход не через турникет даёт пустой first_in при заполненном last_out.

Сложность (R — строк за период, r — строк одного сотрудника за день):
    load_days — 2 запроса и O(R) группировка: каждую строку надо прочитать.
    merge_day — O(r): SA-строка за день одна (unique staff+date_at), её интервалы уже
    по времени; LA приходит отсортированной по first_in (индекс staff+first_in). Timsort
    в merge_work_intervals_to_total_seconds видит два готовых прогона и сливает их за O(r)
    вместо O(r log r).
"""

import datetime
import logging
from collections import defaultdict
from typing import Any, Iterable, List, Optional, Tuple

from django.db.models import Q

from monitoring_app import models, utils

logger = logging.getLogger("django")

SA_DAY_SHIFT = datetime.timedelta(days=1)
SA_PRESENT = Q(first_in__isnull=False) | Q(last_out__isnull=False)

SA_FIELDS = (
    "staff_id",
    "date_at",
    "first_in",
    "last_out",
    "area_name_in",
    "area_name_out",
    "effective_work_seconds",
    "area_sequence",
    "effective_work_intervals",
)
LA_FIELDS = (
    "staff_id",
    "date_at",
    "first_in",
    "last_out",
    "latitude",
    "longitude",
    "duration_seconds",
)


def to_date(value: Any) -> Optional[datetime.date]:
    """date/datetime → date (None → None)."""
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def sa_date_at(day: datetime.date) -> datetime.date:
    """StaffAttendance.date_at для рабочего дня day."""
    return day + SA_DAY_SHIFT


def event_day(date_at: datetime.date) -> datetime.date:
    """Рабочий день для StaffAttendance.date_at (колонка NOT NULL)."""
    return date_at - SA_DAY_SHIFT


def load_days(
    staff_ids: Iterable[int],
    date_from: datetime.date,
    date_to: datetime.date,
    *,
    sa_fields: Tuple[str, ...] = SA_FIELDS,
    la_fields: Tuple[str, ...] = LA_FIELDS,
) -> Tuple[dict, dict]:
    """SA и LA за рабочие дни [date_from, date_to], сгруппированные по рабочему дню.

    Args:
        staff_ids: id сотрудников.
        date_from: Первый рабочий день.
        date_to: Последний рабочий день (включительно).
        sa_fields: Поля StaffAttendance для .values() (должны включать date_at).
        la_fields: Поля LessonAttendance для .values() (должны включать date_at).

    Returns:
        (sa_by_day, la_by_day): {рабочий день: [строки .values()]}. LA без отбракованных
        дней (exclude_report_invalid_days), по возрастанию first_in. Два запроса, O(R).
    """
    staff_ids = list(staff_ids)
    sa_by_day: dict = defaultdict(list)
    for row in models.StaffAttendance.objects.filter(
        staff_id__in=staff_ids,
        date_at__range=(sa_date_at(date_from), sa_date_at(date_to)),
    ).values(*sa_fields):
        sa_by_day[event_day(row["date_at"])].append(row)

    la_by_day: dict = defaultdict(list)
    for row in (
        models.LessonAttendance.exclude_report_invalid_days(
            models.LessonAttendance.objects.filter(
                staff_id__in=staff_ids, date_at__range=(date_from, date_to)
            )
        )
        .order_by("first_in")
        .values(*la_fields)
    ):
        day = to_date(row["date_at"])
        if day is not None:
            la_by_day[day].append(row)
    return dict(sa_by_day), dict(la_by_day)


def resolve_la_location(lat, lon, location_searcher) -> Optional[str]:
    """Имя ближайшей ClassLocation для координат занятия.

    Returns:
        Имя локации или None, если координат/индекса нет.
    """
    if location_searcher is None or lat is None or lon is None:
        return None
    try:
        location = location_searcher.find_nearest_location(lat, lon, radius=float("inf"))
        return location["name"] if location is not None else None
    except Exception as e:
        logger.warning("Error resolving LA location: %s", e)
        return None


def parse_intervals(raw_intervals) -> List[Tuple[datetime.datetime, datetime.datetime]]:
    """effective_work_intervals из JSON → [(start, end)] с end > start; битые пропускаются."""
    intervals = []
    for raw in raw_intervals or []:
        try:
            s = raw.get("start") and datetime.datetime.fromisoformat(
                raw["start"].replace("Z", "+00:00")
            )
            e = raw.get("end") and datetime.datetime.fromisoformat(
                raw["end"].replace("Z", "+00:00")
            )
            if s is not None and e is not None and e > s:
                intervals.append((s, e))
        except (ValueError, TypeError, AttributeError):
            continue
    return intervals


def merge_day(sa_records, la_records, location_searcher=None) -> dict:
    """Сводит SA и LA одного сотрудника за один рабочий день.

    first_in — самый ранний из SA и LA, last_out — самый поздний; при равенстве
    побеждает SA. Эффективное время — объединение интервалов SA (effective_work_intervals)
    и LA (first_in–last_out) без двойного учёта. area_sequence (история СКУД) убирается,
    только если границу дня перебило занятие.

    Args:
        sa_records: Строки StaffAttendance дня (.values() с полями SA_FIELDS).
        la_records: Строки LessonAttendance дня (.values() с полями LA_FIELDS).
        location_searcher: Индекс локаций для имени места занятия или None.

    Returns:
        first_in, last_out (aware UTC или None), area_name_in/out, first_in_source,
        last_out_source ("staff_attendance" / "lesson_attendance" / None),
        effective_work_seconds, area_sequence. O(r) для строк из load_days.
    """
    combined: dict[str, Any] = {
        "first_in": None,
        "last_out": None,
        "area_name_in": None,
        "area_name_out": None,
        "first_in_source": None,
        "last_out_source": None,
        "effective_work_seconds": None,
        "area_sequence": sa_records[0].get("area_sequence") if sa_records else None,
    }
    for r in sa_records:
        if r.get("first_in") and (
            combined["first_in"] is None or r["first_in"] < combined["first_in"]
        ):
            combined["first_in"] = r["first_in"]
            combined["first_in_source"] = "staff_attendance"
            if r.get("area_name_in"):
                combined["area_name_in"] = (
                    utils.resolve_area_address(r["area_name_in"]) or r["area_name_in"]
                )
        if r.get("last_out") and (
            combined["last_out"] is None or r["last_out"] > combined["last_out"]
        ):
            combined["last_out"] = r["last_out"]
            combined["last_out_source"] = "staff_attendance"
            if r.get("area_name_out"):
                combined["area_name_out"] = (
                    utils.resolve_area_address(r["area_name_out"]) or r["area_name_out"]
                )

    earliest_la = min(
        (r for r in la_records if r.get("first_in")), key=lambda r: r["first_in"], default=None
    )
    latest_la = max(
        (r for r in la_records if r.get("last_out")), key=lambda r: r["last_out"], default=None
    )
    if earliest_la is not None and (
        combined["first_in"] is None or earliest_la["first_in"] < combined["first_in"]
    ):
        combined["first_in"] = earliest_la["first_in"]
        combined["first_in_source"] = "lesson_attendance"
        name = resolve_la_location(
            earliest_la.get("latitude"), earliest_la.get("longitude"), location_searcher
        )
        if name:
            combined["area_name_in"] = name
    if latest_la is not None and (
        combined["last_out"] is None or latest_la["last_out"] > combined["last_out"]
    ):
        combined["last_out"] = latest_la["last_out"]
        combined["last_out_source"] = "lesson_attendance"
        name = resolve_la_location(
            latest_la.get("latitude"), latest_la.get("longitude"), location_searcher
        )
        if name:
            combined["area_name_out"] = name

    intervals = parse_intervals(sa_records[0].get("effective_work_intervals")) if sa_records else []
    for la in la_records:
        fi, lo = la.get("first_in"), la.get("last_out")
        if fi is not None and lo is not None and lo > fi:
            intervals.append((fi, lo))
    total = utils.merge_work_intervals_to_total_seconds(intervals)
    combined["effective_work_seconds"] = total or None
    if "lesson_attendance" in (combined["first_in_source"], combined["last_out_source"]):
        combined["area_sequence"] = None
    return combined
