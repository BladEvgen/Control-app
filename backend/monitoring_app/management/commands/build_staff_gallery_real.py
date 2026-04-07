from __future__ import annotations

import logging
import os

import numpy as np
from django.core.management.base import BaseCommand
from monitoring_app import models
from monitoring_app.ml import (
    _collect_readable_lesson_attendance_paths_for_staff,
    _collect_trusted_staff_face_sample_paths_for_staff,
    _dedupe_normalized_rows,
    _l2_normalize_embedding_rows,
    create_embeddings_from_images,
    load_arcface_model,
)

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        pin_filter = (options.get("pin") or "").strip()
        dry = bool(options.get("dry_run"))

        load_arcface_model()

        qs = models.Staff.objects.filter(avatar__isnull=False).exclude(avatar="")
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
                        self.style.WARNING(
                            f"[skip] {staff.pin}: файл аватара не найден"
                        )
                    )
                    skipped += 1
                    continue

                base_dir = os.path.dirname(ap)
                out_path = os.path.join(base_dir, f"{staff.pin}_gallery_real.npy")

                paths: list[str] = [ap]
                paths.extend(_collect_trusted_staff_face_sample_paths_for_staff(staff))
                paths.extend(_collect_readable_lesson_attendance_paths_for_staff(staff))
                seen: set[str] = set()
                uniq: list[str] = []
                for p in paths:
                    abs_p = os.path.abspath(p)
                    if abs_p in seen:
                        continue
                    seen.add(abs_p)
                    uniq.append(p)

                vecs = create_embeddings_from_images(uniq)
                if not vecs:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[skip] {staff.pin}: не удалось получить эмбеддинги"
                        )
                    )
                    skipped += 1
                    continue

                mat = np.asarray(vecs, dtype=np.float64)
                mat = _l2_normalize_embedding_rows(mat)
                mat = _dedupe_normalized_rows(mat, min_cos=0.999)

                if dry:
                    self.stdout.write(
                        f"[dry-run] {staff.pin}: {mat.shape[0]} прототипов -> {out_path}"
                    )
                else:
                    np.save(out_path, mat)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{staff.pin}: сохранено {mat.shape[0]} прототипов -> {out_path}"
                        )
                    )
                ok += 1
            except Exception as exc:
                logger.exception("build_staff_gallery_real: staff %s", staff.pin)
                self.stdout.write(self.style.ERROR(f"{staff.pin}: {exc}"))
                skipped += 1

        self.stdout.write(
            self.style.NOTICE(
                f"Готово: обработано успешно={ok}, пропуск/ошибка={skipped}"
            )
        )
