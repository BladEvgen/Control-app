"""Бэкап базы Django-проекта в JSON (сериализаторы Django) и SQL (родной дампер)."""

import gzip
import os
import shutil
import subprocess
import tempfile
from argparse import ArgumentParser
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any, cast

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, models, router
from django.db.models import Prefetch

DUMP_TOOLS: dict[str, str] = {"mysql": "mysqldump", "psql": "pg_dump"}
DUMP_FLAGS: dict[str, list[str]] = {
    "mysql": [
        "--single-transaction",
        "--routines",
        "--triggers",
        "--no-tablespaces",
        "--set-gtid-purged=OFF",
    ],
    "postgresql": ["--no-owner", "--clean", "--if-exists"],
    "sqlite": [".dump"],
}
JSON_EXCLUDE: frozenset[str] = frozenset({"sessions"})
GZIP_LEVEL = 6
CHUNK_SIZE = 2000


def backup_dir(explicit: str | None) -> Path:
    """Возвращает каталог бэкапов.

    Args:
        explicit (str | None): Путь из флага; относительный считается
            от ``<BASE_DIR>/..``.

    Returns:
        Path: ``explicit``, иначе ``settings.BACKUP_DB_DIR``,
        иначе ``<BASE_DIR>/../DB``.
    """
    root = Path(settings.BASE_DIR).parent
    if explicit:
        return root / explicit
    configured = getattr(settings, "BACKUP_DB_DIR", None)
    return Path(configured) if configured else root / "DB"


def open_out(path: Path, mode: str) -> IO[Any] | gzip.GzipFile:
    """Открывает файл на запись, сжимая gzip, если имя кончается на ``.gz``.

    Args:
        path (Path): Путь к файлу.
        mode (str): ``"wb"`` или ``"wt"``.

    Returns:
        IO[Any] | gzip.GzipFile: Открытый файл.
    """
    encoding = None if "b" in mode else "utf-8"
    if path.name.endswith(".gz"):
        return gzip.open(path, mode, compresslevel=GZIP_LEVEL, encoding=encoding)
    return path.open(mode, encoding=encoding)


def natural_fks(model: type[models.Model] | None) -> list[str]:
    """Имена FK/O2O-полей, чьи модели сериализуются natural key.

    Args:
        model (type[models.Model] | None): Модель; ``None`` даёт пустой список.

    Returns:
        list[str]: Имена полей для ``select_related``.
    """
    if model is None:
        return []
    return [
        f.name
        for f in model._meta.concrete_fields
        if f.is_relation and hasattr(f.related_model, "natural_key")
    ]


def dump_objects(database: str, exclude: frozenset[str]) -> Iterator[models.Model]:
    """Отдаёт все объекты базы в порядке зависимостей, как ``dumpdata --all``.

    Связи с natural key подгружаются ``select_related``/``prefetch_related``,
    поэтому сериализатор не делает запрос на каждый объект.

    Args:
        database (str): Alias базы.
        exclude (frozenset[str]): Метки ``app`` или ``app.model`` для пропуска.

    Yields:
        models.Model: Объекты чанками по ``CHUNK_SIZE``.
    """
    configs = [
        (config, None)
        for config in apps.get_app_configs()
        if config.models_module and config.label not in exclude
    ]
    for model in serializers.sort_dependencies(configs, allow_cycles=True):
        meta = model._meta
        if (
            meta.proxy
            or meta.label_lower in exclude
            or not router.allow_migrate_model(database, model)
        ):
            continue
        related = [
            path
            for name in natural_fks(model)
            for path in (
                name,
                *(
                    f"{name}__{deep}"
                    for deep in natural_fks(meta.get_field(name).related_model)
                ),
            )
        ]
        m2m = [
            Prefetch(
                f.name,
                queryset=f.related_model._base_manager.select_related(
                    *natural_fks(f.related_model)
                ),
            )
            for f in meta.many_to_many
            if f.remote_field.through._meta.auto_created
            and hasattr(f.related_model, "natural_key")
        ]
        yield from (
            model._base_manager.using(database)
            .order_by(meta.pk.name)
            .select_related(*related)
            .prefetch_related(*m2m)
            .iterator(chunk_size=CHUNK_SIZE)
        )


def sql_dump_command(database: str) -> tuple[list[str], dict[str, str]]:
    """Собирает команду дампера СУБД и окружение с паролем.

    Args:
        database (str): Alias базы.

    Returns:
        tuple[list[str], dict[str, str]]: Аргументы процесса и окружение.

    Raises:
        CommandError: СУБД не поддерживается, база sqlite в памяти
            или дампера нет в PATH.
    """
    connection = connections[database]
    in_memory = getattr(connection, "is_in_memory_db", lambda: False)()
    if connection.vendor not in DUMP_FLAGS or in_memory:
        msg = f"SQL-дамп для {connection.vendor} не поддерживается"
        raise CommandError(msg)
    args, env = connection.client.settings_to_cmd_args_env(
        connection.settings_dict, DUMP_FLAGS[connection.vendor]
    )
    cmd = [DUMP_TOOLS.get(args[0], args[0]), *args[1:]]
    if not shutil.which(cmd[0]):
        msg = f"{cmd[0]} не найден в PATH"
        raise CommandError(msg)
    return cmd, {**os.environ, **(env or {})}


class Command(BaseCommand):
    """Создаёт ``backup_<дата>_<время>.sql[.gz]`` или ``.json[.gz]``.

    ``--format auto`` (по умолчанию) снимает один SQL, если для СУБД есть
    дампер, иначе один JSON; ``json``/``sql``/``both`` задают формат явно.
    JSON содержит все модели, которые роутер пускает в базу, кроме сессий,
    с natural keys.
    SQL снимается целиком дампером СУБД (mysqldump, pg_dump, sqlite3);
    аргументы и пароль собирает ``connection.client``, как ``dbshell``,
    пароль передаётся через окружение. Файл появляется только после
    успешного дампа; бэкапы старше ``--keep-days`` удаляются.
    """

    help = "Создать бэкап БД (JSON и/или SQL)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Регистрирует флаги команды."""
        parser.add_argument(
            "--format",
            choices=["auto", "json", "sql", "both"],
            default="auto",
            help="auto: SQL, если есть дампер СУБД, иначе JSON",
        )
        parser.add_argument("--compress", action="store_true", help="Сжать в .gz")
        parser.add_argument(
            "--output-dir",
            default=None,
            help="Каталог бэкапов, относительный — от <BASE_DIR>/.. "
            "(по умолчанию BACKUP_DB_DIR или <BASE_DIR>/../DB)",
        )
        parser.add_argument("--database", default="default")
        parser.add_argument("--keep-days", type=int, default=30)

    def handle(self, *_args: Any, **options: Any) -> None:
        """Снимает бэкапы выбранных форматов и чистит старые."""
        target = backup_dir(options["output_dir"])
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = ".gz" if options["compress"] else ""
        database = options["database"]
        fmt = options["format"]
        if fmt == "auto":
            try:
                sql_dump_command(database)
                fmt = "sql"
            except CommandError as exc:
                self.stdout.write(self.style.WARNING(f"{exc}; бэкап в JSON"))
                fmt = "json"

        if fmt in ("json", "both"):
            self._write(
                target / f"backup_{stamp}.json{suffix}", self._dump_json, database
            )
        if fmt in ("sql", "both"):
            self._write(
                target / f"backup_{stamp}.sql{suffix}", self._dump_sql, database
            )

        self._cleanup(target, options["keep_days"])

    def _write(
        self, path: Path, dump: Callable[[Path, str], None], database: str
    ) -> None:
        """Пишет дамп в ``.part_<имя>`` и переименовывает в ``path`` после успеха.

        Args:
            path (Path): Итоговый файл.
            dump (Callable[[Path, str], None]): Функция дампа ``(файл, alias)``.
            database (str): Alias базы.
        """
        part = path.with_name(f".part_{path.name}")
        self.stdout.write(f"Создание {path}...")
        try:
            dump(part, database)
            part.rename(path)
        finally:
            part.unlink(missing_ok=True)
        size = path.stat().st_size / 1024 / 1024
        self.stdout.write(self.style.SUCCESS(f"Готово: {path} ({size:.2f} MB)"))

    def _dump_json(self, part: Path, database: str) -> None:
        """Сериализует базу в JSON потоком, не держа объекты в памяти."""
        with open_out(part, "wt") as out:
            serializers.serialize(
                "json",
                dump_objects(database, JSON_EXCLUDE),
                stream=out,
                use_natural_foreign_keys=True,
                use_natural_primary_keys=True,
            )

    def _dump_sql(self, part: Path, database: str) -> None:
        """Пишет вывод дампера СУБД в файл потоком.

        Raises:
            CommandError: Дампер недоступен (см. ``sql_dump_command``)
                или завершился с ошибкой (текст stderr в сообщении).
        """
        cmd, env = sql_dump_command(database)
        with tempfile.TemporaryFile() as errors, open_out(part, "wb") as out:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors, env=env)
            shutil.copyfileobj(cast(IO[bytes], proc.stdout), out)
            if proc.wait():
                errors.seek(0)
                stderr = errors.read().decode(errors="replace").strip()
                msg = f"{cmd[0]} завершился с кодом {proc.returncode}: {stderr}"
                raise CommandError(msg)

    def _cleanup(self, target: Path, keep_days: int) -> None:
        """Удаляет ``backup_YYYYMMDD_*`` с датой в имени старше ``keep_days``.

        Args:
            target (Path): Каталог бэкапов.
            keep_days (int): Сколько дней хранить.
        """
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y%m%d")
        old = [
            f
            for f in target.glob("backup_*")
            if f.name[7:15].isdigit() and f.name[7:15] < cutoff
        ]
        for f in old:
            f.unlink()
        if old:
            self.stdout.write(f"Удалено старых бэкапов: {len(old)}")
