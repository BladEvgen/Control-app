import bisect
import datetime
import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar, Union, cast

from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.core.cache.backends.locmem import LocMemCache
from django.utils import timezone

logger = logging.getLogger(__name__)

Cache: BaseCache = caches["default"]
T = TypeVar("T")

_preload_registry: Dict[str, Callable[[], Any]] = {}


def get_cache(
    key: str,
    query: Optional[Callable[[], T]] = None,
    timeout: int = 10,
    cache: BaseCache = Cache,
) -> Optional[T]:
    """
    Получает данные из кэша по указанному ключу `key`.

    Args:
        key (str): Строковый ключ для доступа к данным в кэше.
        query (callable, optional): Функция, вызываемая для получения данных в случае их отсутствия в кэше.
            По умолчанию используется `lambda: any`, возвращающая всегда `True`.
        timeout (int, optional): Время жизни данных в кэше в секундах. По умолчанию: 10 секунд.
        cache (any, optional): Объект кэша, используемый для хранения данных. По умолчанию: `Cache`.

    Returns:
        any: Возвращает данные из кэша, если они есть, иначе данные, полученные из запроса.

    Examples:
        >>> get_cache("my_data_key")
    """
    data: Optional[T] = cache.get(key)
    if data is None and query is not None:
        data = query()
        set_tracked(key, data, timeout, cache=cache)
    return data


_TRACKED_PREFIXES = (
    "staff_detail_",
    "department_confirmation_",
    "staff_attendance_stats_",
    "map_location_",
    "attendance_data_",
    "staffatt_count_",
)
_KEY_INDEX = "attendance_cache_index"


def _redis_client(cache: BaseCache) -> Any:
    backend = cast(Any, cache)
    if hasattr(backend, "_cache") and hasattr(backend._cache, "get_client"):
        return backend._cache.get_client(write=True)
    return None


def set_tracked(key: str, value: Any, timeout: Optional[int], cache: BaseCache = Cache) -> None:
    """cache.set + запись ключа в индекс посещаемости (для invalidate_attendance_scope)."""
    cache.set(key, value, timeout)
    client = _redis_client(cache)
    if client is not None and key.startswith(_TRACKED_PREFIXES):
        client.sadd(cache.make_key(_KEY_INDEX), cache.make_key(key))


def preload_cache(
    key: str,
    query: Callable[[], T],
    timeout: int = 10,
    cache: BaseCache = Cache,
    force: bool = False,
) -> Optional[T]:
    """
    Предзагружает данные в кэш (горячий кэш).
    Если данные уже есть в кэше и force=False, возвращает существующие данные.
    Если force=True, перезаписывает данные в кэше.

    Args:
        key (str): Строковый ключ для доступа к данным в кэше.
        query (callable): Функция для получения данных.
        timeout (int, optional): Время жизни данных в кэше в секундах. По умолчанию: 10 секунд.
        cache (any, optional): Объект кэша. По умолчанию: `Cache`.
        force (bool, optional): Принудительно обновить кэш. По умолчанию: False.

    Returns:
        any: Загруженные данные.

    Examples:
        >>> preload_cache("my_data_key", lambda: expensive_query())
    """
    if not force:
        data = cache.get(key)
        if data is not None:
            logger.debug("Cache hit for key: %s", key)
            return data

    logger.info("Preloading cache for key: %s", key)
    try:
        data = query()
        cache.set(key, data, timeout)
        logger.info("Successfully preloaded cache for key: %s", key)
        return data
    except Exception as e:
        logger.error("Error preloading cache for key %s: %s", key, e)
        return None


def register_preload(key: str, query: Callable[[], Any]) -> None:
    """
    Регистрирует функцию для предзагрузки кэша.

    Args:
        key (str): Ключ кэша.
        query (callable): Функция для получения данных.

    Examples:
        >>> register_preload("parent_departments", lambda: get_parent_departments())
    """
    _preload_registry[key] = query
    logger.info("Registered preload function for key: %s", key)


def warmup_cache(keys: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
    """
    Прогревает кэш, выполняя предзагрузку для всех зарегистрированных ключей или указанных ключей.

    Args:
        keys (list, optional): Список ключей для предзагрузки. Если None, используется весь регистр.
        force (bool, optional): Принудительно обновить кэш. По умолчанию: False.

    Returns:
        dict: Словарь с результатами предзагрузки {key: success/error}.

    Examples:
        >>> warmup_cache()  # Прогревает все зарегистрированные ключи
        >>> warmup_cache(["parent_departments", "locations"])  # Прогревает указанные ключи
    """
    results: Dict[str, Any] = {}
    keys_to_warm = keys if keys else list(_preload_registry.keys())

    logger.info("Starting cache warmup for %s keys (force=%s)", len(keys_to_warm), force)

    for key in keys_to_warm:
        if key not in _preload_registry:
            logger.warning("Preload function not registered for key: %s", key)
            results[key] = {"status": "error", "message": "Not registered"}
            continue

        try:
            query = _preload_registry[key]
            data = preload_cache(key, query, force=force)
            results[key] = {
                "status": "success" if data is not None else "error",
                "data": data,
            }
        except Exception as e:
            logger.error("Error warming up cache for key %s: %s", key, e)
            results[key] = {"status": "error", "message": str(e)}

    logger.info(
        "Cache warmup completed. Success: %s",
        sum(1 for r in results.values() if r.get("status") == "success"),
    )
    return results


def invalidate_cache(key: str, cache: BaseCache = Cache) -> bool:
    """
    Инвалидирует (удаляет) данные из кэша.

    Args:
        key (str): Ключ кэша для удаления.
        cache (any, optional): Объект кэша. По умолчанию: `Cache`.

    Returns:
        bool: True если ключ был удален, False если ключа не было в кэше.

    Examples:
        >>> invalidate_cache("my_data_key")
    """
    try:
        deleted = cache.delete(key)
        if deleted:
            logger.info("Cache invalidated for key: %s", key)
        else:
            logger.debug("Cache key not found for invalidation: %s", key)
        return bool(deleted)
    except Exception as e:
        logger.error("Error invalidating cache for key %s: %s", key, e)
        return False


def invalidate_cache_pattern(pattern: str, cache: BaseCache = Cache) -> int:
    """
    Инвалидирует все ключи кэша, соответствующие паттерну.


    Args:
        pattern (str): Паттерн для поиска ключей (например, "staff_detail_*").
        cache (any, optional): Объект кэша. По умолчанию: `Cache`.

    Returns:
        int: Количество удаленных ключей.

    Examples:
        >>> invalidate_cache_pattern("staff_detail_*")
    """
    try:
        backend = cast(Any, cache)
        if hasattr(cache, "_cache") and hasattr(backend._cache, "get_client"):
            client = backend._cache.get_client(write=True)
            redis_pattern = f"*{pattern.rstrip('*')}*"
            keys_to_delete = list(client.scan_iter(match=redis_pattern))
            if keys_to_delete:
                deleted_count = client.delete(*keys_to_delete)
                logger.info(
                    "Invalidated %s cache keys matching pattern: %s",
                    deleted_count,
                    pattern,
                )
                return deleted_count or 0
            return 0
        if isinstance(cache, LocMemCache):
            needle = pattern.rstrip("*")
            with backend._lock:
                keys = [key for key in backend._cache if needle in key]
                for key in keys:
                    backend._delete(key)
            return len(keys)
        if hasattr(cache, "keys"):
            keys = backend.keys(pattern)
            if keys:
                deleted = cache.delete_many(keys)
                deleted_count = deleted if deleted is not None else 0
                logger.info(
                    "Invalidated %s cache keys matching pattern: %s",
                    deleted_count,
                    pattern,
                )
                return deleted_count
            return 0
        logger.warning("Cache backend does not support pattern invalidation")
        return 0
    except Exception as e:
        logger.error("Error invalidating cache pattern %s: %s", pattern, e)
        return 0


def staff_detail_cache_version() -> str:
    from monitoring_app.models import LessonAttendance

    return LessonAttendance.REPORT_FILTER_CACHE_VERSION


def invalidate_staff_detail_for_pin(staff_pin: str, cache: BaseCache = Cache) -> int:
    """Удаляет все staff_detail_* ключи для PIN (все диапазоны дат)."""
    pin = (staff_pin or "").strip()
    if not pin:
        return 0
    version = staff_detail_cache_version()
    return invalidate_cache_pattern(f"staff_detail_{version}_{pin}_", cache=cache)


def invalidate_staff_detail_for_department(
    department_id: Union[int, str], cache: BaseCache = Cache
) -> int:
    """Сбрасывает staff_detail-кэш отдела.

    department_id принимает и строку: первичный ключ ChildDepartment — CharField,
    и в базе есть нечисловые id (например «AUP»). Значение только подставляется
    в ключ кэша, приводить его к int не нужно и нельзя.
    """
    version = staff_detail_cache_version()
    return invalidate_cache_pattern(f"staff_detail_{version}_{department_id}_", cache=cache)


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _cache_keys(cache: BaseCache) -> tuple[list[str], Callable[[list[str]], None]]:
    client = _redis_client(cache)
    if client is not None:
        index = cache.make_key(_KEY_INDEX)
        raw = [k.decode() if isinstance(k, bytes) else k for k in client.smembers(index)]
        pipe = client.pipeline()
        for key in raw:
            pipe.exists(key)
        expired = {key for key, alive in zip(raw, pipe.execute()) if not alive}
        if expired:
            client.srem(index, *expired)
        live = [key for key in raw if key not in expired]

        def delete(keys: list[str]) -> None:
            if keys:
                client.delete(*keys)
                client.srem(index, *keys)

        return live, delete
    backend = cast(Any, cache)
    if isinstance(cache, LocMemCache):

        def delete_local(keys: list[str]) -> None:
            with backend._lock:
                for key in keys:
                    backend._delete(key)

        return list(backend._cache), delete_local
    return [], lambda keys: None


def _touches(rest: str, days: list[datetime.date]) -> bool:
    """Ключ с датой/диапазоном дат задевает один из days. Ключ без даты — задевает всегда."""
    found = _DATE_RE.findall(rest)
    if not found:
        return True
    start = datetime.date.fromisoformat(found[0])
    end = datetime.date.fromisoformat(found[1]) if len(found) > 1 else start
    i = bisect.bisect_left(days, start)
    return i < len(days) and days[i] <= end


def _department_chain(department_ids: set[str]) -> set[str]:
    """Отделы и все их предки: статистика отдела кэшируется под каждым предком (поддерево)."""
    from monitoring_app.models import ChildDepartment

    parent = dict(ChildDepartment.objects.values_list("id", "parent_id"))
    out: set[str] = set()
    for dept_id in department_ids:
        while dept_id and dept_id not in out:
            out.add(dept_id)
            dept_id = parent.get(dept_id)
    return out


def _as_day(value: Any) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def invalidate_attendance_scope(
    staff_ids: Iterable[int],
    days: Iterable[Any],
    cache: BaseCache = Cache,
) -> int:
    """Сбрасывает только кэши, построенные из посещаемости этих сотрудников за эти рабочие дни..

    Returns:
        Количество удалённых ключей.
    """
    from monitoring_app.models import Staff

    day_list = sorted({_as_day(d) for d in days if d})
    ids = [int(sid) for sid in staff_ids if sid]
    if not day_list:
        return 0
    rows = list(Staff.all_objects.filter(id__in=ids).values_list("pin", "department_id"))
    pins = {pin.strip() for pin, _ in rows if pin and pin.strip()}
    departments = {str(dept) for _, dept in rows if dept is not None}
    version = staff_detail_cache_version()

    dated_prefixes = [f"staff_detail_{version}_{pin}_" for pin in pins]
    dated_prefixes += [f"staff_detail_{version}_{d}_" for d in _department_chain(departments)]
    dated_prefixes += [f"department_confirmation_{d}_" for d in departments]
    dated_prefixes += [
        "department_confirmation_pins_",
        f"staff_attendance_stats_{version}_",
        f"map_location_{version}_",
        "attendance_data_",
    ]
    made = [(cache.make_key(prefix), prefix) for prefix in dated_prefixes]
    always = cache.make_key("staffatt_count_")

    keys, delete = _cache_keys(cache)
    doomed = [
        key
        for key in keys
        if key.startswith(always)
        or any(key.startswith(m) and _touches(key[len(m) :], day_list) for m, _ in made)
    ]
    delete(doomed)

    exact = [f"photos_for_{d}" for d in day_list]
    if timezone.localdate() in day_list:
        exact += ["today_attendance_stats", "map_locations_today"]
    cache.delete_many(exact)
    logger.info(
        "Attendance cache scope: %s staff, %s days, %s keys", len(ids), len(day_list), len(doomed)
    )
    return len(doomed)


def invalidate_staff_attendance_caches(
    staff_ids: Optional[Iterable[int]] = None,
    days: Optional[Iterable[Any]] = None,
    cache: BaseCache = Cache,
) -> None:
    """Сброс кэшей StaffAttendance после bulk-записи (сигналы не шлются).

    С staff_ids и days (рабочие дни) — точечно; без них — всё (смена режима отчёта и т.п.).
    """
    if staff_ids is not None and days is not None:
        invalidate_attendance_scope(staff_ids, days, cache=cache)
        return
    for prefix in (
        "attendance_data_",
        "staffatt_count_",
        "staff_attendance_stats_",
        "map_location_",
        "department_confirmation_",
        "staff_detail_",
    ):
        invalidate_cache_pattern(f"{prefix}*", cache=cache)
    invalidate_cache("today_attendance_stats", cache=cache)
    invalidate_cache("map_locations_today", cache=cache)
