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
    Внимание: Работает только с Redis и Memcached, которые поддерживают поиск по паттернам.

    Args:
        pattern (str): Паттерн для поиска ключей (например, "staff_*").
        cache (any, optional): Объект кэша. По умолчанию: `Cache`.

    Returns:
        int: Количество удаленных ключей.

    Examples:
        >>> invalidate_cache_pattern("staff_detail_*")
    """
    try:
        if hasattr(cache, "keys"):
            keys = cache.keys(pattern)
            if keys:
                deleted = cache.delete_many(keys)
                deleted_count = deleted if deleted is not None else 0
                logger.info(f"Invalidated {deleted_count} cache keys matching pattern: {pattern}")
                return deleted_count
            else:
                return 0
        else:
            logger.warning("Cache backend does not support pattern invalidation")
            return 0
    except Exception as e:
        logger.error(f"Error invalidating cache pattern {pattern}: {str(e)}")
        return 0
