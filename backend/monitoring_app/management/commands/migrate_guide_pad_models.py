from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from monitoring_app.photo_pad import (
    _get_guide_color_model,
    _guide_model_modern_path,
    _load_guide_extra_trees_classifier,
    _runtime_cache,
    _runtime_cache_lock,
)


class Command(BaseCommand):
    help = (
        "Migrate legacy sklearn 0.19 guide YCrCb/Luv ExtraTrees pickles to "
        "sklearn 1.5+ joblib exports used by photo_pad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=("replay", "print", "all"),
            default="all",
            help="Which bundled guide model to migrate (default: all).",
        )

    def handle(self, *args: Any, **options: Any):
        from django.conf import settings

        models_root = Path(
            getattr(settings, "PHOTO_PAD_GUIDE_MODELS_ROOT", Path("models"))
        )
        names = {
            "replay": models_root / "replay-attack_ycrcb_luv_extraTreesClassifier.pkl",
            "print": models_root / "print-attack_ycrcb_luv_extraTreesClassifier.pkl",
        }
        selected = ("replay", "print") if options["model"] == "all" else (options["model"],)

        with _runtime_cache_lock:
            _runtime_cache.pop("guide_ycrcb_luv_extra_trees", None)
            _runtime_cache.pop("guide_sklearn_tree_unpickle_patch", None)
            _runtime_cache.pop("guide_ycrcb_luv_model_error", None)

        for key in selected:
            legacy = names[key]
            modern = _guide_model_modern_path(legacy)
            self.stdout.write(f"Migrating {legacy.name} -> {modern.name}")
            if not legacy.is_file():
                self.stdout.write(self.style.WARNING(f"  skip: missing {legacy}"))
                continue
            model = _load_guide_extra_trees_classifier(legacy)
            if modern.is_file():
                self.stdout.write(self.style.SUCCESS(f"  ok: {modern} ({model.__class__.__name__})"))
            else:
                self.stdout.write(self.style.ERROR(f"  failed to write {modern}"))

        probe = _get_guide_color_model()
        if probe is None:
            self.stdout.write(self.style.ERROR("Replay guide model still unavailable after migration."))
        else:
            self.stdout.write(self.style.SUCCESS("Replay guide model loads for PAD inference."))
