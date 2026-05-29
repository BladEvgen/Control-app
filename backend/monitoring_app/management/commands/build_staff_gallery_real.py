from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Any, cast

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from monitoring_app import models
from monitoring_app.ml import (
    _collect_readable_lesson_attendance_paths_for_staff,
    _collect_trusted_staff_face_sample_paths_for_staff,
    _dedupe_normalized_rows,
    _l2_normalize_embedding_rows,
    create_vetted_gallery_embeddings_from_images,
    load_arcface_model,
)

logger = logging.getLogger(__name__)


def _compact_gallery_report_for_disk(report: Mapping[str, object]) -> dict[str, object]:
    """Keep meta JSON bounded; full PAD trace is not needed on disk."""
    accepted_limit = max(
        0, int(getattr(settings, "FACE_GALLERY_REAL_META_ACCEPTED_DETAIL_LIMIT", 48))
    )
    rejected_limit = max(
        0, int(getattr(settings, "FACE_GALLERY_REAL_META_REJECTED_DETAIL_LIMIT", 24))
    )
    accepted = report.get("accepted")
    rejected = report.get("rejected")
    accepted_rows = accepted if isinstance(accepted, list) else []
    rejected_rows = rejected if isinstance(rejected, list) else []

    def _compact_row(row: object) -> dict[str, object]:
        if not isinstance(row, Mapping):
            return {}
        out: dict[str, object] = {}
        for key in (
            "path",
            "source",
            "reasons",
            "quality_rank",
            "det_score",
            "face_area_ratio",
            "blur_laplacian_var",
            "brightness_mean",
            "pose_yaw",
            "pose_pitch",
            "pad_status",
            "pad_risk_score",
            "anchor_cosine",
            "centroid_cosine",
        ):
            if key in row:
                out[key] = row[key]
        return out

    return {
        "input_count": report.get("input_count", 0),
        "decoded_candidate_count": report.get("decoded_candidate_count", 0),
        "accepted_count": report.get("accepted_count", 0),
        "rejected_count": report.get("rejected_count", 0),
        "accepted_by_source": report.get("accepted_by_source", {}),
        "rejected_by_reason": report.get("rejected_by_reason", {}),
        "accepted_detail_count": min(len(accepted_rows), accepted_limit),
        "rejected_detail_count": min(len(rejected_rows), rejected_limit),
        "accepted_detail_truncated": max(0, len(accepted_rows) - accepted_limit),
        "rejected_detail_truncated": max(0, len(rejected_rows) - rejected_limit),
        "accepted": [_compact_row(row) for row in accepted_rows[:accepted_limit]],
        "rejected": [_compact_row(row) for row in rejected_rows[:rejected_limit]],
    }


class Command(BaseCommand):
    help = (
        "Строит или обновляет {pin}_gallery_real.npy рядом с аватаром сотрудника. "
        "Источники только реальные: файл аватара, доверенные StaffFaceSample, "
        "доверенные фото LessonAttendance (те же правила отбора, что для обучения). "
        "Без аугментации и без смешивания "
        "synthetic train embeddings (embeddings.npy)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pin",
            type=str,
            default="",
            help="Обработать только сотрудника с этим PIN.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Не записывать файлы, только отчёт.",
        )
        parser.add_argument(
            "--no-pad-validation",
            action="store_true",
            help=(
                "Не запускать PAD-проверку при сборке gallery_real.npy. "
                "Качество и consistency-фильтры останутся включены."
            ),
        )

    def handle(self, *args, **options):
        pin_filter = (options.get("pin") or "").strip()
        dry = bool(options.get("dry_run"))
        run_pad = not bool(options.get("no_pad_validation"))

        load_arcface_model()

        style = cast(Any, self.style)
        staff_manager = cast(Any, models.Staff).objects
        qs = staff_manager.filter(avatar__isnull=False).exclude(avatar="")
        if pin_filter:
            qs = qs.filter(pin=pin_filter)

        ok = 0
        skipped = 0

        for staff in qs.iterator(chunk_size=50):
            try:
                if not staff.avatar or not getattr(staff.avatar, "path", None):
                    skipped += 1
                    continue
                ap = staff.avatar.path
                if not os.path.isfile(ap):
                    self.stdout.write(
                        style.WARNING(f"[skip] {staff.pin}: файл аватара не найден")
                    )
                    skipped += 1
                    continue

                base_dir = os.path.dirname(ap)
                out_path = os.path.join(base_dir, f"{staff.pin}_gallery_real.npy")

                sources: list[dict[str, object]] = [
                    {"path": ap, "source": "avatar", "trusted": True}
                ]
                sources.extend(
                    {
                        "path": path,
                        "source": "staff_face_sample",
                        "trusted": True,
                    }
                    for path in _collect_trusted_staff_face_sample_paths_for_staff(
                        staff
                    )
                )
                sources.extend(
                    {
                        "path": path,
                        "source": "lesson_attendance",
                        "trusted": False,
                    }
                    for path in _collect_readable_lesson_attendance_paths_for_staff(
                        staff
                    )
                )
                seen: set[str] = set()
                uniq_sources: list[dict[str, object]] = []
                for src in sources:
                    p = str(src.get("path") or "")
                    abs_p = os.path.abspath(p)
                    if abs_p in seen:
                        continue
                    seen.add(abs_p)
                    uniq_sources.append({**src, "path": abs_p})

                vecs, report = create_vetted_gallery_embeddings_from_images(
                    uniq_sources,
                    use_tta=True,
                    run_pad=run_pad,
                )
                if not vecs:
                    self.stdout.write(
                        style.WARNING(
                            f"[skip] {staff.pin}: нет безопасных эмбеддингов "
                            f"(accepted=0, rejected={report.get('rejected_count')})"
                        )
                    )
                    skipped += 1
                    continue

                mat = np.asarray(vecs, dtype=np.float64)
                mat = _l2_normalize_embedding_rows(mat)
                mat = _dedupe_normalized_rows(mat, min_cos=0.999)

                if dry:
                    self.stdout.write(
                        f"[dry-run] {staff.pin}: {mat.shape[0]} прототипов "
                        f"(rejected={report.get('rejected_count')}) -> {out_path}"
                    )
                else:
                    np.save(out_path, mat)
                    meta_path = os.path.join(
                        base_dir, f"{staff.pin}_gallery_real_meta.json"
                    )
                    with open(meta_path, "w", encoding="utf-8") as fh:
                        json.dump(
                            {
                                "pin": str(staff.pin),
                                "output_path": out_path,
                                "prototypes": int(mat.shape[0]),
                                "report": _compact_gallery_report_for_disk(report),
                            },
                            fh,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    self.stdout.write(
                        style.SUCCESS(
                            f"{staff.pin}: сохранено {mat.shape[0]} прототипов "
                            f"(rejected={report.get('rejected_count')}) -> {out_path}"
                        )
                    )
                ok += 1
            except Exception as exc:
                logger.exception("build_staff_gallery_real: staff %s", staff.pin)
                self.stdout.write(style.ERROR(f"{staff.pin}: {exc}"))
                skipped += 1

        self.stdout.write(
            style.NOTICE(f"Готово: обработано успешно={ok}, пропуск/ошибка={skipped}")
        )
