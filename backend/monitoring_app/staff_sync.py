import logging
import re
from asyncio import gather, run as asyncio_run
from contextlib import AbstractContextManager
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, cast

from django.conf import settings
from django.db import transaction

from monitoring_app import models

logger = logging.getLogger("django")

EXCLUDED_FIO_PATTERN = re.compile(
    r"^(гость|охрана|в\s*фио)\s*\d*$",
    re.IGNORECASE,
)


def is_excluded_staff(name: str, surname: str) -> bool:
    """
    Определяет, нужно ли исключить персону из синхронизации по ФИО.

    Исключаются шаблоны: гость, охрана, «в фио» и варианты с цифрами
    (Гость 1, Охрана 4 и т.п.).

    Args:
        name: Имя или первая часть ФИО.
        surname: Фамилия или вторая часть ФИО.

    Returns:
        True, если запись исключаем из синхронизации.
    """
    if not name and not surname:
        return True
    for part in (str(name or "").strip(), str(surname or "").strip()):
        if part and EXCLUDED_FIO_PATTERN.match(part):
            return True
    full = f"{surname or ''} {name or ''}".strip()
    if full and EXCLUDED_FIO_PATTERN.match(full):
        return True
    return False



_FETCH_BATCH_SIZE = 80

_FETCH_CONNECT_TIMEOUT = 5.0
_FETCH_READ_TIMEOUT = 10.0
_FETCH_TOTAL_TIMEOUT = 15.0


async def _fetch_one_person(
    session: Any,
    base_url: str,
    api_key: str,
    pin: str,
) -> Tuple[Optional[Dict[str, Any]], Literal["ok", "404", "error"]]:
    """
    Один запрос GET /api/person/get/{pin}. Без семафора — ограничение по пачкам.
    """
    url = f"{base_url}/api/person/get/{pin}"
    params = {"access_token": api_key}
    try:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return None, "error"
            body = await resp.json()
    except Exception as e:
        logger.debug("get/%s failed: %s", pin, e)
        return None, "error"
    if not isinstance(body, dict):
        return None, "error"
    if body.get("code") == -22 or "не существует" in str(body.get("message", "")).lower():
        return None, "404"
    data = body.get("data")
    if not isinstance(data, dict):
        return None, "error"
    pin_val = data.get("pin") or data.get("personPin") or data.get("personNo")
    if not pin_val:
        return None, "error"
    if not data.get("pin"):
        data = dict(data, pin=str(pin_val).strip())
    return data, "ok"


def _chunked(items: List[str], size: int):
    """Итератор по списку pin пачками фиксированного размера."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _fetch_persons_by_pins_async(
    pins: List[str],
    base_url: str,
    api_key: str,
    batch_size: int = _FETCH_BATCH_SIZE,
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """
    Загрузка персон пачками: не более batch_size одновременных запросов,
    одна сессия на все пачки (переиспользование соединений).
    """
    import aiohttp

    if not pins:
        return [], set()
    conn_limit = min(batch_size + 20, 100)
    timeout = aiohttp.ClientTimeout(
        connect=_FETCH_CONNECT_TIMEOUT,
        sock_read=_FETCH_READ_TIMEOUT,
        total=_FETCH_TOTAL_TIMEOUT,
    )
    connector = aiohttp.TCPConnector(
        limit=conn_limit,
        limit_per_host=conn_limit,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
        force_close=False,
    )
    persons: List[Dict[str, Any]] = []
    pins_404: Set[str] = set()

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        for chunk in _chunked(pins, batch_size):
            tasks = [
                _fetch_one_person(session, base_url, api_key, pin)
                for pin in chunk
            ]
            results = await gather(*tasks, return_exceptions=True)
            for pin, res in zip(chunk, results):
                if isinstance(res, Exception):
                    logger.debug("fetch person failed for %s: %s", pin, res)
                    continue
                if not isinstance(res, tuple) or len(res) != 2:
                    continue
                data, status = res
                if status == "ok" and isinstance(data, dict):
                    persons.append(data)
                elif status == "404":
                    pins_404.add(pin)
    return persons, pins_404


def fetch_persons_by_pins(
    pins: List[str],
    batch_size: int = _FETCH_BATCH_SIZE,
) -> Tuple[List[Dict[str, Any]], Set[str], Optional[str]]:
    """
    Загружает персоны по списку pin пачками (get/{pin}).

    Args:
        pins: Список pin (например, из БД).
        batch_size: Размер пачки одновременных запросов (по умолчанию 80).

    Returns:
        (список персон, множество pin с code=-22 для удаления, ошибка или None).
    """
    api_key = getattr(settings, "API_KEY", None)
    base_url = (getattr(settings, "API_URL", None) or "").strip().rstrip("/")
    if not api_key or not base_url:
        return [], set(), "API_KEY или API_URL не заданы"
    if not pins:
        return [], set(), None
    try:
        persons, pins_404 = asyncio_run(
            _fetch_persons_by_pins_async(
                pins, base_url, api_key, batch_size=batch_size
            )
        )
    except Exception as e:
        logger.exception("Загрузка персон по pin: %s", e)
        return [], set(), str(e)
    return persons, pins_404, None


def _normalize_person_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует запись персоны из API к единому виду.

    Args:
        item: Словарь из ответа API (person).

    Returns:
        Словарь с полями pin, name, lastName, deptCode.
    """
    pin = item.get("pin") or item.get("personPin") or item.get("id")
    if pin is not None:
        pin = str(pin).strip()
    return {
        "pin": pin,
        "name": (item.get("name") or "").strip() or "",
        "lastName": (item.get("lastName") or item.get("last_name") or "").strip() or "",
        "deptCode": item.get("deptCode") or item.get("dept_code"),
    }


def _bulk_create_staff(
    external_by_pin: Dict[str, Dict[str, Any]],
    to_add_pins: Set[str],
    result: Dict[str, Any],
) -> None:
    """
    Создаёт новых сотрудников одним bulk_create и одним bulk для M2M (должности).

    Один запрос за должностью «Сотрудник», один — за отделами по deptCode.

    Args:
        external_by_pin: Словарь pin -> данные персоны из API.
        to_add_pins: Множество pin для создания.
        result: Словарь результата, в который пишется result["created"].
    """
    position, _ = models.Position.objects.get_or_create(name="Сотрудник")
    dept_codes = set()
    for pin in to_add_pins:
        person = external_by_pin.get(pin)
        if person and person.get("deptCode") is not None:
            dept_codes.add(str(person["deptCode"]).strip())
    dept_map: Dict[str, models.ChildDepartment] = {}
    if dept_codes:
        dept_map = {
            d.id: d
            for d in models.ChildDepartment.objects.filter(id__in=dept_codes)
        }
    staff_list: List[models.Staff] = []
    for pin in to_add_pins:
        person = external_by_pin.get(pin)
        if not person:
            continue
        name = person.get("name") or ""
        surname = person.get("lastName") or "Нет фамилии"
        dept_code = person.get("deptCode")
        department = None
        if dept_code is not None:
            department = dept_map.get(str(dept_code).strip())
        staff_list.append(
            models.Staff(
                pin=pin,
                name=name,
                surname=surname,
                department=department,
            )
        )
    if not staff_list:
        return
    try:
        created = models.Staff.objects.bulk_create(staff_list)
        through_model = models.Staff.positions.through
        through_model.objects.bulk_create(
            [
                through_model(staff_id=s.pk, position_id=position.pk)
                for s in created
            ]
        )
        result["created"] = len(created)
        logger.info("Staff sync: bulk created %s staff", len(created))
    except Exception as e:
        logger.exception("Bulk create staff failed: %s", e)
        result.setdefault("errors", []).append(str(e))


def sync_staff_from_external(dry_run: bool = False) -> Dict[str, Any]:
    """
    Синхронизирует Staff с API СКУД: загрузка по pin из БД (get/{pin}), удаление при code=-22.

    Берёт все pin из БД, запрашивает GET /api/person/get/{pin}. Удаляет из БД только тех,
    по кого API вернул 200 с code=-22 («Сотрудник не существует»). HTTP 404 и ошибки не удаляем.

    Args:
        dry_run: Если True, только подсчёт и примеры без изменений в БД.

    Returns:
        Словарь: deleted, created, errors, skipped_excluded, external_count, our_count,
        to_delete_examples, to_add_examples.
    """
    result: Dict[str, Any] = {
        "deleted": 0,
        "created": 0,
        "errors": [],
        "skipped_excluded": 0,
        "external_count": None,
        "our_count": None,
        "to_delete_examples": [],
        "to_add_examples": [],
    }

    our_pins = list(models.Staff.objects.values_list("pin", flat=True))
    result["our_count"] = len(our_pins)
    if not our_pins:
        return result

    logger.info("Загрузка персон по pin из БД (%s шт.) get/{pin}.", len(our_pins))
    persons, pins_404, err = fetch_persons_by_pins(our_pins)
    if err:
        result.setdefault("errors", []).append(err)
        return result
    logger.info(
        "Получено %s персон; удалить при code=-22: %s шт.",
        len(persons),
        len(pins_404),
    )

    external_by_pin: Dict[str, Dict[str, Any]] = {}
    for item in persons:
        normalized = _normalize_person_item(item)
        pin = normalized.get("pin")
        if not pin:
            continue
        name = normalized.get("name") or ""
        surname = normalized.get("lastName") or "Нет фамилии"
        if is_excluded_staff(name, surname):
            result["skipped_excluded"] += 1
            continue
        external_by_pin[pin] = normalized

    result["external_count"] = len(external_by_pin)
    to_delete_pins = pins_404
    to_add_pins: Set[str] = set()

    if to_delete_pins:
        sample_delete = list(to_delete_pins)[:10]
        for row in models.Staff.objects.filter(pin__in=sample_delete).values_list(
            "pin", "name", "surname"
        ):
            result["to_delete_examples"].append(
                {"pin": row[0], "name": row[1] or "", "surname": row[2] or ""}
            )
    if to_add_pins:
        for pin in list(to_add_pins)[:10]:
            p = external_by_pin.get(pin, {})
            result["to_add_examples"].append(
                {
                    "pin": pin,
                    "name": p.get("name") or "",
                    "surname": p.get("lastName") or "",
                }
            )

    if not dry_run:
        _atomic = cast(
            AbstractContextManager[None],
            transaction.atomic(),
        )
        with _atomic:
            if to_delete_pins:
                deleted_count, deleted_by_model = models.Staff.objects.filter(
                    pin__in=to_delete_pins
                ).delete()
                result["deleted"] = deleted_count
                logger.info(
                    "Staff sync: deleted %s staff (not in external API), "
                    "всего записей удалено (с каскадом): %s",
                    len(to_delete_pins),
                    sum(deleted_by_model.values()),
                )
            if to_add_pins:
                _bulk_create_staff(
                    external_by_pin=external_by_pin,
                    to_add_pins=to_add_pins,
                    result=result,
                )
    else:
        result["deleted"] = len(to_delete_pins)
        result["created"] = len(to_add_pins)

    return result
