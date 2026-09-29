import asyncio
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from monitoring_app.attendance_fetcher import AsyncAttendanceFetcher


class Command(BaseCommand):
    help = (
        "Перевыгружает из API СКУД рабочие дни [--from, --to] с точными секундами и "
        "пересчитывает StaffAttendance. Запросов O(событий / 1000), кусками по --chunk-days. "
        "Дни без событий не пишутся — существующие записи (ручные, пробелы API) не затираются."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
        parser.add_argument("--to", dest="end", required=True, type=date.fromisoformat)
        parser.add_argument("--chunk-days", type=int, default=7)
        parser.add_argument("--concurrency", type=int, default=6)
        parser.add_argument("--pin", action="append", help="Только эти PIN (можно несколько).")

    def handle(self, *args, **options):
        start, end = options["start"], options["end"]
        if start > end:
            raise CommandError("--from позже --to")
        fetcher = AsyncAttendanceFetcher(max_concurrent_requests=options["concurrency"])
        summary = asyncio.run(
            fetcher.sync_range(
                start,
                end,
                options["pin"],
                chunk_days=options["chunk_days"],
                keep_existing_when_empty=True,
            )
        )
        summary.pop("errors", None)
        summary.pop("failed_pins", None)
        style = self.style.ERROR if summary["failed_chunks"] else self.style.SUCCESS
        self.stdout.write(style(str(summary)))
