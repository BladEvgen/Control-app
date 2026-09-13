from __future__ import annotations

import datetime
import logging
import os
import zipfile
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from django.core.files.base import ContentFile
from django.db import transaction

from monitoring_app import models
from monitoring_app.services.staff_csv_import import iter_rows

logger = logging.getLogger("django")

ProgressFn = Callable[..., None]


def _noop_progress(*_args: Any) -> None:
    """Заглушка прогресса для вызовов без отчётности."""


MAX_ERRORS_REPORTED = 10

MAX_PHOTO_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_UNPACKED_BYTES = 8 * 1024 * 1024 * 1024

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _safe_member_name(name: str) -> Optional[str]:
    """Возвращает безопасное имя файла из архива или None, если член пропускается.

    Путь отбрасывается целиком — берётся только базовое имя. Это закрывает
    zip-slip: член с именем ``../../etc/passwd`` превращается в ``passwd``
    и всё равно никуда не пишется, потому что мы не распаковываем на диск.
    """
    if not name or name.endswith("/"):
        return None
    normalized = name.replace("\\", "/")
    base = os.path.basename(normalized)
    if not base or base in (".", ".."):
        return None
    return base


def import_photos_zip(path: str, progress: ProgressFn = _noop_progress) -> Dict[str, Any]:
    """Загружает аватарки сотрудников из ZIP: имя файла — это pin.

    Переписано относительно прежней версии по трём причинам:

    * не используется ``extractall`` — прежняя версия распаковывала архив
      в ``/tmp`` под именами из архива, то есть член с ``../`` в имени мог
      писать за пределы каталога (zip-slip), и тот же файл читался дважды;
    * pin'ы собираются заранее и разрешаются одним запросом вместо запроса
      на каждый файл — было O(n) обращений к БД, стало одно;
    * есть лимиты на размер одного кадра и на суммарный объём распакованного.

    Архивные сотрудники пропускаются: их записи заморожены.
    """
    result: Dict[str, Any] = {
        "updated": 0,
        "skipped_unknown_pin": 0,
        "skipped_bad_member": 0,
        "skipped_too_large": 0,
        "errors": [],
    }

    with zipfile.ZipFile(path, "r") as archive:
        members: List[Tuple[str, str]] = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            base = _safe_member_name(info.filename)
            if base is None:
                result["skipped_bad_member"] += 1
                continue
            pin, extension = os.path.splitext(base)
            if extension.lower() not in PHOTO_EXTENSIONS:
                result["skipped_bad_member"] += 1
                continue
            if info.file_size > MAX_PHOTO_BYTES:
                result["skipped_too_large"] += 1
                logger.warning(
                    "import_photos_zip: %s пропущен, %s байт больше лимита %s",
                    base,
                    info.file_size,
                    MAX_PHOTO_BYTES,
                )
                continue
            members.append((info.filename, base))

        total = len(members)
        progress("photos", 0, total)

        pins: Set[str] = {os.path.splitext(base)[0] for _, base in members}
        staff_by_pin = models.Staff.objects.filter(pin__in=list(pins)).in_bulk(field_name="pin")

        unpacked = 0
        for index, (member_name, base) in enumerate(members, start=1):
            pin = os.path.splitext(base)[0]
            staff = staff_by_pin.get(pin)
            if staff is None:
                result["skipped_unknown_pin"] += 1
                progress("photos", index, total)
                continue
            try:
                with archive.open(member_name) as source:
                    payload = source.read(MAX_PHOTO_BYTES + 1)
                if len(payload) > MAX_PHOTO_BYTES:
                    result["skipped_too_large"] += 1
                    continue
                unpacked += len(payload)
                if unpacked > MAX_ARCHIVE_UNPACKED_BYTES:
                    raise RuntimeError(
                        f"Суммарный распакованный объём превысил {MAX_ARCHIVE_UNPACKED_BYTES} байт — архив отклонён."
                    )
                if staff.avatar:
                    staff.avatar.delete(save=False)
                staff.avatar.save(base, ContentFile(payload), save=False)
                staff.save()
                result["updated"] += 1
            except RuntimeError:
                raise
            except Exception as error:  # noqa: BLE001
                logger.error("import_photos_zip: %s — %s", base, error)
                if len(result["errors"]) < MAX_ERRORS_REPORTED:
                    result["errors"].append(f"{base}: {error}")
            progress("photos", index, total)

    logger.info(
        "import_photos_zip: обновлено %s, неизвестных pin %s, отклонено членов %s",
        result["updated"],
        result["skipped_unknown_pin"],
        result["skipped_bad_member"] + result["skipped_too_large"],
    )
    return result


def _parse_holiday_date(value: str) -> datetime.date:
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("Неверный формат даты. Ожидается DD.MM.YYYY или YYYY-MM-DD.")


WORKING_DAY_VALUES = {
    "да": True,
    "нет": False,
    "yes": True,
    "no": False,
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "рабочий": True,
    "не рабочий": False,
}


def import_public_holidays(path: str, progress: ProgressFn = _noop_progress) -> Dict[str, Any]:
    """Праздничные даты: дата | название | рабочий день."""
    result: Dict[str, Any] = {"created": 0, "updated": 0, "errors": []}
    rows = list(iter_rows(path, 3))
    total = len(rows)
    progress("holidays", 0, total)

    with transaction.atomic():
        for index, row in enumerate(rows, start=1):
            try:
                if not row[0].strip() or not row[1].strip():
                    raise ValueError("Отсутствует дата праздника или название праздника.")
                date = _parse_holiday_date(row[0])
                flag_raw = row[2].strip().lower()
                is_working_day = WORKING_DAY_VALUES.get(flag_raw)
                if is_working_day is None:
                    raise ValueError(
                        "Неверное значение в поле «Рабочий день». Ожидается «Да» или «Нет»."
                    )
                _holiday, created = models.PublicHoliday.objects.update_or_create(
                    date=date,
                    defaults={
                        "name": row[1].strip(),
                        "is_working_day": is_working_day,
                    },
                )
                result["created" if created else "updated"] += 1
            except Exception as error:  # noqa: BLE001
                logger.error("import_public_holidays: строка %s — %s", index, error)
                if len(result["errors"]) < MAX_ERRORS_REPORTED:
                    result["errors"].append(f"Строка {index}: {error}")
            progress("holidays", index, total)

    logger.info(
        "import_public_holidays: создано %s, обновлено %s, ошибок %s",
        result["created"],
        result["updated"],
        len(result["errors"]),
    )
    return result


def _parse_location_row(row: List[str], utils: Any) -> Tuple[str, str, float, float, Optional[int]]:
    """Разбирает строку точки занятий: название | адрес | гео | радиус.

    Радиус необязателен: пустое или нечисловое значение означает «оставить как
    есть», поэтому возвращается None, а не ноль.
    """
    name = row[0].strip()
    address = row[1].strip()
    geo_data = row[2].strip()
    radius_raw = row[3].strip()

    if not geo_data or geo_data.lower() == "none":
        raise ValueError("Отсутствует значение в столбце «гео».")

    latitude, longitude = utils.extract_coordinates(geo_data)
    if not all([name, address, latitude, longitude]):
        raise ValueError("Отсутствуют необходимые данные.")

    latitude = float(str(latitude).strip().replace(",", "."))
    longitude = float(str(longitude).strip().replace(",", "."))

    acceptance_radius_m: Optional[int] = None
    if radius_raw:
        try:
            parsed_radius = int(float(radius_raw))
            if parsed_radius > 0:
                acceptance_radius_m = parsed_radius
        except (TypeError, ValueError):
            acceptance_radius_m = None

    return name, address, latitude, longitude, acceptance_radius_m


def import_class_locations(path: str, progress: ProgressFn = _noop_progress) -> Dict[str, Any]:
    """Точки занятий: название | адрес | гео | радиус приёмки (опционально).

    Прежняя версия отбрасывала первую строку уже после сортировки строк
    («rows[1:]»), то есть теряла произвольную запись, а не заголовок. Здесь
    строки заголовка снимаются по номеру, до всякой сортировки; сортировка
    не нужна вовсе, потому что записи независимы.
    """
    from monitoring_app import utils
    from monitoring_app.signals import invalidate_class_location_cache_impl

    result: Dict[str, Any] = {"created": 0, "updated": 0, "errors": []}
    rows = list(iter_rows(path, 4))
    total = len(rows)
    progress("locations", 0, total)

    with transaction.atomic():
        existing = {
            (location.name, location.address): location
            for location in models.ClassLocation.objects.only(
                "id", "name", "address", "latitude", "longitude", "acceptance_radius_m"
            )
        }
        to_create: List[models.ClassLocation] = []
        to_update: List[models.ClassLocation] = []

        for index, row in enumerate(rows, start=1):
            try:
                name, address, latitude, longitude, acceptance_radius_m = _parse_location_row(
                    row, utils
                )
                location = existing.get((name, address))
                if location is not None:
                    location.latitude = latitude
                    location.longitude = longitude
                    if acceptance_radius_m is not None:
                        location.acceptance_radius_m = acceptance_radius_m
                    to_update.append(location)
                else:
                    fields: Dict[str, Any] = {
                        "name": name,
                        "address": address,
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                    if acceptance_radius_m is not None:
                        fields["acceptance_radius_m"] = acceptance_radius_m
                    to_create.append(models.ClassLocation(**fields))
            except Exception as error:  # noqa: BLE001
                logger.error("import_class_locations: строка %s — %s", index, error)
                if len(result["errors"]) < MAX_ERRORS_REPORTED:
                    result["errors"].append(f"Строка {index}: {error}")
            progress("locations", index, total)

        if to_create:
            models.ClassLocation.objects.bulk_create(to_create)
            result["created"] = len(to_create)
        if to_update:
            models.ClassLocation.objects.bulk_update(
                to_update, ["latitude", "longitude", "acceptance_radius_m"]
            )
            result["updated"] = len(to_update)

    if result["created"] or result["updated"]:
        try:
            invalidate_class_location_cache_impl()
        except Exception as error:  # noqa: BLE001
            logger.warning("import_class_locations: сброс кеша — %s", error)

    logger.info(
        "import_class_locations: создано %s, обновлено %s, ошибок %s",
        result["created"],
        result["updated"],
        len(result["errors"]),
    )
    return result


def delete_staff_by_parent(
    path: str,
    parent_department_id: str,
    progress: ProgressFn = _noop_progress,
) -> Dict[str, Any]:
    """Удаляет сотрудников подотделов родителя, которых нет в списке pin из файла.

    Поведение сохранено как было: родитель ищется в ``ParentDepartment``,
    подотделы — по совпадению имени родителя. Считаются и архивные записи:
    операция явно удаляющая, скрывать от неё часть базы неправильно.
    """
    if not parent_department_id:
        raise ValueError("ID родительского отдела не был передан.")

    parent = models.ParentDepartment.objects.filter(id=parent_department_id).first()
    if parent is None:
        raise ValueError(f"Родительский отдел с ID {parent_department_id} не найден.")

    child_ids = list(
        models.ChildDepartment.objects.filter(parent__name=parent.name).values_list("id", flat=True)
    )
    if not child_ids:
        raise ValueError(f"Для родительского отдела {parent.name} не найдены дочерние отделы.")

    keep_pins: Set[str] = set()
    for index, row in enumerate(iter_rows(path, 1), start=1):
        pin = row[0].strip()
        if pin:
            keep_pins.add(pin)
        if index % 1000 == 0:
            progress("delete_staff", index, 0)

    to_delete = models.Staff.all_objects.filter(department_id__in=child_ids).exclude(
        pin__in=list(keep_pins)
    )
    deleted_count, _details = to_delete.delete()
    logger.info(
        "delete_staff_by_parent: родитель %s, подотделов %s, оставлено pin %s, удалено записей %s",
        parent.name,
        len(child_ids),
        len(keep_pins),
        deleted_count,
    )
    return {
        "deleted": deleted_count,
        "kept_pins": len(keep_pins),
        "child_departments": len(child_ids),
        "parent": parent.name,
    }
