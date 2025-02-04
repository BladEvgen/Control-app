import asyncio
import logging
from functools import wraps

from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)


def async_class_view(cls):
    """
    Decorator for class-oriented views.
    Wraps the dispatch method so that it always runs asynchronously:
    - If the HTTP method (e.g. get/post) is asynchronous, it is called directly.
    - If the method is synchronous, it is executed via asyncio.to_thread.
    If a coroutine is returned, it is additionally awaited.
    """
    original_dispatch = cls.dispatch

    @wraps(original_dispatch)
    async def async_dispatch(self, request, *args, **kwargs):
        handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
        if asyncio.iscoroutinefunction(handler):
            response = await handler(request, *args, **kwargs)
        else:
            response = await asyncio.to_thread(handler, request, *args, **kwargs)
        if asyncio.iscoroutine(response):
            response = await response
        return response

    cls.dispatch = async_dispatch
    return cls


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
            logger.info(
                "Entering async_drf_view wrapper; converting async view to sync"
            )
            result = async_to_sync(func)(*args, **kwargs)
            logger.info("Async view completed in async_drf_view wrapper")
            return result

        return sync_wrapper

    return decorator
