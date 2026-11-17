"""Выгрузка подозрительных LessonAttendance в XLSX и ZIP с фото.

Команда за один проход по данным формирует отчёт (отдел, ФИО, student_id/tutor_id,
дата, время, локация) и архив с фотографиями. Локация определяется по координатам
через LocationSearcher (Haversine). Пути к файлам фото разрешаются пакетно по
уникальным значениям staff_image_path, без повторных проходов по директориям.
"""

from __future__ import annotations

import datetime
import os
import zipfile
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from monitoring_app import models, utils

CIS_DATE_FORMAT = "%d.%m.%Y"


class _StubLocationSearcher:
    """Заглушка: всегда возвращает «Unknown Area» (нет локаций для Haversine)."""

    def find_nearest_locations_bulk(self, coordinates, *, radius=200):
        return [None] * len(coordinates)


class Command(BaseCommand):
    """Экспорт записей LessonAttendance с подозрительным фото в XLSX и ZIP.

    Формирует отчёт (отдел, ФИО, ID без S/T, дата СНГ, время локальное, локация)
    и рядом архив с фото: папки по дням (YYYY-MM-DD), имена файлов —
    staff_pin_ISO-время (двоеточия заменены на минус).
    """

    help = (
        "Export staff with suspicious LessonAttendance: FIO, pin (no S/T), "
        "department, date, location (from coordinates), time. Uses LocationSearcher (Haversine)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date-from",
            type=str,
            dest="date_from",
            help="Start date YYYY-MM-DD (inclusive).",
        )
        parser.add_argument(
            "--date-to",
            type=str,
            dest="date_to",
            help="End date YYYY-MM-DD (inclusive).",
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default="",
            dest="output",
            help="Output XLSX path. If omitted, writes to out/suspicious_attendance_<date>.xlsx.",
        )
        parser.add_argument(
            "--radius",
            type=int,
            default=200,
            dest="radius",
            help="Radius in meters for LocationSearcher.find_nearest (default: 200).",
        )

    def handle(self, *args, **options):
        """Запуск экспорта: фильтрация по датам, сбор строк и фото, запись XLSX и ZIP."""
        date_from, date_to = self._parse_dates(options.get("date_from"), options.get("date_to"))

        qs = (
            models.LessonAttendance.objects.filter(
                models.LessonAttendance.PHOTO_SUSPICIOUS_FOR_REPORTS_Q
            )
            .select_related("staff", "staff__department")
            .only(
                "id",
                "staff_id",
                "staff__pin",
                "staff__name",
                "staff__surname",
                "staff__department_id",
                "staff__department__id",
                "staff__department__name",
                "date_at",
                "first_in",
                "latitude",
                "longitude",
                "staff_image_path",
            )
            .order_by(
                "staff__department__name",
                "staff__department_id",
                "staff__surname",
                "staff__name",
                "date_at",
                "first_in",
                "pk",
            )
        )
        if date_from is not None:
            qs = qs.filter(date_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(date_at__lte=date_to)

        location_searcher = self._build_location_searcher()
        radius = int(options.get("radius") or 200)
        records = list(qs)
        coordinates = [
            (rec.latitude, rec.longitude)
            for rec in records
            if rec.latitude is not None and rec.longitude is not None
        ]
        nearest_locations = iter(
            location_searcher.find_nearest_locations_bulk(coordinates, radius=radius)
        )

        rows = []
        archive_records = []
        for rec in records:
            staff = rec.staff
            fio = self._fio(staff)
            staff_pin = utils.pin_to_external_format(staff.pin) if staff.pin else ""
            department_id = staff.department_id or ""
            department = staff.department.name if staff.department else "Без отдела"
            date_str = rec.date_at.strftime(CIS_DATE_FORMAT) if rec.date_at else ""
            if rec.latitude is not None and rec.longitude is not None:
                nearest = next(nearest_locations)
                location = str(nearest.get("name") or "Unknown Area") if nearest else "Unknown Area"
            else:
                location = ""
            if rec.first_in:
                local_first_in = timezone.localtime(rec.first_in)
                time_str = local_first_in.strftime("%H:%M:%S")
            else:
                time_str = ""
            rows.append(
                {
                    "lesson_attendance_id": rec.pk,
                    "department_id": department_id,
                    "department": department,
                    "fio": fio,
                    "student_id_tutor_id": staff_pin,
                    "date": date_str,
                    "time": time_str,
                    "location": location,
                    "status": "Аннулирована",
                }
            )
            if rec.staff_image_path and str(rec.staff_image_path).strip():
                archive_records.append((rec, staff_pin or "unknown"))

        output_path = (options.get("output") or "").strip()
        if not output_path:
            output_path = self._default_output_path()
        path = Path(output_path)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_xlsx(rows, path, date_from=date_from, date_to=date_to)
        zip_path = path.with_suffix(".zip")
        added = self._write_archive(archive_records, zip_path)
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(rows)} rows to {path} (UTF-8), archive {zip_path} ({added} photos)"
            )
        )

    def _parse_dates(self, date_from_raw, date_to_raw):
        """Парсит и валидирует даты из аргументов команды.

        Args:
            date_from_raw: Строка начала периода (YYYY-MM-DD) или None.
            date_to_raw: Строка конца периода (YYYY-MM-DD) или None.

        Returns:
            Кортеж (date_from, date_to); каждый элемент — date или None.

        Raises:
            CommandError: Неверный формат даты или date_from > date_to.
        """
        date_from = None
        date_to = None
        if date_from_raw:
            try:
                date_from = datetime.datetime.strptime(date_from_raw.strip(), "%Y-%m-%d").date()
            except ValueError as e:
                raise CommandError(f"Invalid --date-from, use YYYY-MM-DD: {e}") from e
        if date_to_raw:
            try:
                date_to = datetime.datetime.strptime(date_to_raw.strip(), "%Y-%m-%d").date()
            except ValueError as e:
                raise CommandError(f"Invalid --date-to, use YYYY-MM-DD: {e}") from e
        if date_from is not None and date_to is not None and date_from > date_to:
            raise CommandError("date_from must be <= date_to")
        return date_from, date_to

    def _fio(self, staff):
        """Собирает ФИО из полей surname и name.

        Args:
            staff: Экземпляр Staff.

        Returns:
            Строка вида "Фамилия Имя" или пустая строка.
        """
        parts = []
        if getattr(staff, "surname", None):
            parts.append(staff.surname)
        if getattr(staff, "name", None):
            parts.append(staff.name)
        return " ".join(parts).strip() or ""

    def _build_location_searcher(self):
        """Создаёт поисковик локаций по координатам ClassLocation (Haversine + KDTree).

        Всегда возвращает объект с методом find_nearest(lat, lon, radius): при наличии
        записей ClassLocation с координатами — utils.LocationSearcher (точный поиск
        по Haversine в заданном радиусе), иначе заглушку, возвращающую «Unknown Area».

        Returns:
            Экземпляр utils.LocationSearcher или _StubLocationSearcher.
        """
        locations = list(
            models.ClassLocation.objects.filter(
                latitude__isnull=False,
                longitude__isnull=False,
            ).values("name", "latitude", "longitude")
        )
        if not locations:
            self.stdout.write(
                self.style.WARNING(
                    "No ClassLocation with coordinates; location will be «Unknown Area»."
                )
            )
            return _StubLocationSearcher()
        try:
            return utils.LocationSearcher(locations)
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(
                    f"LocationSearcher init failed: {e}; using stub («Unknown Area»)."
                )
            )
            return _StubLocationSearcher()

    def _default_output_path(self) -> str:
        """Возвращает путь по умолчанию для XLSX (out/suspicious_attendance_<сегодня>.xlsx)."""
        today = timezone.localdate().isoformat()
        return str(Path.cwd() / "out" / f"suspicious_attendance_{today}.xlsx")

    def _resolve_photo_path_raw(self, raw_path: str) -> Optional[Path]:
        """Разрешает строковый путь к файлу фото в абсолютный Path.

        Проверяет: абсолютный путь, затем ATTENDANCE_ROOT и MEDIA_ROOT.
        Статические заглушки (/static/, no-avatar) игнорируются.

        Args:
            raw_path: Значение staff_image_path (относительный или абсолютный).

        Returns:
            Path к существующему файлу или None.
        """
        raw = (raw_path or "").strip()
        if not raw or "/static/" in raw or raw == "/static/media/images/no-avatar.png":
            return None
        p = Path(raw)
        if p.is_absolute() and p.exists():
            return p
        for root in (
            getattr(settings, "ATTENDANCE_ROOT", None),
            getattr(settings, "MEDIA_ROOT", None),
        ):
            if not root:
                continue
            candidate = Path(root) / raw.lstrip("/")
            if candidate.exists():
                return candidate
            candidate = Path(root) / p.name
            if candidate.exists():
                return candidate
        if not p.is_absolute():
            candidate = Path.cwd() / raw
            if candidate.exists():
                return candidate
        return None

    def _resolve_photo_paths_batch(self, path_strings: set[str]) -> dict[str, Optional[Path]]:
        """Разрешает множество путей к фото за один проход (без повторных обращений к ФС).

        Для каждого уникального staff_image_path вызывается _resolve_photo_path_raw
        один раз; результат кэшируется в словаре.

        Args:
            path_strings: Множество строк путей (значения staff_image_path).

        Returns:
            Словарь: ключ — исходная строка пути, значение — Path или None.
        """
        return {p: self._resolve_photo_path_raw(p) for p in path_strings}

    def _archive_arcname(self, rec, staff_pin_short: str, used: set) -> str:
        """Формирует имя файла в архиве: <день>/<staff_pin>_<ISO-время>.ext.

        Время в локальном часовом поясе, двоеточия заменены на минус.
        При коллизии добавляется суффикс _1, _2, ...

        Args:
            rec: Запись LessonAttendance.
            staff_pin_short: PIN без обёртки S/T.
            used: Множество уже занятых имён в архиве (модифицируется).

        Returns:
            Строка пути внутри ZIP (например, 2026-03-18/24254_2026-03-18T14-30-00.jpg).
        """
        day_dir = rec.date_at.strftime("%Y-%m-%d") if rec.date_at else "unknown"
        if rec.first_in:
            local_dt = timezone.localtime(rec.first_in)
            time_part = local_dt.strftime("%Y-%m-%dT%H-%M-%S")
        else:
            time_part = "no-time"
        base = f"{staff_pin_short}_{time_part}"
        ext = Path(rec.staff_image_path or "").suffix or ".jpg"
        if not ext.startswith("."):
            ext = "." + ext
        arcname = f"{day_dir}/{base}{ext}"
        suffix = 0
        while arcname in used:
            suffix += 1
            arcname = f"{day_dir}/{base}_{suffix}{ext}"
        used.add(arcname)
        return arcname

    def _write_archive(self, archive_records: list, zip_path: Path) -> int:
        """Создаёт ZIP с фото: папки по дням (YYYY-MM-DD), имена — staff_pin_ISO-время.

        Пути к файлам разрешаются один раз по множеству уникальных staff_image_path,
        затем каждая запись использует готовый результат из словаря.

        Args:
            archive_records: Список кортежей (LessonAttendance, staff_pin_short).
            zip_path: Куда записать ZIP-файл.

        Returns:
            Количество добавленных в архив файлов.
        """
        unique_paths = {rec.staff_image_path for rec, _ in archive_records if rec.staff_image_path}
        resolved = self._resolve_photo_paths_batch(unique_paths)

        added = 0
        used_arcnames: set[str] = set()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rec, staff_pin_short in archive_records:
                src = resolved.get(rec.staff_image_path) if rec.staff_image_path else None
                if not src or not src.is_file():
                    continue
                arcname = self._archive_arcname(rec, staff_pin_short, used_arcnames)
                try:
                    zf.write(os.fspath(src), arcname)
                    added += 1
                except (OSError, zipfile.LargeZipFile) as e:
                    self.stderr.write(self.style.WARNING(f"Skip photo {src}: {e}\n"))
        return added

    def _write_xlsx(self, rows, path: Path, *, date_from=None, date_to=None):
        """Пишет матрицу по людям/датам и лист с деталями подозрительных занятий."""
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Сводка"

        if date_from is not None and date_to is not None:
            dates = [
                (date_from + datetime.timedelta(days=offset)).strftime(CIS_DATE_FORMAT)
                for offset in range((date_to - date_from).days + 1)
            ]
        else:
            dates = sorted(
                {row["date"] for row in rows},
                key=lambda value: datetime.datetime.strptime(value, CIS_DATE_FORMAT),
            )
        grouped: dict[tuple[str, str, str, str], dict[str, int]] = {}
        for row in rows:
            person = (
                row["department"],
                row["department_id"],
                row["fio"],
                row["student_id_tutor_id"],
            )
            grouped.setdefault(person, {}).setdefault(row["date"], 0)
            grouped[person][row["date"]] += 1

        summary_headers = ["Код отдела", "Отдел", "ФИО", "ID", "Всего"] + dates
        self._write_header(ws, summary_headers)
        for row_idx, (person, day_counts) in enumerate(sorted(grouped.items()), start=2):
            department, department_id, fio, staff_id = person
            values = [department_id, department, fio, staff_id, sum(day_counts.values())]
            values.extend(self._summary_status(day_counts.get(day, 0)) for day in dates)
            for col_idx, value in enumerate(values, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if col_idx >= 6 and value:
                    cell.fill = PatternFill("solid", fgColor="FDE9D9")
                    cell.font = Font(color="9C0006", bold=True)

        self._finish_sheet(ws, summary_headers, freeze="F2")
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 34
        ws.column_dimensions["C"].width = 30
        ws.column_dimensions["D"].width = 16
        ws.column_dimensions["E"].width = 10
        for col_idx in range(6, len(summary_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 18

        details = wb.create_sheet("Suspicious")
        headers = [
            "ID записи",
            "Код отдела",
            "Отдел",
            "ФИО",
            "student_id / tutor_id",
            "Дата",
            "Время",
            "Локация",
            "Статус",
        ]
        self._write_header(details, headers)
        keys = [
            "lesson_attendance_id",
            "department_id",
            "department",
            "fio",
            "student_id_tutor_id",
            "date",
            "time",
            "location",
            "status",
        ]
        for row_idx, row in enumerate(rows, start=2):
            for col_idx, key in enumerate(keys, start=1):
                val = row.get(key, "")
                details.cell(row=row_idx, column=col_idx, value=val).alignment = Alignment(
                    vertical="center", wrap_text=True
                )
        self._finish_sheet(details, headers, freeze="A2")
        for column, width in zip("ABCDEFGHI", (12, 14, 34, 30, 20, 14, 12, 32, 18)):
            details.column_dimensions[column].width = width
        wb.save(path)

    @staticmethod
    def _summary_status(count):
        if not count:
            return ""
        return "Аннулирована" if count == 1 else f"Аннулирована ({count})"

    @staticmethod
    def _write_header(ws, headers):
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    @staticmethod
    def _finish_sheet(ws, headers, *, freeze):
        ws.freeze_panes = freeze
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 1)}"
        ws.row_dimensions[1].height = 32
        border = Border(bottom=Side(style="thin", color="B4C6E7"))
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.border = border
        if ws.max_row > 1:
            table = Table(
                displayName="SummaryTable" if ws.title == "Сводка" else "SuspiciousTable",
                ref=f"A1:{get_column_letter(len(headers))}{ws.max_row}",
            )
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showRowStripes=True,
                showFirstColumn=False,
                showLastColumn=False,
            )
            ws.add_table(table)
