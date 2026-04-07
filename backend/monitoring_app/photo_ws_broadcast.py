from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import date
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

PHOTO_LIVE_UPDATE_JSON_BASE_BYTES = 220
PHOTO_LIVE_UPDATE_BYTES_PER_ID = 14
PHOTO_LIVE_UPDATE_MIN_CHUNK_SIZE = 40
PHOTO_LIVE_UPDATE_MAX_CHUNK_SIZE = 450
PHOTO_LIVE_UPDATE_TARGET_PAYLOAD_BYTES = 42_000


def estimate_photo_live_meta_payload_bytes(num_ids: int) -> int:
    """Estimate serialized JSON size for a single meta fan-out message body.

    Uses a linear model: fixed base plus ``num_ids`` times an average bytes-per-id
    estimate. Intended as a conservative upper-bound style guide for chunking,
    not an exact byte count.

    Args:
        num_ids: Number of attendance ids that would appear in ``attendance_ids``.

    Returns:
        Non-negative estimated size in bytes. For ``num_ids <= 0``, returns only
        the base overhead constant.
    """
    if num_ids <= 0:
        return PHOTO_LIVE_UPDATE_JSON_BASE_BYTES
    return PHOTO_LIVE_UPDATE_JSON_BASE_BYTES + num_ids * PHOTO_LIVE_UPDATE_BYTES_PER_ID


def choose_photo_live_update_chunk_size(total_ids: int) -> int:
    """Choose how many attendance ids to place in one channel layer message.

    Small or medium lists that fit under the byte target and ``MAX_CHUNK`` are
    kept in a single chunk. Larger lists use a step derived from the byte
    budget, clamped to ``[MIN_CHUNK, MAX_CHUNK]``.

    Args:
        total_ids: Total number of ids to send for one date (non-negative).

    Returns:
        Chunk size (step) in ``[1, MAX_CHUNK]``. For ``total_ids <= 0``, returns
        ``PHOTO_LIVE_UPDATE_MAX_CHUNK_SIZE`` (callers should not rely on this
        for empty lists).
    """
    if total_ids <= 0:
        return PHOTO_LIVE_UPDATE_MAX_CHUNK_SIZE

    if total_ids <= PHOTO_LIVE_UPDATE_MIN_CHUNK_SIZE:
        return total_ids

    if (
        total_ids <= PHOTO_LIVE_UPDATE_MAX_CHUNK_SIZE
        and estimate_photo_live_meta_payload_bytes(total_ids)
        <= PHOTO_LIVE_UPDATE_TARGET_PAYLOAD_BYTES
    ):
        return total_ids

    budget = PHOTO_LIVE_UPDATE_TARGET_PAYLOAD_BYTES - PHOTO_LIVE_UPDATE_JSON_BASE_BYTES
    by_bytes = max(1, budget // PHOTO_LIVE_UPDATE_BYTES_PER_ID)
    return max(
        PHOTO_LIVE_UPDATE_MIN_CHUNK_SIZE,
        min(PHOTO_LIVE_UPDATE_MAX_CHUNK_SIZE, by_bytes, total_ids),
    )


def iter_photo_live_update_id_chunks(unique_ids: list[int]) -> Iterator[list[int]]:
    """Iterate contiguous id slices for WebSocket fan-out.

    Chunk boundaries are determined by ``choose_photo_live_update_chunk_size``
    applied to ``len(unique_ids)``.

    Args:
        unique_ids: Ordered list of distinct attendance ids for one date.

    Yields:
        Slices of ``unique_ids`` of length up to the chosen chunk size. Yields
        nothing if ``unique_ids`` is empty.
    """
    n = len(unique_ids)
    if n == 0:
        return
    step = choose_photo_live_update_chunk_size(n)
    for start in range(0, n, step):
        yield unique_ids[start : start + step]


def sanitize_photo_group_name(name: str) -> str:
    """Make a string safe for use as a Django Channels group name.

    Replaces characters outside ``[a-zA-Z0-9_.-]`` with underscores and truncates
    to 100 characters.

    Args:
        name: Raw group name fragment (e.g. ``photos_2025-04-07``).

    Returns:
        Sanitized name suitable for ``group_add`` / ``group_send``.
    """
    return re.sub(r"[^a-zA-Z0-9_\\-\\.]", "_", name)[:100]


def broadcast_lesson_attendance_photo_meta_updates(
    updated_ids_by_date: dict[date, list[int]],
    *,
    log_prefix: str,
) -> None:
    """Invalidate photo list cache and schedule WebSocket meta updates after commit.

    For each calendar date in ``updated_ids_by_date``, deletes
    ``photos_for_{date}`` from cache, deduplicates ids, then registers a
    post-commit callback that sends one or more ``new_photo`` messages with
    ``stateCode`` ``UPDATED_META`` to the matching ``photos_{date}`` group.

    Args:
        updated_ids_by_date: Map from ``LessonAttendance.date_at`` to attendance
            primary keys that changed and should be reflected live.
        log_prefix: Short label prepended to warning logs on send failures
            (e.g. task or view name).
    """
    if not updated_ids_by_date:
        return

    for lesson_date in updated_ids_by_date:
        cache.delete(f"photos_for_{lesson_date}")

    snapshot: dict[date, list[int]] = {
        d: list(dict.fromkeys(ids)) for d, ids in updated_ids_by_date.items() if ids
    }
    if not snapshot:
        return

    def _do_broadcast() -> None:
        """Send chunked ``group_send`` payloads for the captured snapshot."""
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        version_ts = timezone.now().isoformat()
        for lesson_date, unique_ids in snapshot.items():
            if not unique_ids:
                continue
            group_name = sanitize_photo_group_name(f"photos_{lesson_date.isoformat()}")
            for chunk in iter_photo_live_update_id_chunks(unique_ids):
                payload: dict[str, Any] = {
                    "type": "new_photo",
                    "attendance_ids": chunk,
                    "op": "updated",
                    "stateCode": "UPDATED_META",
                    "versionTs": version_ts,
                }
                if len(chunk) == 1:
                    payload["attendance_id"] = chunk[0]
                try:
                    async_to_sync(channel_layer.group_send)(group_name, payload)
                except Exception as exc:
                    logger.warning(
                        "%s ws_broadcast_failed date=%s ids=%s error=%s",
                        log_prefix,
                        lesson_date.isoformat(),
                        chunk[:10],
                        exc,
                    )

    transaction.on_commit(_do_broadcast)
