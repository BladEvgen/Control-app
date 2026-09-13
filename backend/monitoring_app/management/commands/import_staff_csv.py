import logging
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from monitoring_app.services import staff_csv_import

logger = logging.getLogger("django")


class Command(BaseCommand):
    help = (
        "Импортирует отделы и сотрудников из CSV-выгрузок СКУД. "
        "Отделы обрабатываются до сотрудников. Архивные сотрудники "
        "(archived_at заполнен) полностью пропускаются."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--departments",
            type=str,
            default=None,
            help="Путь к CSV с отделами (dep_*.csv).",
        )
        parser.add_argument(
            "--humans",
            type=str,
            default=None,
            help="Путь к CSV с сотрудниками (hum_*.csv).",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=staff_csv_import.DEFAULT_CHUNK_SIZE,
            help=(
                f"Размер чанка при обработке сотрудников (по умолчанию {staff_csv_import.DEFAULT_CHUNK_SIZE})."
            ),
        )
        parser.add_argument(
            "--merge-department",
            action="append",
            default=[],
            metavar="СТАРЫЙ=НОВЫЙ",
            help=(
                "Слить отдел со старым id в id из выгрузки. Можно указать "
                "несколько раз. По умолчанию уже применяется "
                f"{staff_csv_import.LEGACY_DEPARTMENT_ALIASES}."
            ),
        )
        parser.add_argument(
            "--archive-missing",
            action="store_true",
            help=(
                "Пометить archived_at у активных сотрудников, которых нет "
                "в выгрузке. Записи не удаляются. По умолчанию выключено."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Разрешить архивирование, даже если оно затрагивает больше "
                f"{staff_csv_import.ARCHIVE_GUARD_FRACTION:.0%} активных сотрудников."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Посчитать и напечатать все изменения, затем откатить транзакцию.",
        )

    def handle(self, *args, **options):
        departments_path = options.get("departments")
        humans_path = options.get("humans")
        if not departments_path and not humans_path:
            raise CommandError("Укажите --departments и/или --humans: импортировать нечего.")
        for label, path in (
            ("--departments", departments_path),
            ("--humans", humans_path),
        ):
            if path and not os.path.isfile(path):
                raise CommandError(f"{label}: файл не найден — {path}")

        try:
            aliases = staff_csv_import.parse_alias_args(options.get("merge_department") or [])
        except ValueError as error:
            raise CommandError(str(error)) from error

        dry_run = options.get("dry_run", False)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN: изменения будут откатены."))

        try:
            stats = staff_csv_import.run_import(
                departments_path=departments_path,
                humans_path=humans_path,
                chunk_size=options["chunk_size"],
                aliases=aliases,
                archive_missing=options.get("archive_missing", False),
                force=options.get("force", False),
                dry_run=dry_run,
                progress=self._progress,
            )
        except staff_csv_import.ImportAborted as error:
            raise CommandError(f"Импорт прерван: {error}") from error
        except KeyboardInterrupt:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Прервано (Ctrl+C), изменения откатены."))
            raise SystemExit(130)

        self.stdout.write("")
        for line in stats.summary_lines():
            self.stdout.write(line)
        for skipped in stats.rows_skipped[:20]:
            self.stdout.write(self.style.WARNING(f"  ! {skipped}"))
        if len(stats.rows_skipped) > 20:
            self.stdout.write(self.style.WARNING(f"  ... и ещё {len(stats.rows_skipped) - 20}"))
        self.stdout.write(self.style.SUCCESS("Готово."))

    def _progress(self, stage: str, processed: int, total: int) -> None:
        """Однострочный индикатор в stderr, чтобы не мешать выводу сводки."""
        if not sys.stderr.isatty():
            return
        sys.stderr.write(f"\r{stage}: {processed} / {total}   ")
        sys.stderr.flush()
        if total and processed >= total:
            sys.stderr.write("\n")
            sys.stderr.flush()
