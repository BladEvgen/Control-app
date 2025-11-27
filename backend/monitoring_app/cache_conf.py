from typing import Any, Callable, Optional, TypeVar

from django.core.cache import caches
from django.core.cache.backends.base import BaseCache

Cache: BaseCache = caches["default"]
T = TypeVar("T")


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
