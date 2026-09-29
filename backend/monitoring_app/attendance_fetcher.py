"""Выгрузка событий СКУД и расчёт дневной посещаемости сотрудников (StaffAttendance).

Как работает:
    1. Рабочий день делится на часовые окна; каждое окно — один запрос к API СКУД без
       personPin (события всех сотрудников сразу). Если окно вернулось полным
       (PAGE_SIZE событий), оно делится пополам по секундам, пока не станет неполным.
       Пагинация API не используется: при равных eventTime порядок между страницами
       нестабилен, и события на стыках теряются или дублируются.
    2. События без дублей (по id) раскладываются одним проходом по корзинам
       (сотрудник, дата). Чужие PIN (студенты, гости) отбрасываются.
    3. Для каждой корзины compute_day:
        - сортирует события и схлопывает повторные проходы через одно устройство
          в пределах ATTENDANCE_REPEAT_TAP_SECONDS (двойное прикладывание карты);
        - обратным проходом запоминает для каждого события следующее другое устройство
          и ближайший повторный вход, затем за O(1) решает судьбу выхода: турникет выхода —
          выход; мост ЦОС — переход, если дальше турникет выхода или повторный вход
          в пределах grace, иначе выход;
        - считает интервалы «в здании» между входом и выходом и строит два варианта:
          "all" (все устройства) и "turnstile" (только турникеты; единственный проход
          через турникет даёт только приход или только уход — по его направлению);
        - собирает area_sequence — историю перемещений по всем устройствам.
    4. Строки пишутся одним upsert (INSERT … ON DUPLICATE KEY UPDATE). В отчётные колонки
       идёт вариант режима AttendanceSettings.turnstile_only, оба варианта сохраняются
       в report_variants. Смена режима — apply_report_mode(): один UPDATE внутри БД.
    5. Если API ответил ошибкой, кусок дней не пишется целиком (частичных дней не бывает).

Сложность (E — событий за период, N — сотрудников, R — записей, k — событий
сотрудника за день, P = 1000 — размер страницы API):
    - запросы к API: O(E / P) — около 50 на день (раньше O(N · дни) — 8 070 на день);
    - группировка: O(E); расчёт дня: O(k log k) на сортировку, остальное O(k);
      сотрудники без событий получают один общий пустой результат — O(1);
    - запись: O(R) одним upsert; счётчики created/updated — один SELECT ключей;
    - смена режима отчёта: O(R) одним UPDATE внутри БД, без передачи строк в Python;
    - память: O(событий одного куска chunk_days).
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from datetime import datetime as dt
from datetime import time, timedelta
from datetime import timezone as dt_timezone
from datetime import tzinfo
from operator import itemgetter
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
import backoff
from channels.db import database_sync_to_async
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Value
from django.db.models.fields.json import KT, KeyTransform
from django.db.models.functions import NullIf
from django.utils import timezone

from monitoring_app import models
from monitoring_app.cache_conf import invalidate_staff_attendance_caches

logger = logging.getLogger("django")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
    "sec-ch-ua-platform": '"Windows"',
}

SENSITIVE_QUERY_KEYS = {"access_token", "token", "api_key", "apikey"}
MAX_RESPONSE_BODY_PREVIEW_LEN = 300
API_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

REPORT_MODES = ("all", "turnstile")
REPORT_FIELDS = (
    "first_in",
    "last_out",
    "area_name_in",
    "area_name_out",
    "effective_work_seconds",
    "effective_work_intervals",
)
RESOLUTION_STAT_KEYS = (
    "ambiguous_exit_candidates",
    "ambiguous_resolved_as_exit",
    "ambiguous_resolved_as_transfer",
)

Event = Tuple[dt, str, str]


def _sanitize_url(raw_url: str) -> str:
    """Скрывает секреты в query-параметрах URL для логов.

    Args:
        raw_url: URL запроса, возможно с access_token.

    Returns:
        URL, где значения ключей из SENSITIVE_QUERY_KEYS заменены на "***";
        исходная строка, если URL не разобрать.
    """
    try:
        parsed_url = urlsplit(raw_url)
        redacted_query = urlencode(
            [
                (key, "***" if key.lower() in SENSITIVE_QUERY_KEYS else value)
                for key, value in parse_qsl(parsed_url.query, keep_blank_values=True)
            ],
            doseq=True,
        )
        return urlunsplit(parsed_url._replace(query=redacted_query))
    except Exception:
        return raw_url


def _shorten_payload(payload: str, max_len: int = MAX_RESPONSE_BODY_PREVIEW_LEN) -> str:
    """Сжимает тело ответа в одну строку ограниченной длины для логов.

    Args:
        payload: Тело ответа API.
        max_len: Максимальная длина результата без многоточия.

    Returns:
        Тело в одну строку, обрезанное до max_len символов с "..." при обрезке.
    """
    one_line_payload = " ".join((payload or "").split())
    if len(one_line_payload) <= max_len:
        return one_line_payload
    return f"{one_line_payload[:max_len]}..."


@dataclass(frozen=True)
class DeviceRules:
    """Классы устройств СКУД и пороги из настроек; собирается один раз на выгрузку.

    Attributes:
        exit: Устройства выхода (ATTENDANCE_EXIT_DEVICE_SNS).
        ambiguous_exit: Выходы, которые могут быть переходом (мост ЦОС).
        reentry: Устройства повторного входа, подтверждающие переход через мост.
        turnstile: Турникеты — единственный источник для режима «только турникеты».
        grace: Окно, в котором повторный вход превращает мост в переход.
        repeat_tap: Окно, в котором повторный проход через то же устройство
            считается повтором (двойное прикладывание карты), а не новым движением.
    """

    exit: frozenset
    ambiguous_exit: frozenset
    reentry: frozenset
    turnstile: frozenset
    grace: timedelta
    repeat_tap: timedelta

    @classmethod
    def from_settings(cls) -> "DeviceRules":
        """Собирает правила из django.conf.settings.

        Returns:
            DeviceRules с множествами devSn и порогами; некорректные числовые
            настройки заменяются значениями по умолчанию (45 мин и 120 с).
        """

        def non_negative_int(name: str, default: int) -> int:
            try:
                return max(0, int(getattr(settings, name, default)))
            except (TypeError, ValueError):
                return default

        return cls(
            exit=frozenset(getattr(settings, "ATTENDANCE_EXIT_DEVICE_SNS", ())),
            ambiguous_exit=frozenset(getattr(settings, "ATTENDANCE_AMBIGUOUS_EXIT_DEVICE_SNS", ())),
            reentry=frozenset(getattr(settings, "ATTENDANCE_REENTRY_DEVICE_SNS", ())),
            turnstile=frozenset(getattr(settings, "ATTENDANCE_TURNSTILE_DEVICE_SNS", ())),
            grace=timedelta(
                minutes=non_negative_int("ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES", 45)
            ),
            repeat_tap=timedelta(seconds=non_negative_int("ATTENDANCE_REPEAT_TAP_SECONDS", 120)),
        )


class DayResult(NamedTuple):
    """Итог дня по одному сотруднику.

    Attributes:
        variants: {"all": {...}, "turnstile": {...}} — поля REPORT_FIELDS,
            first_in/last_out — aware datetime или None.
        area_sequence: История перемещений по всем устройствам или None без событий.
        stats: Счётчики неоднозначных выходов (ключи RESOLUTION_STAT_KEYS).
        parse_errors: Число событий с нераспознанным eventTime.
    """

    variants: Dict[str, Dict[str, Any]]
    area_sequence: Optional[List[Dict[str, str]]]
    stats: Dict[str, int]
    parse_errors: int


def _zero_stats() -> Dict[str, int]:
    """Возвращает обнулённые счётчики неоднозначных выходов.

    Returns:
        Словарь {ключ из RESOLUTION_STAT_KEYS: 0}.
    """
    return {key: 0 for key in RESOLUTION_STAT_KEYS}


def _parse_events(events: Iterable[Dict[str, Any]], tz: tzinfo) -> Tuple[List[Event], int]:
    """Разбирает сырые события API и сортирует их по времени. O(k log k).

    Args:
        events: События API СКУД (eventTime, areaName, devSn).
        tz: Таймзона проекта: eventTime приходит в локальном времени без смещения.

    Returns:
        Кортеж (события (время, зона, devSn) по возрастанию времени,
        число событий с нераспознанным eventTime).
    """
    parsed: List[Event] = []
    errors = 0
    for ev in events:
        try:
            t = dt.fromisoformat(ev["eventTime"])
        except (ValueError, KeyError, TypeError):
            errors += 1
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=tz)
        area = (ev.get("areaName") or "").strip() or "Unknown"
        parsed.append((t, area, (ev.get("devSn") or "").strip()))
    parsed.sort(key=itemgetter(0))
    return parsed, errors


def _kept_indices(events: List[Event], repeat_tap: timedelta) -> List[int]:
    """Отбрасывает повторные проходы через одно устройство подряд. O(k).

    Двойное прикладывание карты к турникету (07:05:57 и 07:06:27) иначе читается
    как «вошёл и вышел», и весь остальной день выпадает из эффективного времени.

    Args:
        events: События дня по возрастанию времени.
        repeat_tap: Максимальный промежуток между повтором и предыдущим проходом.

    Returns:
        Индексы событий, которые участвуют в расчёте (повторы пропущены).
    """
    kept: List[int] = []
    for i, (t, _, sn) in enumerate(events):
        if kept:
            prev_t, _, prev_sn = events[kept[-1]]
            if sn == prev_sn and t - prev_t <= repeat_tap:
                continue
        kept.append(i)
    return kept


def _resolve_exits(events: List[Event], rules: DeviceRules, stats: Dict[str, int]) -> List[str]:
    """Определяет, какие события закрывают интервал «в здании». O(k).

    Первое событие дня — всегда приход. Неоднозначный выход (мост ЦОС) — переход, если
    следующее событие другого устройства — турникет выхода (выйти можно только изнутри)
    или в пределах grace есть событие на устройстве повторного входа.

    Args:
        events: События дня по возрастанию времени (без повторов).
        rules: Классы устройств и пороги.
        stats: Счётчики неоднозначных выходов; увеличиваются на месте.

    Returns:
        Для каждого события: "exit", "bridge_transfer" или "" (не выход).
    """
    n = len(events)
    next_other_sn: List[Optional[str]] = [None] * n
    next_reentry_t: List[Optional[dt]] = [None] * n
    for i in range(n - 2, -1, -1):
        nt, _, nsn = events[i + 1]
        next_other_sn[i] = nsn if nsn != events[i][2] else next_other_sn[i + 1]
        next_reentry_t[i] = nt if nsn in rules.reentry else next_reentry_t[i + 1]

    hard_exit = rules.exit - rules.ambiguous_exit
    resolutions = [""] * n
    for i in range(1, n):
        t, _, sn = events[i]
        if sn not in rules.exit:
            continue
        if sn not in rules.ambiguous_exit:
            resolutions[i] = "exit"
            continue
        stats["ambiguous_exit_candidates"] += 1
        reentry_t = next_reentry_t[i]
        if next_other_sn[i] in hard_exit or (
            reentry_t is not None and reentry_t - t <= rules.grace
        ):
            stats["ambiguous_resolved_as_transfer"] += 1
            resolutions[i] = "bridge_transfer"
        else:
            stats["ambiguous_resolved_as_exit"] += 1
            resolutions[i] = "exit"
    return resolutions


def _report(events: List[Event], resolutions: List[str]) -> Dict[str, Any]:
    """Считает отчётные поля дня по событиям одного варианта. O(k).

    Приход — первое событие, уход — последнее, эффективное время — сумма интервалов
    от входа до выхода (незакрытый интервал закрывается последним событием).

    Args:
        events: События варианта по возрастанию времени.
        resolutions: Результат _resolve_exits для этих же событий.

    Returns:
        Словарь с ключами REPORT_FIELDS; без событий — пустой день
        (first_in/last_out = None, зоны "Unknown").
    """
    if not events:
        return {
            "first_in": None,
            "last_out": None,
            "area_name_in": "Unknown",
            "area_name_out": "Unknown",
            "effective_work_seconds": None,
            "effective_work_intervals": None,
        }
    intervals: List[Tuple[dt, dt]] = []
    in_start: Optional[dt] = None
    for (t, _, _), resolution in zip(events, resolutions):
        if resolution == "exit":
            if in_start is not None:
                intervals.append((in_start, t))
            in_start = None
        elif in_start is None:
            in_start = t
    last_t = events[-1][0]
    if in_start is not None and last_t > in_start:
        intervals.append((in_start, last_t))
    total = sum(int((e - s).total_seconds()) for s, e in intervals)
    return {
        "first_in": events[0][0],
        "last_out": last_t,
        "area_name_in": events[0][1],
        "area_name_out": events[-1][1],
        "effective_work_seconds": total or None,
        "effective_work_intervals": (
            [{"start": s.isoformat(), "end": e.isoformat()} for s, e in intervals] or None
        ),
    }


def _turnstile_report(events: List[Event], rules: DeviceRules) -> Dict[str, Any]:
    """Вариант «только турникеты»: те же правила, но по одним турникетам. O(k).

    Единственный проход через турникет — это либо приход, либо уход, но не оба сразу:
    турникет выхода даёт только уход (сотрудник вошёл не через турникет — прихода нет),
    любой другой — только приход. Иначе отчёт показал бы «16:51 – 16:51».

    Args:
        events: Турникетные события дня по возрастанию времени (без повторов).
        rules: Классы устройств и пороги.

    Returns:
        Словарь с ключами REPORT_FIELDS.
    """
    report = _report(events, _resolve_exits(events, rules, _zero_stats()))
    if len(events) == 1:
        side = (
            ("first_in", "area_name_in")
            if events[0][2] in rules.exit
            else ("last_out", "area_name_out")
        )
        report[side[0]] = None
        report[side[1]] = "Unknown"
    return report


def compute_day(
    events: Iterable[Dict[str, Any]],
    rules: Optional[DeviceRules] = None,
    tz: Optional[tzinfo] = None,
) -> DayResult:
    """Считает оба варианта отчёта и историю перемещений одного сотрудника за день.

    Args:
        events: Сырые события API СКУД за один день одного сотрудника.
        rules: Классы устройств; по умолчанию DeviceRules.from_settings().
        tz: Таймзона eventTime; по умолчанию таймзона проекта.

    Returns:
        DayResult с вариантами "all" и "turnstile", area_sequence и счётчиками.
        Сложность O(k log k), где k — число событий.
    """
    rules = rules or DeviceRules.from_settings()
    parsed, parse_errors = _parse_events(events, tz or timezone.get_default_timezone())
    kept = _kept_indices(parsed, rules.repeat_tap)
    kept_events = [parsed[i] for i in kept]
    stats = _zero_stats()
    kept_resolutions = _resolve_exits(kept_events, rules, stats)

    area_sequence: List[Dict[str, str]] = []
    owner = -1
    for i, (t, area, sn) in enumerate(parsed):
        if owner + 1 < len(kept) and kept[owner + 1] == i:
            owner += 1
        resolution = kept_resolutions[owner]
        item = {"t": t.strftime("%H:%M"), "area": area}
        if sn:
            item["devSn"] = sn
        if kept[owner] > 0 and sn in rules.exit:
            item["exit_candidate"] = "1"
        if resolution:
            item["exit_resolution"] = resolution
        if resolution == "exit":
            item["is_exit"] = "1"
        area_sequence.append(item)

    return DayResult(
        variants={
            "all": _report(kept_events, kept_resolutions),
            "turnstile": _turnstile_report(
                [e for e in kept_events if e[2] in rules.turnstile], rules
            ),
        },
        area_sequence=area_sequence or None,
        stats=stats,
        parse_errors=parse_errors,
    )


def _to_db_datetime(value: Optional[dt]) -> Optional[str]:
    """Переводит время в формат, в котором БД хранит DATETIME при USE_TZ.

    Так apply_report_mode переносит значение из JSON в колонку одним UPDATE без CAST.

    Args:
        value: Aware datetime или None.

    Returns:
        Строка "YYYY-MM-DD HH:MM:SS[.ffffff]" в UTC или None.
    """
    if value is None:
        return None
    return value.astimezone(dt_timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def variant_to_json(variant: Dict[str, Any]) -> Dict[str, Any]:
    """Готовит вариант отчёта к записи в report_variants.

    Args:
        variant: Поля REPORT_FIELDS с datetime в first_in/last_out.

    Returns:
        Копия варианта, где first_in/last_out — строки UTC (см. _to_db_datetime).
    """
    return {
        **variant,
        "first_in": _to_db_datetime(variant["first_in"]),
        "last_out": _to_db_datetime(variant["last_out"]),
    }


def variant_from_json(variant: Dict[str, Any]) -> Dict[str, Any]:
    """Читает вариант отчёта из report_variants.

    Args:
        variant: Вариант из JSON (строки времени в UTC или с явным смещением).

    Returns:
        Поля REPORT_FIELDS, first_in/last_out — aware datetime или None.
    """
    out = {field: variant.get(field) for field in REPORT_FIELDS}
    for field in ("first_in", "last_out"):
        value = out[field]
        if value:
            parsed = dt.fromisoformat(value)
            out[field] = parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)
    return out


def _record_fields(day: DayResult, mode: str) -> Dict[str, Any]:
    """Собирает поля строки StaffAttendance для режима отчёта.

    Args:
        day: Итог дня сотрудника.
        mode: "all" или "turnstile" — какой вариант идёт в отчётные колонки.

    Returns:
        Поля REPORT_FIELDS, area_sequence и report_variants.
    """
    return {
        **day.variants[mode],
        "area_sequence": day.area_sequence,
        "report_variants": {m: variant_to_json(v) for m, v in day.variants.items()},
    }


def save_attendance_days(
    days: Dict[date, Dict[int, DayResult]], mode: Optional[str] = None
) -> Dict[str, int]:
    """Записывает дни в StaffAttendance одним upsert. O(R).

    Args:
        days: {рабочий день: {staff_id: DayResult}}; строка сохраняется
            с date_at = рабочий день + 1.
        mode: "all" или "turnstile"; по умолчанию из AttendanceSettings.

    Returns:
        {"created_records": ..., "updated_records": ...}. Счётчики берутся из одного
        SELECT существующих ключей; сама запись — INSERT … ON DUPLICATE KEY UPDATE.
    """
    mode = mode or models.AttendanceSettings.report_mode()
    records = [
        models.StaffAttendance(
            staff_id=staff_id,
            date_at=work_day + timedelta(days=1),
            **_record_fields(day, mode),
        )
        for work_day, by_staff in days.items()
        for staff_id, day in by_staff.items()
    ]
    if not records:
        return {"created_records": 0, "updated_records": 0}

    existing = set(
        models.StaffAttendance.objects.filter(
            date_at__in={record.date_at for record in records}
        ).values_list("staff_id", "date_at")
    )
    updated = sum((record.staff_id, record.date_at) in existing for record in records)
    unique_fields = (
        ["staff", "date_at"] if connection.features.supports_update_conflicts_with_target else None
    )
    with transaction.atomic():
        models.StaffAttendance.objects.bulk_create(
            records,
            batch_size=1000,
            update_conflicts=True,
            unique_fields=unique_fields,
            update_fields=[*REPORT_FIELDS, "area_sequence", "report_variants"],
        )
    return {"created_records": len(records) - updated, "updated_records": updated}


def apply_report_mode(mode: Optional[str] = None) -> int:
    """Переписывает отчётные колонки из report_variants[mode] одним UPDATE. O(R) в БД.

    JSON null через ->> в MySQL приходит строкой 'null' — NullIf превращает её в SQL NULL.

    Args:
        mode: "all" или "turnstile"; по умолчанию из AttendanceSettings.

    Returns:
        Число обновлённых строк.

    Raises:
        ValueError: Если mode не из REPORT_MODES.
    """
    mode = mode or models.AttendanceSettings.report_mode()
    if mode not in REPORT_MODES:
        raise ValueError(f"Unknown report mode: {mode}")

    def text(field: str):
        return NullIf(KT(f"report_variants__{mode}__{field}"), Value("null"))

    updated = models.StaffAttendance.objects.exclude(report_variants__isnull=True).update(
        **{field: text(field) for field in REPORT_FIELDS if field != "effective_work_intervals"},
        effective_work_intervals=KeyTransform(
            "effective_work_intervals", KeyTransform(mode, "report_variants")
        ),
    )
    invalidate_staff_attendance_caches()
    logger.info("apply_report_mode(mode=%s): %d rows", mode, updated)
    return updated


class AttendanceApiError(Exception):
    """Ответ API СКУД с ошибкой (сетевые сбои не сюда — их повторяет backoff).

    Attributes:
        info: Подробности для логов и ответа fetch_data_view
            (pin, status, url, error, response_body_preview).
    """

    def __init__(self, info: Dict[str, Any]):
        """Сохраняет подробности ошибки.

        Args:
            info: Словарь с полем "error" и контекстом запроса.
        """
        super().__init__(info.get("error"))
        self.info = info


class AsyncAttendanceFetcher:
    """Клиент API СКУД: события всех сотрудников за период и запись дней в StaffAttendance.

    Используется как асинхронный контекстный менеджер (сессия aiohttp открывается
    на время выгрузки); sync_range и get_all_attendance открывают его сами.

    Attributes:
        PAGE_SIZE: Максимальный размер страницы API.
        BULK_WINDOW: Начальная длина окна запроса без personPin.
        max_concurrent_requests: Предел одновременных запросов к API.
        requests_ok: Число успешных запросов за время жизни объекта.
    """

    PAGE_SIZE = 1000
    BULK_WINDOW = timedelta(hours=1)

    def __init__(self, max_concurrent_requests: int = 6):
        """Создаёт клиент без открытой сессии.

        Args:
            max_concurrent_requests: Предел одновременных запросов к API.

        Raises:
            ValueError: Если предел меньше 1.
        """
        if max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests must be greater than 0")
        self.max_concurrent_requests = max_concurrent_requests
        self.session: Optional[aiohttp.ClientSession] = None
        self.requests_ok = 0
        self._bulk = True

    async def __aenter__(self) -> "AsyncAttendanceFetcher":
        """Открывает сессию aiohttp и семафор параллельных запросов.

        Returns:
            Этот же клиент.
        """
        self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit_per_host=20),
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        """Закрывает сессию aiohttp.

        Args:
            *exc_info: Стандартные аргументы выхода из контекста (не используются).
        """
        if self.session:
            await self.session.close()

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientConnectionError, asyncio.TimeoutError),
        max_tries=3,
    )
    async def _get(self, params: Dict[str, str]) -> List[Dict[str, Any]]:
        """Запрашивает одну страницу событий listAttTransaction.

        Args:
            params: startDate, endDate, pageNo и при необходимости personPin.

        Returns:
            Список событий страницы.

        Raises:
            AttendanceApiError: Не 200, не JSON, неверный формат или code != 0.
            aiohttp.ClientConnectionError: Сеть недоступна после 3 попыток backoff.
            asyncio.TimeoutError: Таймаут после 3 попыток backoff.
            RuntimeError: Сессия не открыта (клиент вне async with).
        """
        if self.session is None:
            raise RuntimeError("aiohttp session is not initialized")
        async with self._semaphore:
            async with self.session.get(
                f"{settings.API_URL.rstrip('/')}/api/transaction/listAttTransaction",
                params={
                    **params,
                    "pageSize": str(self.PAGE_SIZE),
                    "access_token": settings.API_KEY,
                },
                headers=BROWSER_HEADERS,
                ssl=True,
            ) as response:
                body = await response.text()
                status, url = response.status, _sanitize_url(str(response.url))

        def fail(message: str) -> AttendanceApiError:
            info = {
                "pin": params.get("personPin"),
                "status": status,
                "url": url,
                "error": message,
                "response_body_preview": _shorten_payload(body),
            }
            logger.error("Attendance API error: %s", info)
            return AttendanceApiError(info)

        if status != 200:
            raise fail("External API responded with non-200 status")
        try:
            data = json.loads(body)
        except ValueError as decode_error:
            raise fail(f"Invalid JSON payload: {decode_error}") from decode_error
        if not isinstance(data, dict):
            raise fail("Unexpected payload format")
        if data.get("code") not in (0, None):
            raise fail(f"API code {data.get('code')}: {data.get('message')}")
        records = data.get("data") or []
        if not isinstance(records, list):
            raise fail("Invalid payload: field 'data' must be a list")
        self.requests_ok += 1
        return records

    async def fetch_window(
        self, start: dt, end: dt, pin: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Все события за окно [start, end], без пагинации. O(E_окна / P) запросов.

        Полное окно (PAGE_SIZE событий) делится пополам по секундам, пока ответ не станет
        неполным: соседние окна не пересекаются и не оставляют щелей, поэтому события
        с одинаковым eventTime не теряются. Страницы используются только для окна в одну
        секунду с более чем PAGE_SIZE событиями.

        Args:
            start: Начало окна, локальное время без таймзоны (включительно).
            end: Конец окна, локальное время без таймзоны (включительно, до секунды).
            pin: Только события этого сотрудника; None — все сотрудники.

        Returns:
            События окна.

        Raises:
            AttendanceApiError: Ошибка ответа API (см. _get).
        """
        params = {
            "startDate": start.strftime(API_DATETIME_FORMAT),
            "endDate": end.strftime(API_DATETIME_FORMAT),
            "pageNo": "1",
        }
        if pin:
            params["personPin"] = pin
        page = await self._get(params)
        if len(page) < self.PAGE_SIZE:
            return page
        if end - start < timedelta(seconds=1):
            events, page_no = list(page), 1
            while len(page) == self.PAGE_SIZE:
                page_no += 1
                page = await self._get({**params, "pageNo": str(page_no)})
                events.extend(page)
            return events
        mid = (start + (end - start) / 2).replace(microsecond=0)
        left, right = await asyncio.gather(
            self.fetch_window(start, mid, pin),
            self.fetch_window(mid + timedelta(seconds=1), end, pin),
        )
        return left + right

    async def fetch_events(
        self, start_day: date, end_day: date, pins: Iterable[str]
    ) -> List[Dict[str, Any]]:
        """Все события за дни [start_day, end_day] без дублей.

        Обычно — часовые окна без personPin. Если API отказал в таком запросе, клиент
        один раз переключается на запросы по сотрудникам из pins.

        Args:
            start_day: Первый рабочий день.
            end_day: Последний рабочий день (включительно).
            pins: PIN сотрудников для запасного режима по одному.

        Returns:
            Уникальные по id события; у каждого есть поле "pin".

        Raises:
            AttendanceApiError: Ошибка API в запасном режиме.
        """
        start = dt.combine(start_day, time.min)
        end = dt.combine(end_day, time.max).replace(microsecond=0)
        if self._bulk:
            windows = []
            while start <= end:
                window_end = min(end, start + self.BULK_WINDOW - timedelta(seconds=1))
                windows.append(self.fetch_window(start, window_end))
                start = window_end + timedelta(seconds=1)
            try:
                chunks = await asyncio.gather(*windows)
            except AttendanceApiError as error:
                logger.warning("Bulk attendance fetch refused (%s), falling back to per-PIN", error)
                self._bulk = False
                return await self.fetch_events(start_day, end_day, pins)
        else:
            pin_list = list(pins)
            chunks = await asyncio.gather(*(self.fetch_window(start, end, pin) for pin in pin_list))
            for pin, chunk in zip(pin_list, chunks):
                for ev in chunk:
                    ev.setdefault("pin", pin)
        unique: Dict[Any, Dict[str, Any]] = {}
        for chunk in chunks:
            for ev in chunk:
                unique[ev.get("id") or (ev.get("pin"), ev.get("eventTime"), ev.get("devSn"))] = ev
        return list(unique.values())

    async def sync_range(
        self,
        start_day: date,
        end_day: date,
        pins: Optional[Iterable[str]] = None,
        *,
        chunk_days: int = 7,
        keep_existing_when_empty: bool = False,
    ) -> Dict[str, Any]:
        """Выгружает рабочие дни [start_day, end_day] и сохраняет их в StaffAttendance.

        Идёт кусками по chunk_days: память O(событий куска). Кусок, где API ответил
        ошибкой, не пишется вовсе — частичных дней не бывает.

        Args:
            start_day: Первый рабочий день.
            end_day: Последний рабочий день (включительно).
            pins: Только эти сотрудники; None — все действующие.
            chunk_days: Сколько дней выгружать за один проход.
            keep_existing_when_empty: Перевыгрузка истории — дни без событий не пишутся,
                чтобы не затереть ручные записи и пробелы API. False — как ежедневная
                выгрузка: строка на каждого сотрудника, в том числе пустая.

        Returns:
            Сводка: total_pins, successful_requests/failed_requests (сотрудники; при ошибке
            куска — все неуспешные), api_requests, pins_with_events, pins_without_events,
            event_time_parse_errors, счётчики неоднозначных выходов, created_records,
            updated_records, failed_pins, failed_chunks, errors.
        """
        staff_qs = models.Staff.objects.all()
        if pins is not None:
            staff_qs = staff_qs.filter(pin__in=list(pins))
        staff_ids: Dict[str, int] = dict(
            await database_sync_to_async(list)(staff_qs.values_list("pin", "id"))
        )
        mode = await database_sync_to_async(models.AttendanceSettings.report_mode)()
        rules = DeviceRules.from_settings()
        tz = timezone.get_default_timezone()
        empty_day = compute_day((), rules, tz)

        stats = {"event_time_parse_errors": 0, **_zero_stats()}
        staff_with_events: set = set()
        totals = {"created_records": 0, "updated_records": 0}
        errors: List[Dict[str, Any]] = []
        failed_chunks: List[str] = []
        logger.info(
            "Attendance sync %s..%s: %d staff, chunk_days=%d, mode=%s",
            start_day,
            end_day,
            len(staff_ids),
            chunk_days,
            mode,
        )

        async with self:
            chunk_start = start_day
            while chunk_start <= end_day:
                chunk_end = min(end_day, chunk_start + timedelta(days=max(1, chunk_days) - 1))
                try:
                    events = await self.fetch_events(chunk_start, chunk_end, staff_ids)
                except (AttendanceApiError, aiohttp.ClientError, asyncio.TimeoutError) as error:
                    info = getattr(error, "info", {"error": f"{type(error).__name__}: {error}"})
                    errors.append({**info, "chunk": f"{chunk_start}..{chunk_end}"})
                    failed_chunks.append(f"{chunk_start}..{chunk_end}")
                    chunk_start = chunk_end + timedelta(days=1)
                    continue

                grouped: Dict[Tuple[int, str], List[Dict[str, Any]]] = defaultdict(list)
                for ev in events:
                    pin = ev.get("pin")
                    staff_id = staff_ids.get(pin) if isinstance(pin, str) else None
                    if staff_id is not None:
                        grouped[(staff_id, str(ev.get("eventTime", ""))[:10])].append(ev)
                staff_with_events.update(staff_id for staff_id, _ in grouped)

                days: Dict[date, Dict[int, DayResult]] = {}
                day = chunk_start
                while day <= chunk_end:
                    days[day] = (
                        {}
                        if keep_existing_when_empty
                        else dict.fromkeys(staff_ids.values(), empty_day)
                    )
                    day += timedelta(days=1)
                for (staff_id, day_str), day_events in grouped.items():
                    result = compute_day(day_events, rules, tz)
                    stats["event_time_parse_errors"] += result.parse_errors
                    for key in RESOLUTION_STAT_KEYS:
                        stats[key] += result.stats[key]
                    by_day = days.get(date.fromisoformat(day_str))
                    if by_day is not None:
                        by_day[staff_id] = result

                saved = await database_sync_to_async(save_attendance_days)(days, mode)
                for key in totals:
                    totals[key] += saved[key]
                logger.info(
                    "Attendance sync %s..%s: %d events, %d staff with events, %s",
                    chunk_start,
                    chunk_end,
                    len(events),
                    len({staff_id for staff_id, _ in grouped}),
                    saved,
                )
                chunk_start = chunk_end + timedelta(days=1)

        if totals["created_records"] or totals["updated_records"]:
            await database_sync_to_async(invalidate_staff_attendance_caches)()
        summary = {
            "total_pins": len(staff_ids),
            "successful_requests": 0 if failed_chunks else len(staff_ids),
            "failed_requests": len(staff_ids) if failed_chunks else 0,
            "api_requests": self.requests_ok,
            "pins_with_events": len(staff_with_events),
            "pins_without_events": len(staff_ids) - len(staff_with_events),
            **stats,
            **totals,
            "failed_pins": sorted(staff_ids) if failed_chunks else [],
            "failed_chunks": failed_chunks,
            "errors": errors,
        }
        logger.info(
            "Attendance sync summary: %s",
            {k: v for k, v in summary.items() if k not in ("failed_pins", "errors")},
        )
        return summary

    async def get_all_attendance(self, days: Optional[int] = None) -> Dict[str, Any]:
        """Ежедневная выгрузка одного рабочего дня для всех сотрудников.

        Границы дня — в таймзоне проекта: в 04:00 1 марта выгружается 28 февраля
        и сохраняется с date_at = 1 марта.

        Args:
            days: Сколько дней назад от сегодня; по умолчанию settings.DAYS (обычно 1).

        Returns:
            Сводка sync_range плюс days, source_date (рабочий день) и save_date (date_at).
        """
        days_to_subtract = days if days is not None else settings.DAYS
        work_day = timezone.localtime(timezone.now()).date() - timedelta(days=days_to_subtract)
        summary = await self.sync_range(work_day, work_day, chunk_days=1)
        return {
            "days": days_to_subtract,
            "source_date": work_day.isoformat(),
            "save_date": (work_day + timedelta(days=1)).isoformat(),
            **summary,
        }
