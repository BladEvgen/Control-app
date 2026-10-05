import logging
from functools import wraps

from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)


def async_drf_view(methods):
    """
    Custom decorator to handle async views with DRF decorators.
    Uses async_to_sync instead of asyncio.run() so that the async view can run
    properly when the ASGI server already has an event loop.
    """

    def decorator(func):
        @api_view(methods)
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.info("Entering async_drf_view wrapper; converting async view to sync")
            result = async_to_sync(func)(*args, **kwargs)
            logger.info("Async view completed in async_drf_view wrapper")
            return result

        return sync_wrapper

    return decorator
