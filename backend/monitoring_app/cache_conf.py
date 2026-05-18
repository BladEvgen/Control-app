import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar

from django.core.cache import caches
from django.core.cache.backends.base import BaseCache

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
        cache.set(key, data, timeout)
    return data


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
            logger.debug(f"Cache hit for key: {key}")
            return data

    logger.info(f"Preloading cache for key: {key}")
    try:
        data = query()
        cache.set(key, data, timeout)
        logger.info(f"Successfully preloaded cache for key: {key}")
        return data
    except Exception as e:
        logger.error(f"Error preloading cache for key {key}: {str(e)}")
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
    logger.info(f"Registered preload function for key: {key}")


def warmup_cache(
    keys: Optional[List[str]] = None, force: bool = False
) -> Dict[str, Any]:
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

    logger.info(f"Starting cache warmup for {len(keys_to_warm)} keys (force={force})")

    for key in keys_to_warm:
        if key not in _preload_registry:
            logger.warning(f"Preload function not registered for key: {key}")
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
            logger.error(f"Error warming up cache for key {key}: {str(e)}")
            results[key] = {"status": "error", "message": str(e)}

    logger.info(
        f"Cache warmup completed. Success: {sum(1 for r in results.values() if r.get('status') == 'success')}"
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
            logger.info(f"Cache invalidated for key: {key}")
        else:
            logger.debug(f"Cache key not found for invalidation: {key}")
        return bool(deleted)
    except Exception as e:
        logger.error(f"Error invalidating cache for key {key}: {str(e)}")
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
        if hasattr(cache, "_cache") and hasattr(cache._cache, "get_client"):
            client = cache._cache.get_client(write=True)
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
        if hasattr(cache, "keys"):
            keys = cache.keys(pattern)
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


def invalidate_staff_detail_for_staff_id(
    staff_id: int, cache: BaseCache = Cache
) -> int:
    from monitoring_app.models import Staff

    pin = Staff.objects.filter(pk=staff_id).values_list("pin", flat=True).first() or ""
    return invalidate_staff_detail_for_pin(pin, cache=cache)


def invalidate_staff_detail_for_department(
    department_id: int, cache: BaseCache = Cache
) -> int:
    version = staff_detail_cache_version()
    return invalidate_cache_pattern(
        f"staff_detail_{version}_{department_id}_", cache=cache
    )


def invalidate_lesson_attendance_derived_caches(
    *,
    staff_pins: Optional[List[str]] = None,
    staff_ids: Optional[List[int]] = None,
    department_ids: Optional[List[int]] = None,
    lesson_dates: Optional[List[Any]] = None,
    cache: BaseCache = Cache,
) -> None:
    """Инвалидирует кэши, зависящие от LessonAttendance (staff detail, stats, карта)."""
    from django.core.cache import cache as django_cache
    from monitoring_app.models import Staff

    _invalidate_excel_attendance_cache(cache=cache)

    version = staff_detail_cache_version()
    invalidate_cache_pattern(f"staff_attendance_stats_{version}_*", cache=cache)
    invalidate_cache_pattern(f"map_location_{version}_*", cache=cache)
    invalidate_cache_pattern("department_confirmation_pins_*", cache=cache)

    for lesson_date in lesson_dates or []:
        django_cache.delete(f"photos_for_{lesson_date}")

    resolved_pins: set[str] = set()
    for pin in staff_pins or []:
        pin_value = (pin or "").strip()
        if pin_value:
            resolved_pins.add(pin_value)

    id_list = [int(sid) for sid in (staff_ids or []) if sid]
    if id_list:
        for pin in Staff.objects.filter(id__in=id_list).values_list("pin", flat=True):
            pin_value = (pin or "").strip()
            if pin_value:
                resolved_pins.add(pin_value)

    for pin in resolved_pins:
        invalidate_staff_detail_for_pin(pin, cache=cache)

    resolved_dept_ids: set[int] = set()
    for dept_id in department_ids or []:
        if dept_id is not None:
            resolved_dept_ids.add(int(dept_id))

    if id_list:
        for dept_id in Staff.objects.filter(id__in=id_list).values_list(
            "department_id", flat=True
        ):
            if dept_id is not None:
                resolved_dept_ids.add(int(dept_id))

    for dept_id in resolved_dept_ids:
        invalidate_cache_pattern(f"department_confirmation_{dept_id}_*", cache=cache)
        invalidate_staff_detail_for_department(dept_id, cache=cache)


def _invalidate_excel_attendance_cache(cache: BaseCache = Cache) -> None:
    invalidate_cache_pattern("attendance_data_*", cache=cache)
