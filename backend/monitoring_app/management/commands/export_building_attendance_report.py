from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitoring_app.services import building_attendance_report


class Command(BaseCommand):
    help = (
        "Export Excel report for building attendance by departments using "
        "student-only attendance data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date-from",
            type=str,
            dest="date_from",
            help="Start date in YYYY-MM-DD format.",
        )
        parser.add_argument(
            "--date-to",
            type=str,
            dest="date_to",
            help="End date in YYYY-MM-DD format.",
        )
        parser.add_argument(
            "--days-with-data",
            type=int,
            default=building_attendance_report.DEFAULT_DAYS_WITH_DATA,
            dest="days_with_data",
            help=(
                "Number of latest dates with data when date range is not set "
                f"(default: {building_attendance_report.DEFAULT_DAYS_WITH_DATA})."
            ),
        )
        parser.add_argument(
            "--output",
            type=str,
            default="",
            dest="output",
            help="Output path for Excel file. If omitted, file is saved in current directory.",
        )

    def handle(self, *args, **options):
        try:
            params = building_attendance_report.parse_report_request_params(
                date_from_raw=options.get("date_from"),
                date_to_raw=options.get("date_to"),
                days_with_data_raw=options.get("days_with_data"),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        report_result = building_attendance_report.build_building_attendance_report_excel(
            date_from=params.date_from,
            date_to=params.date_to,
            days_with_data=params.days_with_data,
        )

        default_filename = building_attendance_report.build_report_filename(
            report_result.selected_dates
        )
        output_raw = str(options.get("output") or "").strip()
        output_path = self._resolve_output_path(
            output_raw=output_raw,
            default_filename=default_filename,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(report_result.excel_bytes)

        if report_result.selected_dates:
            self.stdout.write(
                self.style.SUCCESS(
                    "Building attendance report exported: "
                    f"{output_path} (dates={len(report_result.selected_dates)}, "
                    f"from={report_result.selected_dates[0]}, "
                    f"to={report_result.selected_dates[-1]})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Building attendance report exported with no data: "
                    f"{output_path}"
                )
            )

    def _resolve_output_path(self, *, output_raw: str, default_filename: str) -> Path:
        if not output_raw:
            # Default location: out/{generated_file_name}.xlsx
            return Path.cwd() / "out" / default_filename

        candidate = Path(output_raw)
        candidate_raw = str(output_raw)
        looks_like_dir = candidate_raw.endswith(("/", "\\")) or (
            candidate.exists() and candidate.is_dir()
        )
        if looks_like_dir:
            candidate = candidate / default_filename

        if candidate.suffix.lower() != ".xlsx":
            candidate = candidate.with_suffix(".xlsx")
        return candidate
