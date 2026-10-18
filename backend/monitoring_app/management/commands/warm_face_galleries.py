"""Pre-build the face gallery cache for every searchable staff member.

Run after changing the face model or ``RUNTIME_GALLERY_CACHE_VERSION``: otherwise
the first 1:N search after a restart embeds every gallery on the fly.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q

from monitoring_app import ml, models

CHUNK = 250


class Command(BaseCommand):
    help = "Embed and cache runtime face galleries for all staff (after a model change)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--purge-stale",
            action="store_true",
            help="Delete cache files written by other RUNTIME_GALLERY_CACHE_VERSIONs.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        staff = list(
            models.Staff.objects.filter(
                Q(face_mask__isnull=False) | (Q(avatar__isnull=False) & ~Q(avatar=""))
            )
            .select_related("department", "face_mask")
            .order_by("pin")
        )
        started = time.monotonic()
        self.stdout.write(f"staff: {len(staff)}")
        for start in range(0, len(staff), CHUNK):
            ml.build_multi_staff_runtime_gallery_matrix(staff[start : start + CHUNK])
            done = min(start + CHUNK, len(staff))
            self.stdout.write(f"  {done}/{len(staff)}  {time.monotonic() - started:.0f}s")
        matrix, _owners = ml.build_multi_staff_runtime_gallery_matrix(staff)
        self.stdout.write(self.style.SUCCESS(f"search gallery ready: {matrix.shape[0]} templates"))

        if opts["purge_stale"]:
            suffix = f"_v{ml.RUNTIME_GALLERY_CACHE_VERSION}.npz"
            stale = [
                p
                for p in Path(ml._runtime_gallery_cache_dir()).glob("*.npz")
                if not p.name.endswith(suffix)
            ]
            for p in stale:
                p.unlink(missing_ok=True)
            self.stdout.write(f"removed {len(stale)} stale cache files")
