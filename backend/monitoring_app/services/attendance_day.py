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

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from monitoring_app import models, utils

logger = logging.getLogger(__name__)

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


DAY_NORM_MINUTES = 8 * 60


def remote_credit_by_day(
    remote_works: Iterable["models.RemoteWork"], start: datetime.date, end: datetime.date
) -> dict:
    """{рабочий день: % нормы, зачитываемый без СКУД} для дней [start, end] под удалёнкой.

    Пересекающиеся периоды не суммируются: берётся наибольший процент.
    """
    out: dict = {}
    works = list(remote_works)
    day = start
    while day <= end:
        shares = [rw.credit_percent for rw in works if rw.covers(day)]
        if shares:
            out[day] = max(shares)
        day += datetime.timedelta(days=1)
    return out


def remote_credit_minutes(
    verified_minutes: float, credit_percent: int, norm: float = DAY_NORM_MINUTES
) -> float:
    """Минуты, зачтённые за удалённую работу, которую терминалы не видят.

    Подтверждённое СКУД время остаётся как есть; удалённо добирается только разрыв
    до нормы и не больше credit_percent нормы. Пришёл на 4 ч при 100% → +4 ч,
    отработал в здании 9 ч → +0, не пришёл при 50% → +4 ч.
    """
    return max(0.0, min(norm * credit_percent / 100, norm - verified_minutes))


ACTIVITY_SESSION_GAP = datetime.timedelta(minutes=15)


def record_interval(
    staff_id: int, start: datetime.datetime, end: datetime.datetime, source: str
) -> None:
    """Добавляет интервал цифровой явки, склеивая сеансы с паузой ≤ ACTIVITY_SESSION_GAP.

    Интервал через полночь делится по локальным дням. Хранится как [начало, конец, источник].
    """
    start, end = min(start, end), max(start, end)
    while True:
        day = timezone.localdate(start)
        next_midnight = timezone.make_aware(
            datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min)
        )
        piece_end = min(end, next_midnight)
        _merge_into_day(staff_id, day, start, piece_end, source)
        if end <= next_midnight:
            return
        start = next_midnight


def _merge_into_day(staff_id, day, start, end, source) -> None:
    with transaction.atomic():
        row, _ = models.RemoteActivityDay.objects.select_for_update().get_or_create(
            staff_id=staff_id, day=day
        )
        spans = [
            (
                datetime.datetime.fromisoformat(s),
                datetime.datetime.fromisoformat(e),
                rest[0] if rest else "web",
            )
            for s, e, *rest in row.intervals
        ]
        spans.append((start, end, source))
        spans.sort()
        merged: list[tuple[datetime.datetime, datetime.datetime, str]] = [spans[0]]
        for s, e, src in spans[1:]:
            last_s, last_e, last_src = merged[-1]
            if s - last_e <= ACTIVITY_SESSION_GAP:
                sources = last_src if src in last_src.split("+") else f"{last_src}+{src}"
                merged[-1] = (last_s, max(last_e, e), sources)
            else:
                merged.append((s, e, src))
        row.intervals = [[s.isoformat(), e.isoformat(), src] for s, e, src in merged]
        row.active_seconds = int(sum((e - s).total_seconds() for s, e, _ in merged))
        row.save(update_fields=["intervals", "active_seconds"])


def record_activity(staff_id: int, now: datetime.datetime, source: str = "web") -> None:
    """Точечная отметка «пользователь что-то сделал» — продлевает текущий сеанс."""
    record_interval(staff_id, now, now, source)


TOUCH_TICK_SECONDS = 60
STAFF_LOOKUP_TTL = 300


def touch_activity(user, source: str) -> None:
    """Отметка активности учётной записи: не чаще раза в минуту, только для сотрудника."""
    from django.core.cache import cache

    if not cache.add(f"activity_tick:{user.pk}", 1, TOUCH_TICK_SECONDS):
        return
    staff_id = cache.get(f"activity_staff:{user.pk}")
    if staff_id is None:
        staff_id = staff_id_for_user(user)
        cache.set(f"activity_staff:{user.pk}", staff_id, STAFF_LOOKUP_TTL)
    if staff_id:
        record_activity(staff_id, timezone.now(), source)


_TRANSLIT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "ә": "a",
        "ғ": "g",
        "қ": "k",
        "ң": "n",
        "ө": "o",
        "ұ": "u",
        "ү": "u",
        "һ": "h",
        "і": "i",
    }
)


def _latin(value: Optional[str]) -> str:
    return (value or "").strip().lower().translate(_TRANSLIT)


def staff_id_for_user(user) -> int:
    """Сотрудник учётной записи; без ручной привязки — автопривязка дистанционщика.

    Автопривязка: среди сотрудников с удалёнкой и без учётной записи ровно один, чьи
    фамилия и имя (латиницей) есть в логине/ФИО/почте пользователя. Связь сохраняется
    в Staff.user — её видно и можно исправить в админке. Ноль совпадений или больше
    одного — ничего не связываем: лучше не засчитать, чем засчитать чужому.
    """
    linked = models.Staff.all_objects.filter(user_id=user.pk).values_list("id", flat=True).first()
    if linked:
        return linked
    account = " ".join(
        _latin(getattr(user, field, ""))
        for field in ("username", "first_name", "last_name", "email")
    )
    matches = [
        staff_id
        for staff_id, name, surname in models.Staff.all_objects.filter(
            user__isnull=True, remote_work__isnull=False
        )
        .distinct()
        .values_list("id", "name", "surname")
        if _latin(name)
        and _latin(surname)
        and _latin(name) in account
        and _latin(surname) in account
    ]
    if len(matches) != 1:
        return 0
    models.Staff.all_objects.filter(id=matches[0], user__isnull=True).update(user=user)
    logger.info("Auto-linked user_id=%s to staff_id=%s for digital presence", user.pk, matches[0])
    return matches[0]


def activity_intervals(staff_ids: Iterable[int], start: datetime.date, end: datetime.date) -> dict:
    """{(staff_id, день): [(начало, конец), ...]} цифровой явки за период. Один запрос."""
    out: dict = {}
    for staff_id, day, spans in models.RemoteActivityDay.objects.filter(
        staff_id__in=list(staff_ids), day__range=(start, end)
    ).values_list("staff_id", "day", "intervals"):
        out[(staff_id, day)] = [
            (datetime.datetime.fromisoformat(s), datetime.datetime.fromisoformat(e))
            for s, e, *_ in spans
        ]
    return out


def activity_beyond_office_seconds(office: list, digital: list) -> int:
    """Секунды цифровой явки вне интервалов СКУД: работа в системе из офиса не считается дважды."""
    if not digital:
        return 0
    return utils.merge_work_intervals_to_total_seconds(
        office + digital
    ) - utils.merge_work_intervals_to_total_seconds(office)


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
        effective_work_seconds, area_sequence, turnstile_missing ("in" / "out" / None —
        какой отметки нет). O(r) для строк из load_days.
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

    sa_intervals = (
        parse_intervals(sa_records[0].get("effective_work_intervals")) if sa_records else []
    )
    intervals = list(sa_intervals)
    for la in la_records:
        fi, lo = la.get("first_in"), la.get("last_out")
        if fi is not None and lo is not None and lo > fi:
            intervals.append((fi, lo))
    total = utils.merge_work_intervals_to_total_seconds(intervals)
    if not sa_intervals and sa_records and sa_records[0].get("effective_work_seconds"):
        total = max(total, sa_records[0]["effective_work_seconds"])
    combined["effective_work_seconds"] = total or None
    if not intervals and combined["first_in"] and combined["last_out"]:
        if combined["last_out"] > combined["first_in"]:
            intervals = [(combined["first_in"], combined["last_out"])]
    combined["work_intervals"] = intervals
    combined["turnstile_missing"] = (
        "out"
        if combined["first_in"] and not combined["last_out"]
        else "in" if combined["last_out"] and not combined["first_in"] else None
    )
    if "lesson_attendance" in (combined["first_in_source"], combined["last_out_source"]):
        combined["area_sequence"] = None
    return combined
