from __future__ import annotations

import datetime
import logging
import time
from typing import cast

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Anti-spoof scan / backfill для LessonAttendance"

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            dest="scan_all",
            help="Сканировать весь архив (включая уже проверенные)",
        )
        parser.add_argument(
            "--force-checked",
            "--force-rescan",
            action="store_true",
            dest="force_checked",
            help=(
                "Принудительно пересканировать уже проверенные записи "
                "в рамках заданного фильтра (date/since-date/status/pks)."
            ),
        )
        parser.add_argument(
            "--status",
            choices=["pending", "clean", "review", "suspicious", "error"],
            help="Фильтр по текущему photo_spoof_status",
        )
        parser.add_argument(
            "--pks",
            type=str,
            default="",
            help="Список pk через запятую: --pks 1,2,3",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Размер батча (default: 200)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Запустить без сохранения результатов",
        )
        parser.add_argument(
            "--force-manual",
            action="store_true",
            help="Разрешить перескан записей с ручным override",
        )
        parser.add_argument(
            "--reset-manual-verdicts",
            action="store_true",
            dest="reset_manual_verdicts",
            help=(
                "Сбрасывать ручные вердикты (manual verdict/comment/by/at) "
                "до none для пересканированных записей."
            ),
        )
        parser.add_argument(
            "--device",
            choices=["auto", "cpu", "cuda"],
            default="auto",
            help="Устройство для PAD-движка",
        )
        parser.add_argument(
            "--max-records",
            type=int,
            default=200,
            help="Максимум записей за запуск (default: 200)",
        )
        parser.add_argument(
            "--date",
            type=str,
            default="",
            help="Сканировать только указанную дату YYYY-MM-DD (по date_at)",
        )
        parser.add_argument(
            "--since-date",
            type=str,
            default="",
            help="Сканировать записи начиная с даты YYYY-MM-DD (по date_at)",
        )

    def _parse_pks(self, raw: str) -> list[int]:
        if not raw:
            return []
        pks: list[int] = []
        for item in raw.split(","):
            value = item.strip()
            if not value:
                continue
            if not value.isdigit():
                raise CommandError(f"Некорректный pk: {value}")
            pks.append(int(value))
        return pks

    def _parse_since_date(self, raw: str) -> datetime.date | None:
        if not raw:
            return None
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError as exc:
            raise CommandError(
                "Неверный формат --since-date. Используй YYYY-MM-DD."
            ) from exc

    def _parse_exact_date(self, raw: str) -> datetime.date | None:
        if not raw:
            return None
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError as exc:
            raise CommandError("Неверный формат --date. Используй YYYY-MM-DD.") from exc

    def handle(self, *args, **options):
        from monitoring_app.models import LessonAttendance
        from monitoring_app.photo_pad import (
            MANUAL_NONE,
            PAD_MODEL_VERSION,
            check_photo,
            normalize_device,
        )

        pks = self._parse_pks(options["pks"])
        exact_date = self._parse_exact_date(options["date"])
        since_date = self._parse_since_date(options["since_date"])
        batch_size = max(1, int(options["batch_size"]))
        dry_run = bool(options["dry_run"])
        force_manual = bool(options["force_manual"])
        reset_manual_verdicts = bool(options["reset_manual_verdicts"])
        force_checked = bool(options["force_checked"])
        max_records = max(0, int(options["max_records"]))
        device = normalize_device(options["device"])

        if reset_manual_verdicts and not force_manual:
            force_manual = True
            self.stdout.write(
                self.style.WARNING(
                    "--reset-manual-verdicts включен: автоматически включаю --force-manual."
                )
            )

        if (
            force_checked
            and not options["scan_all"]
            and not pks
            and not options["status"]
            and exact_date is None
            and since_date is None
        ):
            raise CommandError(
                "Для --force-checked укажи --date/--since-date/--status/--pks "
                "или используй --all."
            )

        qs = LessonAttendance.objects.filter(staff_image_path__isnull=False).exclude(
            staff_image_path=""
        )

        if exact_date is not None:
            qs = qs.filter(date_at=exact_date)
        if since_date is not None:
            qs = qs.filter(date_at__gte=since_date)

        if pks:
            qs = qs.filter(pk__in=pks)
        elif options["scan_all"] or force_checked:
            pass
        elif options["status"]:
            qs = qs.filter(photo_spoof_status=options["status"])
        elif dry_run:
            if exact_date is None and since_date is None:
                qs = qs.filter(date_at=timezone.localdate())
        else:
            q_checked_null = cast(Q, Q(photo_spoof_checked_at__isnull=True))
            q_version_old = cast(Q, ~Q(photo_spoof_model_version=PAD_MODEL_VERSION))
            q_pending = cast(Q, Q(photo_spoof_status="pending"))
            rescan_q = cast(Q, cast(Q, q_checked_null | q_version_old) | q_pending)
            qs = qs.filter(rescan_q)
            if exact_date is None and since_date is None:
                qs = qs.filter(date_at=timezone.localdate())

        if not force_manual and not dry_run:
            qs = qs.filter(photo_manual_verdict=MANUAL_NONE)

        qs = qs.order_by("pk").only(
            "pk",
            "date_at",
            "staff_image_path",
            "photo_manual_verdict",
        )

        if max_records:
            records = list(qs[:max_records])
        else:
            records = list(qs)

        total = len(records)
        self.stdout.write(
            self.style.WARNING(
                "Кандидатов: "
                f"{total} | batch_size={batch_size} | dry_run={dry_run} "
                f"| force_manual={force_manual} | force_checked={force_checked} "
                f"| device={device} "
                f"| date={exact_date or (timezone.localdate() if since_date is None and not options['scan_all'] and not pks and not options['status'] else 'mixed')}"
            )
        )
        if total == 0:
            self.stdout.write("Нет кандидатов для сканирования.")
            return

        stats = {
            "checked": 0,
            "clean": 0,
            "review": 0,
            "suspicious": 0,
            "error": 0,
            "skipped_manual": 0,
            "manual_reset": 0,
        }
        elapsed_list: list[float] = []
        updated_ws_by_date: dict[datetime.date, list[int]] = {}

        for start in range(0, total, batch_size):
            batch = records[start : start + batch_size]
            for record in batch:
                if (
                    not dry_run
                    and not force_manual
                    and record.photo_manual_verdict != MANUAL_NONE
                ):
                    stats["skipped_manual"] += 1
                    continue

                image_path = record.staff_image_path
                if not image_path:
                    logger.warning(
                        "Skip PAD scan for pk=%s: empty staff_image_path",
                        record.pk,
                    )
                    stats["error"] += 1
                    stats["checked"] += 1
                    continue

                t0 = time.monotonic()
                try:
                    result = check_photo(image_path=image_path, device=device)
                except Exception as exc:
                    logger.exception(
                        "PAD scan failed for lesson attendance pk=%s path= %s error=%s",
                        record.pk,
                        image_path,
                        exc,
                    )
                    stats["error"] += 1
                    stats["checked"] += 1
                    elapsed_list.append(time.monotonic() - t0)
                    continue

                elapsed_list.append(time.monotonic() - t0)
                stats["checked"] += 1
                stats[result.status] = stats.get(result.status, 0) + 1

                if not dry_run:
                    update_kwargs = result.to_update_kwargs()
                    if (
                        reset_manual_verdicts
                        and record.photo_manual_verdict != MANUAL_NONE
                    ):
                        update_kwargs.update(
                            {
                                "photo_manual_verdict": MANUAL_NONE,
                                "photo_manual_comment": "",
                                "photo_manual_by_id": None,
                                "photo_manual_at": None,
                            }
                        )
                        stats["manual_reset"] += 1
                    rows = LessonAttendance.objects.filter(pk=record.pk).update(
                        **update_kwargs
                    )
                    if rows:
                        updated_ws_by_date.setdefault(record.date_at, []).append(
                            record.pk
                        )
                elif (
                    reset_manual_verdicts and record.photo_manual_verdict != MANUAL_NONE
                ):
                    stats["manual_reset"] += 1

                if result.status == "suspicious":
                    self.stdout.write(
                        self.style.ERROR(
                            f"SUSPICIOUS pk={record.pk} "
                            f"score={result.risk_score:.3f} "
                            f"tags={result.tags} "
                            f"path= {image_path}"
                        )
                    )

            avg_ms = (
                (sum(elapsed_list) / len(elapsed_list) * 1000.0)
                if elapsed_list
                else 0.0
            )
            self.stdout.write(
                "Прогресс: "
                f"{min(start + batch_size, total)}/{total} | "
                f"checked={stats['checked']} suspicious={stats['suspicious']} "
                f"review={stats['review']} error={stats['error']} avg={avg_ms:.0f}ms/фото"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Готово: "
                f"checked={stats['checked']} clean={stats['clean']} "
                f"review={stats['review']} suspicious={stats['suspicious']} "
                f"error={stats['error']} skipped_manual={stats['skipped_manual']} "
                f"manual_reset={stats['manual_reset']}"
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: изменения НЕ сохранены"))
        elif updated_ws_by_date:
            from monitoring_app.photo_ws_broadcast import (
                broadcast_lesson_attendance_photo_meta_updates,
            )

            broadcast_lesson_attendance_photo_meta_updates(
                updated_ws_by_date,
                log_prefix="scan_lesson_attendance_photos_cmd",
            )
