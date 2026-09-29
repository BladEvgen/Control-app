import csv
import datetime
import io
import os
import tempfile
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from monitoring_app.models import ChildDepartment, ParentDepartment, Position, Staff
from monitoring_app.services import staff_csv_import

if TYPE_CHECKING:
    from django.contrib.auth.models import User
else:
    User = get_user_model()

DEP_HEADER = [
    ["Отдел", ""],
    [
        "Номер отдела",
        "Имя отдела",
        "Номер родительского отдела",
        "Название родительского отдела",
        "",
    ],
]
HUM_HEADER = [
    ["Сотрудник", ""],
    [
        "ID сотрудника",
        "Имя",
        "Фамилия",
        "Отдел №",
        "Имя отдела",
        "Название должности",
        "",
    ],
]


def write_csv(rows, header):
    """Пишет файл байт-в-байт как выгрузка: BOM, CRLF, кавычки вокруг всех полей."""
    handle, path = tempfile.mkstemp(suffix=".csv")
    os.close(handle)
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    for row in header + rows:
        writer.writerow(row)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        file.write(buffer.getvalue())
    return path


def dep_csv(rows):
    return write_csv(rows, DEP_HEADER)


def hum_csv(rows):
    return write_csv(rows, HUM_HEADER)


def run_task_eagerly(*args):
    """Запускает Celery-задачу синхронно, как это сделал бы воркер.

    ``.apply()``, а не прямой вызов: задача объявлена с ``bind=True`` и
    публикует прогресс через ``update_state``, которому нужен настоящий task_id.
    ``cast`` — потому что celery отдаёт ``@shared_task`` как ``Any | Proxy``,
    и у ``Proxy`` атрибут ``apply`` типизирован неверно.
    """
    from monitoring_app import tasks

    task = cast(Any, tasks.process_uploaded_file)
    return task.apply(args=args).get()


class CsvReadingTests(TestCase):
    def test_reads_utf8_bom_crlf_and_skips_two_header_rows(self):
        path = dep_csv([["1", "КРМУ", "", "", ""], ["2", "AUP", "1", "КРМУ", ""]])
        self.addCleanup(os.remove, path)

        rows = list(staff_csv_import.read_csv_rows(path, 4))

        self.assertEqual([row[0] for row in rows], ["1", "2"])
        self.assertEqual(rows[0][0], "1")
        self.assertEqual(rows[0][1], "КРМУ")

    def test_keeps_kazakh_and_mixed_alphabets(self):
        path = hum_csv([["S1S", "Әдемішке", "Өрікбаева", "9", "ЖҒД26 608 Қ б", "", ""]])
        self.addCleanup(os.remove, path)

        row = next(iter(staff_csv_import.read_csv_rows(path, 6)))

        self.assertEqual(row[1], "Әдемішке")
        self.assertEqual(row[2], "Өрікбаева")
        self.assertEqual(row[4], "ЖҒД26 608 Қ б")

    def test_short_rows_are_padded_not_raising(self):
        path = write_csv([["1", "КРМУ"]], DEP_HEADER)
        self.addCleanup(os.remove, path)

        row = next(iter(staff_csv_import.read_csv_rows(path, 4)))

        self.assertEqual(len(row), 4)
        self.assertEqual(row[2], "")


class PositionDerivationTests(TestCase):
    def test_derives_from_pin_pattern(self):
        cases = {
            "T900001T": staff_csv_import.POSITION_EMPLOYEE,
            "T900002T": staff_csv_import.POSITION_EMPLOYEE,
            "S900001S": staff_csv_import.POSITION_STUDENT,
            "V900001V": staff_csv_import.POSITION_OTHER,
            "O90000001": staff_csv_import.POSITION_OTHER,
            "L900001L": staff_csv_import.POSITION_OTHER,
            "U9U": staff_csv_import.POSITION_OTHER,
            "": staff_csv_import.POSITION_OTHER,
        }
        for pin, expected in cases.items():
            with self.subTest(pin=pin):
                self.assertEqual(staff_csv_import.derive_position_name(pin), expected)


class DepartmentImportTests(TestCase):
    def test_builds_tree_with_single_root_regardless_of_row_order(self):
        path = dep_csv(
            [
                ["100", "кафедра", "10", "факультет", ""],
                ["10", "факультет", "1", "КРМУ", ""],
                ["1", "КРМУ", "", "", ""],
            ]
        )
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(departments_path=path)

        self.assertEqual(stats.departments_created, 3)
        self.assertEqual(
            list(ChildDepartment.objects.filter(parent__isnull=True).values_list("id", flat=True)),
            ["1"],
        )
        self.assertEqual(ChildDepartment.objects.get(id="100").parent_id, "10")
        self.assertEqual(ChildDepartment.objects.get(id="10").parent_id, "1")

    def test_renames_and_reparents_existing_departments(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="10", name="старое имя", parent_id="1")
        ChildDepartment.objects.create(id="100", name="кафедра", parent_id="1")
        path = dep_csv(
            [
                ["1", "КРМУ", "", "", ""],
                ["10", "факультет", "1", "КРМУ", ""],
                ["100", "кафедра", "10", "факультет", ""],
            ]
        )
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(departments_path=path)

        self.assertEqual(ChildDepartment.objects.get(id="10").name, "факультет")
        self.assertEqual(ChildDepartment.objects.get(id="100").parent_id, "10")
        self.assertEqual(stats.departments_renamed, 1)
        self.assertEqual(stats.departments_reparented, 1)

    def test_departments_outside_csv_are_left_untouched(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="999", name="старая группа", parent_id="1")
        Staff.objects.create(pin="S999S", name="И", surname="И", department_id="999")
        path = dep_csv([["1", "КРМУ", "", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(departments_path=path)

        legacy = ChildDepartment.objects.get(id="999")
        self.assertEqual(legacy.name, "старая группа")
        self.assertEqual(legacy.parent_id, "1")
        self.assertEqual(Staff.objects.get(pin="S999S").department_id, "999")
        self.assertEqual(stats.departments_untouched, 1)


class LegacyDepartmentMergeTests(TestCase):
    def setUp(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="AUP", name="АУП")
        ChildDepartment.objects.create(id="10001", name="администрация", parent_id="AUP")
        ChildDepartment.objects.create(id="77", name="вне выгрузки", parent_id="AUP")
        ParentDepartment.objects.create(id="AUP", name="АУП")
        Staff.objects.create(pin="T900100T", name="И", surname="И", department_id="AUP")

    def test_merge_moves_children_staff_and_parent_row_then_drops_legacy(self):
        path = dep_csv(
            [
                ["1", "КРМУ", "", "", ""],
                ["2", "AUP", "1", "КРМУ", ""],
                ["10001", "администрация", "2", "AUP", ""],
            ]
        )
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(departments_path=path)

        self.assertFalse(ChildDepartment.objects.filter(id="AUP").exists())
        self.assertEqual(ChildDepartment.objects.get(id="10001").parent_id, "2")
        self.assertEqual(ChildDepartment.objects.get(id="77").parent_id, "2")
        self.assertEqual(Staff.objects.get(pin="T900100T").department_id, "2")
        self.assertFalse(ParentDepartment.objects.filter(id="AUP").exists())
        self.assertEqual(ParentDepartment.objects.get(id="2").name, "AUP")
        self.assertEqual(len(stats.departments_merged), 1)

    def test_merge_aborts_and_rolls_back_when_target_missing(self):
        path = dep_csv([["1", "КРМУ", "", "", ""]])
        self.addCleanup(os.remove, path)

        with self.assertRaises(staff_csv_import.ImportAborted):
            staff_csv_import.run_import(departments_path=path)

        self.assertTrue(ChildDepartment.objects.filter(id="AUP").exists())
        self.assertEqual(ChildDepartment.objects.get(id="10001").parent_id, "AUP")
        self.assertEqual(Staff.objects.get(pin="T900100T").department_id, "AUP")


class StaffImportTests(TestCase):
    def setUp(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="2", name="AUP", parent_id="1")
        ChildDepartment.objects.create(id="9451", name="ЖҒД26 608 Қ б", parent_id="1")

    def test_creates_staff_and_assigns_position_derived_from_pin(self):
        path = hum_csv(
            [
                ["T900001T", "Тестбек", "Тестбеков", "2", "AUP", "", ""],
                ["S900001S", "Пробамир", "Пробаев", "9451", "ЖҒД26 608 Қ б", "", ""],
                ["V900001V", "Гость", "Гостев", "2", "AUP", "", ""],
            ]
        )
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path)

        self.assertEqual(stats.staff_created, 3)
        self.assertEqual(
            [p.name for p in Staff.objects.get(pin="T900001T").positions.all()],
            [staff_csv_import.POSITION_EMPLOYEE],
        )
        self.assertEqual(
            [p.name for p in Staff.objects.get(pin="S900001S").positions.all()],
            [staff_csv_import.POSITION_STUDENT],
        )
        self.assertEqual(
            [p.name for p in Staff.objects.get(pin="V900001V").positions.all()],
            [staff_csv_import.POSITION_OTHER],
        )
        self.assertEqual(
            str(Position.objects.get(name=staff_csv_import.POSITION_OTHER).rate),
            "0.00",
        )

    def test_position_is_replaced_not_added(self):
        staff = Staff.objects.create(pin="S1S", name="И", surname="И", department_id="9451")
        old = Position.objects.create(name="Старая должность")
        staff.positions.add(old)
        path = hum_csv([["S1S", "И", "И", "9451", "ЖҒД26 608 Қ б", "", ""]])
        self.addCleanup(os.remove, path)

        staff_csv_import.run_import(humans_path=path)

        self.assertEqual(
            [p.name for p in staff.positions.all()],
            [staff_csv_import.POSITION_STUDENT],
        )

    def test_updates_name_surname_and_department(self):
        Staff.objects.create(pin="T900100T", name="Старое", surname="Имя", department_id="2")
        path = hum_csv([["T900100T", "Новое", "Фамилия", "9451", "ЖҒД26 608 Қ б", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path)

        staff = Staff.objects.get(pin="T900100T")
        self.assertEqual(
            (staff.name, staff.surname, staff.department_id),
            ("Новое", "Фамилия", "9451"),
        )
        self.assertEqual(stats.staff_updated, 1)

    def test_blank_name_does_not_overwrite_existing_value(self):
        Staff.objects.create(pin="T900100T", name="Тестбек", surname="Тестбеков", department_id="2")
        path = hum_csv([["T900100T", "", "", "2", "AUP", "", ""]])
        self.addCleanup(os.remove, path)

        staff_csv_import.run_import(humans_path=path)

        staff = Staff.objects.get(pin="T900100T")
        self.assertEqual((staff.name, staff.surname), ("Тестбек", "Тестбеков"))

    def test_unknown_department_creates_stub_instead_of_null(self):
        path = hum_csv([["T900100T", "И", "И", "55555", "Неизвестный", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path)

        staff = Staff.objects.get(pin="T900100T")
        self.assertEqual(staff.department_id, "55555")
        self.assertEqual(stats.department_stubs_created, 1)
        self.assertEqual(
            ChildDepartment.objects.get(id="55555").parent_id,
            staff_csv_import.ROOT_DEPARTMENT_ID,
        )

    def test_existing_staff_keeps_department_when_csv_department_unknown(self):
        Staff.objects.create(pin="T900100T", name="И", surname="И", department_id="2")
        path = hum_csv([["T900100T", "И", "И", "55555", "Неизвестный", "", ""]])
        self.addCleanup(os.remove, path)

        staff_csv_import.run_import(humans_path=path)

        self.assertEqual(Staff.objects.get(pin="T900100T").department_id, "2")
        self.assertFalse(ChildDepartment.objects.filter(id="55555").exists())

    def test_explicit_position_column_wins_over_pin_pattern(self):
        path = hum_csv([["S1S", "И", "И", "9451", "гр", "Ассистент кафедры", ""]])
        self.addCleanup(os.remove, path)

        staff_csv_import.run_import(humans_path=path)

        self.assertEqual(
            [p.name for p in Staff.objects.get(pin="S1S").positions.all()],
            ["Ассистент кафедры"],
        )

    def test_chunking_does_not_change_result(self):
        rows = [
            [f"S{index}S", f"Имя{index}", f"Фам{index}", "9451", "гр", "", ""]
            for index in range(25)
        ]
        path = hum_csv(rows)
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path, chunk_size=4)

        self.assertEqual(stats.staff_created, 25)
        self.assertEqual(Staff.objects.count(), 25)
        self.assertEqual(stats.positions_assigned, 25)


class ArchivedStaffTests(TestCase):
    def setUp(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="2", name="AUP", parent_id="1")
        ChildDepartment.objects.create(id="9451", name="группа", parent_id="1")

    def test_archive_missing_marks_but_does_not_delete(self):
        Staff.objects.create(pin="T900100T", name="И", surname="И", department_id="2")
        Staff.objects.create(pin="T2T", name="У", surname="У", department_id="2")
        path = hum_csv([["T900100T", "И", "И", "2", "AUP", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path, archive_missing=True)

        self.assertEqual(stats.staff_archived, 1)
        self.assertTrue(Staff.all_objects.filter(pin="T2T").exists())
        self.assertIsNotNone(Staff.all_objects.get(pin="T2T").archived_at)

    def test_archived_staff_hidden_from_default_manager_only(self):
        Staff.all_objects.create(
            pin="T9T",
            name="И",
            surname="И",
            department_id="2",
            archived_at=timezone.now(),
        )

        self.assertFalse(Staff.objects.filter(pin="T9T").exists())
        self.assertTrue(Staff.all_objects.filter(pin="T9T").exists())

    def test_archived_staff_is_frozen_and_skipped_by_import(self):
        staff = Staff.all_objects.create(
            pin="T9T",
            name="Старое",
            surname="Имя",
            department_id="2",
            archived_at=timezone.now(),
        )
        old_position = Position.objects.create(name="Старая должность")
        staff.positions.add(old_position)
        path = hum_csv([["T9T", "Новое", "Фамилия", "9451", "группа", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path)

        refreshed = Staff.all_objects.get(pin="T9T")
        self.assertEqual((refreshed.name, refreshed.surname), ("Старое", "Имя"))
        self.assertEqual(refreshed.department_id, "2")
        self.assertIsNotNone(refreshed.archived_at)
        self.assertEqual([p.name for p in refreshed.positions.all()], ["Старая должность"])
        self.assertEqual(stats.staff_skipped_archived, 1)
        self.assertEqual(stats.staff_created, 0)

    def test_archive_guard_blocks_partial_export_without_force(self):
        for index in range(10):
            Staff.objects.create(pin=f"T{index}T", name="И", surname="И", department_id="2")
        path = hum_csv([["T0T", "И", "И", "2", "AUP", "", ""]])
        self.addCleanup(os.remove, path)

        with self.assertRaises(staff_csv_import.ImportAborted):
            staff_csv_import.run_import(humans_path=path, archive_missing=True)

        self.assertEqual(Staff.objects.count(), 10)

    def test_archive_guard_can_be_overridden_by_force(self):
        for index in range(10):
            Staff.objects.create(pin=f"T{index}T", name="И", surname="И", department_id="2")
        path = hum_csv([["T0T", "И", "И", "2", "AUP", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path, archive_missing=True, force=True)

        self.assertEqual(stats.staff_archived, 9)
        self.assertEqual(Staff.all_objects.count(), 10)


class DryRunTests(TestCase):
    def test_dry_run_reports_changes_but_writes_nothing(self):
        path = dep_csv([["1", "КРМУ", "", "", ""], ["10", "факультет", "1", "КРМУ", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(departments_path=path, dry_run=True)

        self.assertEqual(stats.departments_created, 2)
        self.assertTrue(stats.dry_run)
        self.assertEqual(ChildDepartment.objects.count(), 0)


class InvariantTests(TestCase):
    def test_import_never_leaves_staff_without_department(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="2", name="AUP", parent_id="1")
        Staff.objects.create(pin="T900100T", name="И", surname="И", department_id="2")
        path = hum_csv([["T900100T", "И", "И", "", "", "", ""]])
        self.addCleanup(os.remove, path)

        stats = staff_csv_import.run_import(humans_path=path)

        self.assertEqual(Staff.objects.get(pin="T900100T").department_id, "2")
        self.assertEqual(stats.invariants["staff_without_department_after"], 0)

    def test_second_root_in_csv_aborts_import(self):
        path = dep_csv([["1", "КРМУ", "", "", ""], ["5", "Сирота", "", "", ""]])
        self.addCleanup(os.remove, path)

        with self.assertRaises(staff_csv_import.ImportAborted):
            staff_csv_import.run_import(departments_path=path)

        self.assertEqual(ChildDepartment.objects.count(), 0)


class AliasParsingTests(TestCase):
    def test_parses_pairs(self):
        self.assertEqual(
            staff_csv_import.parse_alias_args(["AUP=2", " OLD = 7 "]),
            {"AUP": "2", "OLD": "7"},
        )

    def test_rejects_malformed(self):
        for value in ("AUP", "=2", "AUP="):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    staff_csv_import.parse_alias_args([value])


class UploadTaskTests(TestCase):
    """Задача Celery, вызванная синхронно: та же логика, что в воркере."""

    def setUp(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="2", name="AUP", parent_id="1")

    def test_staff_category_imports_and_removes_temp_file(self):
        path = hum_csv([["T900100T", "Тестбек", "Тестбеков", "2", "AUP", "", ""]])

        result = run_task_eagerly(path, "staff", {})

        self.assertEqual(result["category"], "staff")
        self.assertEqual(result["detail"]["staff"]["created"], 1)
        self.assertTrue(Staff.objects.filter(pin="T900100T").exists())
        self.assertFalse(os.path.exists(path))

    def test_temp_file_removed_even_when_task_fails(self):
        path = hum_csv([["T900100T", "И", "И", "2", "AUP", "", ""]])

        with self.assertRaises(ValueError):
            run_task_eagerly(path, "несуществующая_категория", {})

        self.assertFalse(os.path.exists(path))

    def test_lock_prevents_two_imports_of_same_category(self):
        from django.core.cache import cache

        from monitoring_app import tasks

        cache.delete(tasks.upload_lock_key("staff"))
        self.addCleanup(cache.delete, tasks.upload_lock_key("staff"))
        self.assertTrue(tasks.acquire_upload_lock("staff"))

        path = hum_csv([["T900100T", "И", "И", "2", "AUP", "", ""]])
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        with self.assertRaises(RuntimeError):
            run_task_eagerly(path, "staff", {})

        self.assertTrue(os.path.exists(path))


class PhotoZipTests(TestCase):
    def setUp(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        self.staff = Staff.objects.create(pin="T900100T", name="И", surname="И", department_id="1")

    def _zip(self, members):
        import zipfile

        handle, path = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in members:
                archive.writestr(name, payload)
        return path

    def test_rejects_zip_slip_and_non_image_members(self):
        from monitoring_app.services import upload_processing

        path = self._zip(
            [
                ("../../etc/passwd", b"root:x:0:0"),
                ("notes.txt", b"text"),
                ("T900100T.jpg", b"\xff\xd8\xff\xe0jpegbytes"),
            ]
        )
        self.addCleanup(os.remove, path)

        result = upload_processing.import_photos_zip(path)

        self.assertEqual(result["skipped_bad_member"], 2)
        self.assertEqual(result["updated"], 1)
        self.assertFalse(os.path.exists("/tmp/etc/passwd"))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.avatar)

    def test_unknown_pin_is_counted_not_fatal(self):
        from monitoring_app.services import upload_processing

        path = self._zip([("НЕТ_ТАКОГО.jpg", b"\xff\xd8\xff\xe0")])
        self.addCleanup(os.remove, path)

        result = upload_processing.import_photos_zip(path)

        self.assertEqual(result["skipped_unknown_pin"], 1)
        self.assertEqual(result["updated"], 0)

    def test_archived_staff_photo_is_not_replaced(self):
        from monitoring_app.services import upload_processing

        Staff.all_objects.filter(pin="T900100T").update(archived_at=timezone.now())
        path = self._zip([("T900100T.jpg", b"\xff\xd8\xff\xe0")])
        self.addCleanup(os.remove, path)

        result = upload_processing.import_photos_zip(path)

        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped_unknown_pin"], 1)


class UploadViewTests(TestCase):
    def setUp(self):
        from monitoring_app.models import FileCategory

        FileCategory.objects.create(name="Сотрудники", slug="staff")
        self.user = User.objects.create_user(username="uploader", password="pass12345")

    def test_anonymous_post_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(
            "/upload/",
            {
                "category": "staff",
                "file": SimpleUploadedFile("hum.csv", b"x", content_type="text/csv"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login_view/", response["Location"])
        self.assertFalse(Staff.objects.exists())

    def test_wrong_extension_is_rejected_before_enqueue(self):
        from unittest.mock import patch

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.user)
        with patch("monitoring_app.tasks.process_uploaded_file.delay") as delay:
            response = self.client.post(
                "/upload/",
                {
                    "category": "staff",
                    "file": SimpleUploadedFile("photos.zip", b"PK", "application/zip"),
                },
            )

        self.assertEqual(response.status_code, 302)
        delay.assert_not_called()

    def test_valid_upload_is_enqueued_and_not_processed_inline(self):
        from unittest.mock import patch

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.user)
        payload = '"Сотрудник",\r\n"ID","Имя","Фамилия","Отдел","Имя отдела","Должность",\r\n'
        with patch("monitoring_app.tasks.process_uploaded_file.delay") as delay:
            delay.return_value.id = "task-123"
            response = self.client.post(
                "/upload/",
                {
                    "category": "staff",
                    "file": SimpleUploadedFile(
                        "hum.csv", payload.encode("utf-8-sig"), content_type="text/csv"
                    ),
                },
            )

        self.assertEqual(response.status_code, 302)
        delay.assert_called_once()
        stored_path, category, options = delay.call_args[0]
        self.addCleanup(lambda: os.path.exists(stored_path) and os.remove(stored_path))
        self.assertEqual(category, "staff")
        self.assertTrue(os.path.exists(stored_path), "файл должен лежать на диске")
        self.assertIn("archive_missing", options)
        self.assertEqual(self.client.session["upload_task_id"], "task-123")

    def test_status_endpoint_requires_auth(self):
        response = self.client.get("/upload/status/task-123/")
        self.assertEqual(response.status_code, 403)

    def test_status_endpoint_reports_state(self):
        self.client.force_login(self.user)
        response = self.client.get("/upload/status/task-123/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "task-123")


class AttendanceFetcherAggregationTests(TestCase):
    """Новый путь фетчера: агрегация на лету + запись по id-картам."""

    def setUp(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        self.staff = Staff.objects.create(
            pin="T900300T", name="Тестбек", surname="Тестбеков", department_id="1"
        )
        Staff.all_objects.create(
            pin="T900301T",
            name="Пробамир",
            surname="Пробаев",
            department_id="1",
            archived_at=timezone.now(),
        )

    def test_archived_pins_are_not_fetched(self):
        from monitoring_app import models as m

        pins = list(m.Staff.objects.values_list("pin", flat=True))

        self.assertIn("T900300T", pins)
        self.assertNotIn("T900301T", pins)

    WORK_DAY = datetime.date(2026, 3, 10)

    def _events(self, *items):
        return [
            {"eventTime": f"2026-03-10 {hhmmss}", "devSn": sn, "areaName": area}
            for hhmmss, sn, area in items
        ]

    def _save(self, result, mode="turnstile"):
        from monitoring_app.attendance_fetcher import save_attendance_days

        return save_attendance_days({self.WORK_DAY: {self.staff.id: result}}, mode)

    def test_empty_events_still_produce_a_row(self):
        from monitoring_app.attendance_fetcher import compute_day
        from monitoring_app.models import StaffAttendance

        result = self._save(compute_day([]))

        self.assertEqual(result["created_records"], 1)
        record = StaffAttendance.objects.get(staff=self.staff)
        self.assertEqual(record.date_at, datetime.date(2026, 3, 11))
        self.assertIsNone(record.first_in)
        self.assertEqual(record.area_name_in, "Unknown")

    def test_second_run_updates_instead_of_duplicating(self):
        from monitoring_app.attendance_fetcher import compute_day
        from monitoring_app.models import StaffAttendance

        self._save(compute_day([]))
        events = self._events(
            ("09:00:00", "CN3R230260002", "Вход"), ("10:00:00", "CN3R230260001", "Выход")
        )
        result = self._save(compute_day(events))

        self.assertEqual(result, {"created_records": 0, "updated_records": 1})
        self.assertEqual(StaffAttendance.objects.count(), 1)
        record = StaffAttendance.objects.get(staff=self.staff)
        self.assertEqual(record.effective_work_seconds, 3600)
        self.assertEqual(record.area_name_in, "Вход")

    def test_report_mode_switch_is_single_update_without_api(self):
        from monitoring_app.attendance_fetcher import apply_report_mode, compute_day
        from monitoring_app.models import StaffAttendance

        events = self._events(
            ("09:00:05", "CN3R230260002", "АБЫЛАЙХАНА"),
            ("18:00:07", "CN3R230260001", "АБЫЛАЙХАНА"),
            ("19:30:09", "CJKT220360027", "лифт4"),
        )
        self._save(compute_day(events), mode="turnstile")
        record = StaffAttendance.objects.get(staff=self.staff)
        self.assertEqual(timezone.localtime(record.last_out).strftime("%H:%M:%S"), "18:00:07")
        self.assertEqual(len(record.area_sequence), 3)

        with self.assertNumQueries(1):  # смена режима — один UPDATE
            self.assertEqual(apply_report_mode(mode="all"), 1)
        record.refresh_from_db()
        self.assertEqual(timezone.localtime(record.first_in).strftime("%H:%M:%S"), "09:00:05")
        self.assertEqual(timezone.localtime(record.last_out).strftime("%H:%M:%S"), "19:30:09")
        self.assertEqual(record.area_name_out, "лифт4")
        self.assertEqual(record.effective_work_seconds, 9 * 3600 + 2)
        self.assertEqual(len(record.effective_work_intervals), 1)

        apply_report_mode(mode="turnstile")
        record.refresh_from_db()
        self.assertEqual(timezone.localtime(record.last_out).strftime("%H:%M:%S"), "18:00:07")
        self.assertEqual(record.area_name_out, "АБЫЛАЙХАНА")

    def test_report_mode_without_turnstile_nulls_report_columns(self):
        from monitoring_app.attendance_fetcher import apply_report_mode, compute_day
        from monitoring_app.models import StaffAttendance

        self._save(compute_day(self._events(("09:00:00", "CJKT220360027", "лифт4"))), "all")
        apply_report_mode(mode="turnstile")

        record = StaffAttendance.objects.get(staff=self.staff)
        self.assertIsNone(record.first_in)
        self.assertIsNone(record.last_out)
        self.assertIsNone(record.effective_work_seconds)
        self.assertFalse(record.effective_work_intervals)

    def _run_migration_0021(self):
        import importlib

        from django.apps import apps

        importlib.import_module("monitoring_app.migrations.0021_rebuild_attendance_report").rebuild(
            apps, None
        )

    def test_migration_0021_same_event_day_never_has_last_out_before_first_in(self):
        # Ли Александр 28.09.2026: единственный турникет 16:22, дальше только лифты.
        from monitoring_app.models import StaffAttendance

        first_in = timezone.make_aware(datetime.datetime(2026, 3, 10, 16, 22, 37))
        record = StaffAttendance.objects.create(
            staff=self.staff,
            date_at=datetime.date(2026, 3, 11),
            first_in=first_in,
            last_out=timezone.make_aware(datetime.datetime(2026, 3, 10, 17, 53, 53)),
            area_sequence=[
                {"t": "16:22", "area": "АБЫЛАЙХАНА", "devSn": "CN3R230260002"},
                {"t": "16:28", "area": "лифт7", "devSn": "CJKT214260022"},
                {"t": "17:53", "area": "лифт7", "devSn": "CJKT214260022"},
            ],
        )

        self._run_migration_0021()

        record.refresh_from_db()
        self.assertEqual(record.first_in, first_in)
        # Единственный турникет — вход: только приход, ухода по турникету нет.
        self.assertIsNone(record.last_out)

    def test_migration_0021_backfills_legacy_rows_from_area_sequence(self):
        from monitoring_app.attendance_fetcher import apply_report_mode
        from monitoring_app.models import StaffAttendance

        first_in = timezone.make_aware(datetime.datetime(2026, 3, 10, 7, 5, 1))
        record = StaffAttendance.objects.create(
            staff=self.staff,
            date_at=datetime.date(2026, 3, 11),
            first_in=first_in,
            last_out=timezone.make_aware(datetime.datetime(2026, 3, 10, 15, 43, 39)),
            area_sequence=[
                {"t": "07:05", "area": "АБЫЛАЙХАНА", "devSn": "CN3R230260010"},
                {"t": "15:43", "area": "ЦОС", "devSn": "QJT3244400440"},
                {"t": "17:07", "area": "АБЫЛАЙХАНА", "devSn": "CN3R230260001"},
            ],
        )

        self._run_migration_0021()
        apply_report_mode(mode="all")

        record.refresh_from_db()
        self.assertEqual(record.first_in, first_in)  # секунды сохранены
        self.assertEqual(timezone.localtime(record.last_out).strftime("%H:%M"), "17:07")
        self.assertEqual(record.effective_work_seconds, 10 * 3600 + 2 * 60)
        self.assertEqual(set(record.report_variants), {"all", "turnstile"})
        self.assertEqual(record.area_sequence[1].get("exit_resolution"), "bridge_transfer")
        self.assertNotIn("is_exit", record.area_sequence[1])

    def test_fetch_window_splits_full_windows_instead_of_paging(self):
        import asyncio
        from unittest.mock import patch

        from monitoring_app.attendance_fetcher import AsyncAttendanceFetcher

        # 7 событий по часам; страница = 3 → окно делится, пока не станет < 3.
        stamps = [datetime.datetime(2026, 3, 10, h, 0, 0) for h in range(8, 15)]
        calls = []

        async def fake_get(_self, params):
            calls.append(params)
            start = datetime.datetime.fromisoformat(params["startDate"])
            end = datetime.datetime.fromisoformat(params["endDate"])
            hits = [{"id": str(t), "eventTime": str(t)} for t in stamps if start <= t <= end]
            return hits[:3]

        with (
            patch.object(AsyncAttendanceFetcher, "PAGE_SIZE", 3),
            patch.object(AsyncAttendanceFetcher, "_get", fake_get),
        ):
            events = asyncio.run(
                AsyncAttendanceFetcher().fetch_window(
                    datetime.datetime(2026, 3, 10), datetime.datetime(2026, 3, 10, 23, 59, 59)
                )
            )

        self.assertEqual(sorted(e["id"] for e in events), sorted(str(t) for t in stamps))
        self.assertTrue(all(p["pageNo"] == "1" for p in calls))

    def test_unknown_pin_is_skipped_without_error(self):
        from monitoring_app.attendance_fetcher import save_attendance_days
        from monitoring_app.models import StaffAttendance

        self.assertEqual(
            save_attendance_days({}, "all"), {"created_records": 0, "updated_records": 0}
        )
        self.assertEqual(StaffAttendance.objects.count(), 0)


class DepartmentSubtreeTests(TestCase):
    def test_subtree_ids_returns_whole_branch_in_one_query(self):
        ChildDepartment.objects.create(id="1", name="КРМУ")
        ChildDepartment.objects.create(id="10", name="факультет", parent_id="1")
        ChildDepartment.objects.create(id="100", name="кафедра", parent_id="10")
        ChildDepartment.objects.create(id="200", name="другая ветка", parent_id="1")

        root = ChildDepartment.objects.get(id="1")

        self.assertEqual(sorted(root.subtree_ids()), ["1", "10", "100", "200"])
        self.assertEqual(sorted(root.subtree_ids(include_self=False)), ["10", "100", "200"])
        self.assertEqual(
            sorted(d.id for d in root.get_all_child_departments()),
            ["10", "100", "200"],
        )


class AttendanceSyncRangeTests(TransactionTestCase):
    """sync_range пишет в БД из потоков database_sync_to_async — нужна настоящая фиксация."""

    def setUp(self):
        from monitoring_app.models import AttendanceSettings

        AttendanceSettings.load()
        ChildDepartment.objects.create(id="1", name="КРМУ")
        self.staff = Staff.objects.create(
            pin="T900300T", name="Тестбек", surname="Тестбеков", department_id="1"
        )

    def _sync(self, events, **kwargs):
        import asyncio
        from unittest.mock import patch

        from monitoring_app.attendance_fetcher import AsyncAttendanceFetcher

        calls = []

        async def fake_fetch(_self, start_day, end_day, pins):
            calls.append((start_day, end_day))
            return events

        with patch.object(AsyncAttendanceFetcher, "fetch_events", fake_fetch):
            summary = asyncio.run(
                AsyncAttendanceFetcher().sync_range(
                    datetime.date(2026, 3, 10), datetime.date(2026, 3, 11), **kwargs
                )
            )
        return summary, calls

    def test_sync_range_groups_bulk_events_by_pin_and_day(self):
        from monitoring_app.models import StaffAttendance

        events = [
            {
                "id": "1",
                "pin": "T900300T",
                "eventTime": "2026-03-10 09:00:05",
                "devSn": "CN3R230260002",
                "areaName": "А",
            },
            {
                "id": "2",
                "pin": "T900300T",
                "eventTime": "2026-03-10 18:00:07",
                "devSn": "CN3R230260001",
                "areaName": "А",
            },
            {
                "id": "3",
                "pin": "НЕ_СОТРУДНИК",
                "eventTime": "2026-03-10 10:00:00",
                "devSn": "X",
                "areaName": "А",
            },
        ]

        summary, calls = self._sync(events, chunk_days=7)

        self.assertEqual(calls, [(datetime.date(2026, 3, 10), datetime.date(2026, 3, 11))])
        self.assertEqual(summary["created_records"], 2)  # 10.03 с событиями + пустой 11.03
        record = StaffAttendance.objects.get(staff=self.staff, date_at=datetime.date(2026, 3, 11))
        self.assertEqual(timezone.localtime(record.last_out).strftime("%H:%M:%S"), "18:00:07")
        empty = StaffAttendance.objects.get(staff=self.staff, date_at=datetime.date(2026, 3, 12))
        self.assertIsNone(empty.first_in)

    def test_refetch_keeps_existing_rows_on_empty_days(self):
        from monitoring_app.models import StaffAttendance

        manual = StaffAttendance.objects.create(
            staff=self.staff,
            date_at=datetime.date(2026, 3, 12),
            first_in=timezone.make_aware(datetime.datetime(2026, 3, 11, 9, 0)),
        )

        summary, _ = self._sync([], keep_existing_when_empty=True)

        self.assertEqual(summary["created_records"] + summary["updated_records"], 0)
        manual.refresh_from_db()
        self.assertIsNotNone(manual.first_in)
