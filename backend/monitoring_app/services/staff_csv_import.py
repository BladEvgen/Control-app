"""Импорт отделов и сотрудников из CSV-выгрузок СКУД.

Единственное место, где живёт логика импорта. Вызывается из двух точек:

* management-команда ``import_staff_csv`` (CLI);
* Celery-задача ``monitoring_app.tasks.process_uploaded_file`` (веб-загрузка).

Формат файлов (обе выгрузки одинаковы по обвязке): UTF-8 с BOM, CRLF,
все поля в кавычках, **две** строки заголовка — сначала название сущности
(``"Отдел"`` / ``"Сотрудник"``), затем названия колонок. Последняя колонка пустая.

Отделы (``dep_*.csv``)::

    0 Номер отдела | 1 Имя отдела | 2 Номер родительского отдела | 3 Название родительского

Сотрудники (``hum_*.csv``)::

    0 ID сотрудника | 1 Имя | 2 Фамилия | 3 Отдел № | 4 Имя отдела | 5 Название должности

Чтение потоковое и чанками, память O(chunk), а не O(файла).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
)

from django.db import transaction
from django.utils import timezone

from monitoring_app import models

logger = logging.getLogger("django")

CSV_ENCODING = "utf-8-sig"
CSV_ERRORS = "replace"

HEADER_ROWS = 2
DEFAULT_CHUNK_SIZE = 2000

POSITION_EMPLOYEE = "Сотрудник"
POSITION_STUDENT = "Студент"
POSITION_OTHER = "Прочие"

NEW_POSITION_RATES = {POSITION_OTHER: "0.00"}

ROOT_DEPARTMENT_ID = "1"

LEGACY_DEPARTMENT_ALIASES: Dict[str, str] = {"AUP": "2"}

ARCHIVE_GUARD_FRACTION = 0.5

FALLBACK_NAME = "Нет имени"
FALLBACK_SURNAME = "Нет фамилии"

ProgressFn = Callable[[str, int, int], None]


def _noop_progress(*_args: Any) -> None:
    """Заглушка прогресса для вызовов без отчётности (CLI, тесты)."""


@dataclass
class ImportStats:
    """Сводка импорта. Печатается командой и уезжает в результат Celery-задачи."""

    departments_created: int = 0
    departments_renamed: int = 0
    departments_reparented: int = 0
    departments_untouched: int = 0
    department_stubs_created: int = 0
    departments_merged: List[str] = field(default_factory=list)

    staff_created: int = 0
    staff_updated: int = 0
    staff_unchanged: int = 0
    staff_skipped_archived: int = 0
    staff_archived: int = 0
    positions_assigned: int = 0

    rows_read: int = 0
    rows_skipped: List[str] = field(default_factory=list)
    invariants: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "departments": {
                "created": self.departments_created,
                "renamed": self.departments_renamed,
                "reparented": self.departments_reparented,
                "untouched": self.departments_untouched,
                "stubs_created": self.department_stubs_created,
                "merged": self.departments_merged,
            },
            "staff": {
                "created": self.staff_created,
                "updated": self.staff_updated,
                "unchanged": self.staff_unchanged,
                "skipped_archived": self.staff_skipped_archived,
                "archived": self.staff_archived,
                "positions_assigned": self.positions_assigned,
            },
            "rows_read": self.rows_read,
            "rows_skipped": self.rows_skipped[:50],
            "rows_skipped_total": len(self.rows_skipped),
            "invariants": self.invariants,
            "dry_run": self.dry_run,
        }

    def summary_lines(self) -> List[str]:
        lines = [
            f"Отделы:      создано {self.departments_created}, "
            f"переименовано {self.departments_renamed}, "
            f"переподвешено {self.departments_reparented}, "
            f"заглушек {self.department_stubs_created}, "
            f"не тронуто {self.departments_untouched}",
            f"Сотрудники:  создано {self.staff_created}, "
            f"обновлено {self.staff_updated}, "
            f"без изменений {self.staff_unchanged}, "
            f"пропущено архивных {self.staff_skipped_archived}, "
            f"помечено архивными {self.staff_archived}",
            f"Должности:   выставлено {self.positions_assigned}",
            f"Строк прочитано: {self.rows_read}, пропущено битых: {len(self.rows_skipped)}",
        ]
        if self.departments_merged:
            lines.append(f"Слияние отделов: {', '.join(self.departments_merged)}")
        for name, value in self.invariants.items():
            lines.append(f"Инвариант {name}: {value}")
        if self.dry_run:
            lines.append("DRY-RUN: транзакция откатена, в БД ничего не записано.")
        return lines


class ImportAborted(RuntimeError):
    """Импорт остановлен защитной проверкой. Транзакция откатывается целиком."""


def _pad(row: List[str], expected_columns: int) -> List[str]:
    if len(row) < expected_columns:
        return row + [""] * (expected_columns - len(row))
    return row


def read_csv_rows(path: str, expected_columns: int) -> Iterator[List[str]]:
    """Читает CSV потоком, отдаёт строки данных без двух строк заголовка.

    Файл не загружается в память целиком — ``csv.reader`` тянет построчно из
    буферизованного текстового потока. Строки короче ожидаемого добиваются
    пустыми значениями, чтобы вызывающий код не ловил IndexError.
    """
    with open(path, encoding=CSV_ENCODING, errors=CSV_ERRORS, newline="") as handle:
        reader = csv.reader(handle)
        for _ in range(HEADER_ROWS):
            next(reader, None)
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            yield _pad(row, expected_columns)


def read_xlsx_rows(path: str, expected_columns: int) -> Iterator[List[str]]:
    """Читает XLSX потоком в том же виде, что и CSV.

    ``read_only=True`` включает потоковый режим openpyxl: строки отдаются по
    одной, а не собирается полный объектный граф листа. ``values_only=True``
    отдаёт значения вместо объектов ячеек. Всё приводится к строкам, чтобы
    дальше работал один и тот же код, что и для CSV.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        if sheet is None:
            return
        for index, values in enumerate(sheet.iter_rows(values_only=True)):
            if index < HEADER_ROWS:
                continue
            row = ["" if value is None else str(value).strip() for value in values]
            if not any(row):
                continue
            yield _pad(row, expected_columns)
    finally:
        workbook.close()


def iter_rows(path: str, expected_columns: int) -> Iterator[List[str]]:
    """Единый источник строк для CSV и XLSX — выбор по расширению файла."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        return read_xlsx_rows(path, expected_columns)
    return read_csv_rows(path, expected_columns)


def _chunked(rows: Iterable[List[str]], size: int) -> Iterator[List[List[str]]]:
    chunk: List[List[str]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _count_data_rows(path: str) -> int:
    """Оценка числа строк для прогресс-бара. Только для отображения.

    Для CSV считаются переводы строки без парсинга полей. Для XLSX берётся
    ``max_row``, который openpyxl знает из метаданных листа. Если значение
    недоступно, возвращается 0 — прогресс просто покажет обработанные строки
    без общего числа, импорт от этого не зависит.
    """
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            max_row = getattr(sheet, "max_row", None) if sheet is not None else None
            return max(0, (max_row or 0) - HEADER_ROWS)
        finally:
            workbook.close()

    total = 0
    with open(path, "rb") as handle:
        for _ in handle:
            total += 1
    return max(0, total - HEADER_ROWS)


def derive_position_name(pin: str) -> str:
    """Должность по шаблону pin, когда колонка должности в выгрузке пуста.

    ``T…T`` — сотрудник, ``S…S`` — студент, всё остальное — одна общая
    должность «Прочие». Регистр учитывается: выгрузка даёт только заглавные.
    """
    value = (pin or "").strip()
    if len(value) >= 2:
        if value[0] == "T" and value[-1] == "T":
            return POSITION_EMPLOYEE
        if value[0] == "S" and value[-1] == "S":
            return POSITION_STUDENT
    return POSITION_OTHER


def _resolve_positions(names: Set[str]) -> Dict[str, models.Position]:
    """Один запрос за существующими должностями, один bulk_create за новыми."""
    existing = {
        position.name: position for position in models.Position.objects.filter(name__in=list(names))
    }
    missing = [name for name in names if name not in existing]
    if missing:
        models.Position.objects.bulk_create(
            [
                models.Position(name=name, rate=NEW_POSITION_RATES.get(name, "1.00"))
                for name in missing
            ],
            ignore_conflicts=True,
        )
        for position in models.Position.objects.filter(name__in=missing):
            existing[position.name] = position
        logger.info("staff_csv_import: созданы должности %s", missing)

    without_pk = [name for name, position in existing.items() if position.pk is None]
    if without_pk:
        raise ImportAborted(
            f"Не удалось определить id должностей: {without_pk}. Назначение должностей прервано, изменения откатены."
        )
    return existing


def _read_department_rows(
    path: str,
    stats: ImportStats,
    progress: ProgressFn,
    chunk_size: int,
    total: int,
) -> Dict[str, tuple[str, Optional[str]]]:
    """Разбирает файл отделов в ``{id: (имя, id родителя)}``.

    Битая строка не валит импорт — она попадает в ``stats.rows_skipped``
    с номером, чтобы потом было понятно, что именно пропущено.
    """
    progress("departments", 0, total)
    incoming: Dict[str, tuple[str, Optional[str]]] = {}

    for index, row in enumerate(iter_rows(path, 4), start=1):
        dept_id = row[0].strip()
        name = row[1].strip()
        parent_id = row[2].strip() or None

        if not dept_id:
            stats.rows_skipped.append(f"dep:{index}: пустой номер отдела")
            continue
        if not name:
            stats.rows_skipped.append(f"dep:{index}: отдел {dept_id} без названия")
            continue
        if parent_id == dept_id:
            stats.rows_skipped.append(
                f"dep:{index}: отдел {dept_id} ссылается на себя как на родителя"
            )
            parent_id = None

        incoming[dept_id] = (name, parent_id)
        stats.rows_read += 1
        if index % chunk_size == 0:
            progress("departments", index, total)

    progress("departments", total, total)
    return incoming


def import_departments(
    path: str,
    stats: ImportStats,
    progress: ProgressFn = _noop_progress,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Set[str]:
    """Upsert дерева отделов из CSV. Возвращает множество id из выгрузки.

    Два прохода вместо топологической сортировки: сначала все записи заводятся
    и переименовываются с ``parent`` как есть, затем одним ``bulk_update``
    расставляются родители. Так ни на одном шаге не нарушается FK, порядок
    строк в файле не важен, сложность O(n).

    Отделы, которых нет в выгрузке, не удаляются и не изменяются.
    """
    total = _count_data_rows(path)
    incoming = _read_department_rows(path, stats, progress, chunk_size, total)

    existing = models.ChildDepartment.objects.in_bulk(list(incoming))

    to_create: List[models.ChildDepartment] = []
    to_rename: List[models.ChildDepartment] = []
    for dept_id, (name, _) in incoming.items():
        current = existing.get(dept_id)
        if current is None:
            to_create.append(models.ChildDepartment(id=dept_id, name=name, parent=None))
        elif current.name != name:
            current.name = name
            to_rename.append(current)

    if to_create:
        models.ChildDepartment.objects.bulk_create(to_create, batch_size=chunk_size)
        stats.departments_created = len(to_create)
    if to_rename:
        models.ChildDepartment.objects.bulk_update(to_rename, ["name"], batch_size=chunk_size)
        stats.departments_renamed = len(to_rename)

    current_parents: Dict[str, Optional[str]] = dict(
        models.ChildDepartment.objects.filter(id__in=list(incoming)).values_list("id", "parent_id")
    )
    known_ids = set(current_parents)
    by_parent: Dict[Optional[str], List[str]] = {}
    for dept_id, (_, parent_id) in incoming.items():
        if dept_id not in current_parents:
            continue
        if parent_id is not None and parent_id not in incoming and parent_id not in known_ids:
            stats.rows_skipped.append(
                f"dep: отдел {dept_id}: родитель {parent_id} не найден, привязка сохранена"
            )
            continue
        if current_parents[dept_id] != parent_id:
            by_parent.setdefault(parent_id, []).append(dept_id)

    for parent_id, dept_ids in by_parent.items():
        stats.departments_reparented += models.ChildDepartment.objects.filter(
            id__in=dept_ids
        ).update(parent_id=parent_id)

    stats.departments_untouched = models.ChildDepartment.objects.exclude(
        id__in=list(incoming)
    ).count()
    logger.info(
        "staff_csv_import: отделы — создано %s, переименовано %s, переподвешено %s, вне выгрузки %s",
        stats.departments_created,
        stats.departments_renamed,
        stats.departments_reparented,
        stats.departments_untouched,
    )
    return set(incoming)


def merge_legacy_departments(
    aliases: Dict[str, str],
    stats: ImportStats,
) -> None:
    """Сливает старый id отдела в id из выгрузки, не теряя ни людей, ни детей.

    Порядок шагов важен: сначала со старого отдела снимается всё, что на него
    ссылается, и только потом он удаляется — и только если действительно опустел.
    Любая неожиданность поднимает ``ImportAborted``, транзакция откатывается.
    """
    for legacy_id, target_id in aliases.items():
        if legacy_id == target_id:
            continue
        legacy = models.ChildDepartment.objects.filter(id=legacy_id).first()
        if legacy is None:
            continue

        target = models.ChildDepartment.objects.filter(id=target_id).first()
        if target is None:
            raise ImportAborted(
                f"Слияние {legacy_id} → {target_id} невозможно: отдела {target_id} "
                f"нет ни в выгрузке, ни в базе. Ничего не удалено."
            )

        moved_staff = models.Staff.all_objects.filter(department_id=legacy_id).update(
            department_id=target_id
        )

        moved_children = models.ChildDepartment.objects.filter(parent_id=legacy_id).update(
            parent_id=target_id
        )

        legacy_parent = models.ParentDepartment.objects.filter(id=legacy_id).first()
        if legacy_parent is not None:
            models.ParentDepartment.objects.update_or_create(
                id=target_id, defaults={"name": target.name}
            )
            legacy_parent.delete()

        left_staff = models.Staff.all_objects.filter(department_id=legacy_id).count()
        left_children = models.ChildDepartment.objects.filter(parent_id=legacy_id).count()
        if left_staff or left_children:
            raise ImportAborted(
                f"Слияние {legacy_id} → {target_id} прервано: на отделе осталось "
                f"сотрудников {left_staff}, дочерних отделов {left_children}. "
                f"Ничего не удалено."
            )

        legacy.delete()
        stats.departments_merged.append(
            f"{legacy_id} → {target_id} (сотрудников {moved_staff}, отделов {moved_children})"
        )
        logger.info(
            "staff_csv_import: слит отдел %s → %s (сотрудников %s, отделов %s)",
            legacy_id,
            target_id,
            moved_staff,
            moved_children,
        )


def _ensure_department_stub(
    dept_id: str,
    dept_name: str,
    known: Set[str],
    stats: ImportStats,
) -> str:
    """Создаёт заглушку отдела, чтобы новый сотрудник не остался без привязки."""
    name = dept_name.strip() or f"Отдел {dept_id} (нет в выгрузке)"
    models.ChildDepartment.objects.create(id=dept_id, name=name, parent_id=ROOT_DEPARTMENT_ID)
    known.add(dept_id)
    stats.department_stubs_created += 1
    stats.rows_skipped.append(f"hum: отдел {dept_id} отсутствовал — создана заглушка «{name}»")
    logger.warning("staff_csv_import: создана заглушка отдела %s «%s»", dept_id, name)
    return dept_id


def _parse_staff_chunk(
    chunk: List[List[str]],
    csv_pins: Set[str],
    stats: ImportStats,
    processed: int,
) -> tuple[List[Dict[str, Any]], int]:
    """Разбирает чанк строк сотрудников. Возвращает записи и новый счётчик строк.

    Дубль pin внутри файла отбрасывается здесь, а не в БД: иначе в одном
    ``bulk_create`` оказались бы две записи с одинаковым уникальным полем.
    """
    parsed: List[Dict[str, Any]] = []
    for row in chunk:
        processed += 1
        pin = row[0].strip()
        if not pin:
            stats.rows_skipped.append(f"hum:{processed}: пустой ID сотрудника")
            continue
        if pin in csv_pins:
            stats.rows_skipped.append(f"hum:{processed}: дубль pin {pin} в файле")
            continue
        csv_pins.add(pin)
        stats.rows_read += 1
        parsed.append(
            {
                "pin": pin,
                "name": row[1].strip(),
                "surname": row[2].strip(),
                "department_id": row[3].strip(),
                "department_name": row[4].strip(),
                "position_name": row[5].strip() or derive_position_name(pin),
            }
        )
    return parsed, processed


def _resolve_department(
    item: Dict[str, Any],
    current: Optional[models.Staff],
    known_departments: Set[str],
    stats: ImportStats,
) -> Optional[str]:
    """Определяет отдел сотрудника так, чтобы он никогда не остался без привязки.

    Неразрешимый отдел у нового сотрудника превращается в заглушку под корнем;
    у существующего — сохраняется текущая привязка. NULL не возвращается никогда,
    кроме случая, когда в выгрузке отдел вовсе не указан (его подставит вызывающий).
    """
    department_id: Optional[str] = item["department_id"] or None
    if not department_id or department_id in known_departments:
        return department_id

    if current is None:
        return _ensure_department_stub(
            department_id, item["department_name"], known_departments, stats
        )

    stats.rows_skipped.append(
        f"hum: {item['pin']}: отдел {department_id} не найден, сохранена текущая привязка"
    )
    return current.department_id


def _apply_staff_changes(
    current: models.Staff,
    item: Dict[str, Any],
    department_id: Optional[str],
) -> bool:
    """Переносит изменения из строки выгрузки в объект. True, если что-то поменялось.

    Пустое значение в выгрузке не перетирает заполненное в базе: у 87 человек
    в реальной выгрузке пустая фамилия, и терять её из-за этого нельзя.
    """
    changed = False
    if item["name"] and item["name"] != current.name:
        current.name = item["name"]
        changed = True
    if item["surname"] and item["surname"] != current.surname:
        current.surname = item["surname"]
        changed = True
    if department_id and department_id != current.department_id:
        current.department_id = department_id
        changed = True
    return changed


def _assign_positions(through: Any, position_by_pin: Dict[str, int], chunk_size: int) -> int:
    """Выставляет ровно одну должность каждому сотруднику чанка.

    Работает напрямую по through-таблице: три запроса на чанк вместо двух
    на каждого сотрудника. Старые связи сначала удаляются — импорт заменяет
    должность, а не добавляет к имеющимся.
    """
    if not position_by_pin:
        return 0

    ids = dict(
        models.Staff.all_objects.filter(pin__in=list(position_by_pin)).values_list("pin", "id")
    )
    staff_ids = list(ids.values())
    through.objects.filter(staff_id__in=staff_ids).delete()
    through.objects.bulk_create(
        [
            through(staff_id=staff_id, position_id=position_by_pin[pin])
            for pin, staff_id in ids.items()
        ],
        batch_size=chunk_size,
    )
    return len(staff_ids)


def import_staff(
    path: str,
    stats: ImportStats,
    progress: ProgressFn = _noop_progress,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    archive_missing: bool = False,
    force: bool = False,
) -> Set[str]:
    """Upsert сотрудников из CSV чанками. Возвращает множество pin из выгрузки.

    Архивные записи (``archived_at`` заполнен) полностью пропускаются: ни имя,
    ни фамилия, ни отдел, ни должность не обновляются, метка не снимается.
    Поиск идёт через ``all_objects``, иначе архивный pin не нашёлся бы и импорт
    попытался создать дубль, получив IntegrityError на unique-поле ``pin``.
    """
    total = _count_data_rows(path)
    progress("staff", 0, total)

    known_departments: Set[str] = set(models.ChildDepartment.objects.values_list("id", flat=True))
    if ROOT_DEPARTMENT_ID not in known_departments:
        raise ImportAborted(
            f"В базе нет корневого отдела {ROOT_DEPARTMENT_ID!r}: заглушки для "
            f"неразрешимых отделов вешать некуда. Сначала загрузите отделы."
        )
    positions = _resolve_positions({POSITION_EMPLOYEE, POSITION_STUDENT, POSITION_OTHER})

    through = models.Staff.positions.through
    csv_pins: Set[str] = set()
    processed = 0

    for chunk in _chunked(iter_rows(path, 6), chunk_size):
        parsed, processed = _parse_staff_chunk(chunk, csv_pins, stats, processed)

        if not parsed:
            progress("staff", processed, total)
            continue

        unknown_positions = {
            item["position_name"] for item in parsed if item["position_name"] not in positions
        }
        if unknown_positions:
            positions.update(_resolve_positions(unknown_positions))

        existing = models.Staff.all_objects.filter(
            pin__in=[item["pin"] for item in parsed]
        ).in_bulk(field_name="pin")

        to_create: List[models.Staff] = []
        to_update: List[models.Staff] = []
        position_by_pin: Dict[str, int] = {}

        for item in parsed:
            pin = item["pin"]
            current = existing.get(pin)

            if current is not None and current.archived_at is not None:
                stats.staff_skipped_archived += 1
                continue

            department_id = _resolve_department(item, current, known_departments, stats)

            if current is None:
                if not department_id:
                    department_id = ROOT_DEPARTMENT_ID
                to_create.append(
                    models.Staff(
                        pin=pin,
                        name=item["name"] or FALLBACK_NAME,
                        surname=item["surname"] or FALLBACK_SURNAME,
                        department_id=department_id,
                    )
                )
                position_by_pin[pin] = positions[item["position_name"]].pk
                continue

            if _apply_staff_changes(current, item, department_id):
                to_update.append(current)
                stats.staff_updated += 1
            else:
                stats.staff_unchanged += 1
            position_by_pin[pin] = positions[item["position_name"]].pk

        if to_create:
            models.Staff.objects.bulk_create(to_create, batch_size=chunk_size)
            stats.staff_created += len(to_create)
        if to_update:
            models.Staff.objects.bulk_update(
                to_update, ["name", "surname", "department"], batch_size=chunk_size
            )

        stats.positions_assigned += _assign_positions(through, position_by_pin, chunk_size)

        progress("staff", processed, total)

    if archive_missing:
        _archive_missing_staff(csv_pins, stats, force=force)

    logger.info(
        "staff_csv_import: сотрудники — создано %s, обновлено %s, без изменений %s, пропущено архивных %s, помечено %s",
        stats.staff_created,
        stats.staff_updated,
        stats.staff_unchanged,
        stats.staff_skipped_archived,
        stats.staff_archived,
    )
    return csv_pins


def _archive_missing_staff(csv_pins: Set[str], stats: ImportStats, force: bool = False) -> None:
    """Помечает активных сотрудников, которых нет в выгрузке. Один UPDATE.

    Защита от частичной выгрузки: если пометить предстоит больше половины
    активных, импорт прерывается — такой файл почти наверняка неполный.
    """
    missing = models.Staff.objects.exclude(pin__in=list(csv_pins))
    missing_count = missing.count()
    if not missing_count:
        return

    active_total = models.Staff.objects.count()
    fraction = missing_count / active_total if active_total else 0.0
    if fraction > ARCHIVE_GUARD_FRACTION and not force:
        raise ImportAborted(
            f"Архивирование затронуло бы {missing_count} из {active_total} активных "
            f"сотрудников ({fraction:.1%}) — больше порога "
            f"{ARCHIVE_GUARD_FRACTION:.0%}. Похоже, выгрузка неполная. "
            f"Если это осознанно, повторите с force."
        )

    stats.staff_archived = missing.update(archived_at=timezone.now())
    logger.warning(
        "staff_csv_import: помечено архивными %s сотрудников (%.1f%% активных)",
        stats.staff_archived,
        fraction * 100,
    )


def _check_invariants(stats: ImportStats, orphan_before: int) -> None:
    """Проверки, после которых импорт либо принимается, либо откатывается целиком."""
    orphan_after = models.Staff.all_objects.filter(department__isnull=True).count()
    roots = sorted(
        models.ChildDepartment.objects.filter(parent__isnull=True).values_list("id", flat=True)
    )
    stats.invariants = {
        "staff_without_department_before": orphan_before,
        "staff_without_department_after": orphan_after,
        "department_roots": roots,
    }
    if orphan_after > orphan_before:
        raise ImportAborted(
            f"Импорт оставил сотрудников без отдела: было {orphan_before}, стало {orphan_after}. Изменения откатены."
        )
    if roots != [ROOT_DEPARTMENT_ID]:
        raise ImportAborted(
            f"После импорта в дереве отделов корней {len(roots)}: {roots}. "
            f"Ожидался ровно один — {ROOT_DEPARTMENT_ID!r}. Изменения откатены."
        )


def run_import(
    departments_path: Optional[str] = None,
    humans_path: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    aliases: Optional[Dict[str, str]] = None,
    archive_missing: bool = False,
    force: bool = False,
    dry_run: bool = False,
    progress: ProgressFn = _noop_progress,
) -> ImportStats:
    """Полный импорт в одной транзакции. Любая защитная проверка откатывает всё.

    Отделы всегда идут до сотрудников — иначе новые отделы ещё не существуют
    и сотрудники массово получали бы заглушки.
    """
    if not departments_path and not humans_path:
        raise ValueError("Не передан ни файл отделов, ни файл сотрудников.")

    stats = ImportStats(dry_run=dry_run)
    merge_aliases = dict(LEGACY_DEPARTMENT_ALIASES)
    if aliases:
        merge_aliases.update(aliases)

    class _Rollback(Exception):
        """Служебное исключение: откатывает транзакцию после dry-run."""

    try:
        with transaction.atomic():
            orphan_before = models.Staff.all_objects.filter(department__isnull=True).count()

            if departments_path:
                import_departments(
                    departments_path, stats, progress=progress, chunk_size=chunk_size
                )
                merge_legacy_departments(merge_aliases, stats)

            if humans_path:
                import_staff(
                    humans_path,
                    stats,
                    progress=progress,
                    chunk_size=chunk_size,
                    archive_missing=archive_missing,
                    force=force,
                )

            _check_invariants(stats, orphan_before)

            if dry_run:
                raise _Rollback()
    except _Rollback:
        logger.info("staff_csv_import: dry-run завершён, транзакция откатена")
        return stats

    _invalidate_caches()
    return stats


def _invalidate_caches() -> None:
    """Сбрасывает кеши, которые импорт делает неактуальными."""
    from monitoring_app import cache_conf

    for key in ("root_departments_batch",):
        cache_conf.invalidate_cache(key)
    for pattern in ("*department*", "*staff*"):
        try:
            cache_conf.invalidate_cache_pattern(pattern)
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "staff_csv_import: не удалось сбросить кеш по шаблону %s: %s",
                pattern,
                error,
            )


def parse_alias_args(values: Sequence[str]) -> Dict[str, str]:
    """Разбирает ``--merge-department СТАРЫЙ=НОВЫЙ`` в словарь алиасов."""
    aliases: Dict[str, str] = {}
    for value in values or ():
        if "=" not in value:
            raise ValueError(f"Некорректный формат слияния {value!r}: ожидается СТАРЫЙ=НОВЫЙ")
        legacy, target = value.split("=", 1)
        legacy, target = legacy.strip(), target.strip()
        if not legacy or not target:
            raise ValueError(f"Некорректный формат слияния {value!r}: пустой id отдела")
        aliases[legacy] = target
    return aliases
