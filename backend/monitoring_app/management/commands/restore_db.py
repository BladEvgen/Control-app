"""Восстановление базы Django-проекта из бэкапа ``backup_db``."""

import gzip
import json
import os
import shutil
import subprocess
from argparse import ArgumentParser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, cast

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)

from .backup_db import backup_dir

MODEL_SIGNALS = (pre_save, post_save, pre_delete, post_delete, m2m_changed)
RESTORE_FLAGS: dict[str, list[str]] = {"postgresql": ["-v", "ON_ERROR_STOP=1"]}


@contextmanager
def muted_model_signals() -> Iterator[None]:
    """Снимает всех получателей сигналов моделей и возвращает их на выходе.

    Пока контекст открыт, обработчики (уведомления, WebSocket, задачи
    Celery) не вызываются ни для одной модели.

    Yields:
        None
    """
    saved = [(signal, signal.receivers) for signal in MODEL_SIGNALS]
    for signal, _ in saved:
        signal.receivers = []
        signal.sender_receivers_cache.clear()
    try:
        yield
    finally:
        for signal, receivers in saved:
            signal.receivers = receivers
            signal.sender_receivers_cache.clear()


def open_backup(path: Path, mode: str = "rb") -> IO[Any] | gzip.GzipFile:
    """Открывает бэкап на чтение, распаковывая ``.gz``.

    Args:
        path (Path): Путь к файлу.
        mode (str): ``"rb"`` или ``"rt"``.

    Returns:
        IO[Any] | gzip.GzipFile: Открытый файл.
    """
    encoding = None if "b" in mode else "utf-8"
    if path.name.endswith(".gz"):
        return gzip.open(path, mode, encoding=encoding)
    return path.open(mode, encoding=encoding)


class Command(BaseCommand):
    """Загружает ``.json[.gz]`` через ``loaddata`` или ``.sql[.gz]`` клиентом СУБД.

    JSON грузится в одной транзакции с заглушенными сигналами моделей;
    ``--clear`` перед этим выполняет ``flush`` в той же транзакции без
    ``post_migrate``, чтобы сиды проекта не конфликтовали с данными бэкапа.
    SQL передаётся в stdin ``mysql``/``psql``/``sqlite3`` с аргументами
    от ``connection.client``, пароль идёт через окружение.
    """

    help = "Восстановить БД из бэкапа"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Регистрирует флаги команды."""
        parser.add_argument("backup_file", help=".json[.gz] или .sql[.gz]")
        parser.add_argument("--input-dir", default=None)
        parser.add_argument("--database", default="default")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--format", choices=["auto", "json", "sql"], default="auto")
        parser.add_argument(
            "--yes", action="store_true", help="Не спрашивать подтверждение"
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить таблицы (flush) перед загрузкой",
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        """Находит файл, определяет формат, спрашивает подтверждение и грузит.

        Raises:
            CommandError: Файла нет или формат не определён.
        """
        path = Path(options["backup_file"])
        if not path.is_absolute():
            path = backup_dir(options["input_dir"]) / path
        if not path.exists():
            msg = f"Файл бэкапа не найден: {path}"
            raise CommandError(msg)

        fmt = options["format"]
        if fmt == "auto":
            fmt = Path(path.name.lower().removesuffix(".gz")).suffix.lstrip(".")
        if fmt not in ("json", "sql"):
            msg = "Не удалось определить формат: укажите --format json|sql"
            raise CommandError(msg)

        if options["dry_run"]:
            self._check(path, fmt)
            return

        database = options["database"]
        self.stdout.write(
            self.style.WARNING(
                f"Восстановление {path} в базу '{database}' перезапишет данные!"
            )
        )
        if not options["yes"] and input("Продолжить? (yes/no): ").lower() != "yes":
            self.stdout.write("Отменено")
            return

        with muted_model_signals(), transaction.atomic(using=database):
            if options["clear"]:
                call_command(
                    "flush",
                    database=database,
                    interactive=False,
                    inhibit_post_migrate=True,
                    verbosity=0,
                )
            if fmt == "json":
                call_command("loaddata", str(path), database=database)
        if fmt == "sql":
            self._restore_sql(path, database)
        self.stdout.write(self.style.SUCCESS(f"Восстановлено из {path}"))

    def _check(self, path: Path, fmt: str) -> None:
        """Проверяет файл без записи в базу.

        Args:
            path (Path): Файл бэкапа.
            fmt (str): ``"json"`` или ``"sql"``.

        Raises:
            CommandError: JSON не список объектов или SQL пустой.
        """
        with open_backup(path, "rt") as f:
            if fmt == "json":
                data = json.load(f)
                if not isinstance(data, list):
                    msg = "JSON бэкапа должен быть списком объектов"
                    raise CommandError(msg)
                self.stdout.write(
                    self.style.SUCCESS(f"JSON валиден, объектов: {len(data)}")
                )
            elif not f.read(1024).strip():
                msg = "SQL файл пустой"
                raise CommandError(msg)
            else:
                self.stdout.write(self.style.SUCCESS("SQL файл не пустой"))

    def _restore_sql(self, path: Path, database: str) -> None:
        """Передаёт SQL-дамп в stdin клиента СУБД потоком.

        Args:
            path (Path): Файл ``.sql[.gz]``.
            database (str): Alias базы.

        Raises:
            CommandError: Клиента нет в PATH или он завершился с ошибкой.
        """
        connection = connections[database]
        cmd, env = connection.client.settings_to_cmd_args_env(
            connection.settings_dict, RESTORE_FLAGS.get(connection.vendor, [])
        )
        if not shutil.which(cmd[0]):
            msg = f"{cmd[0]} не найден в PATH"
            raise CommandError(msg)
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, env={**os.environ, **(env or {})}
        )
        stdin = cast(IO[bytes], proc.stdin)
        with open_backup(path) as src:
            try:
                shutil.copyfileobj(src, stdin)
            finally:
                stdin.close()
        if proc.wait():
            msg = f"{cmd[0]} завершился с кодом {proc.returncode}"
            raise CommandError(msg)
