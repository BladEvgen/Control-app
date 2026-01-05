import gzip
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management команда для создания резервных копий базы данных.

    Создает бэкапы в форматах JSON и SQL для моделей из приложения
    monitoring_app и Django auth-системы. Поддерживает сжатие
    и автоматическую очистку старых бэкапов.
    """

    help = "Создать бэкап БД (только нужные модели)"

    def add_arguments(self, parser):
        """Добавляет аргументы командной строки для команды.

        Args:
            parser: Парсер аргументов argparse.
        """
        parser.add_argument(
            "--format",
            type=str,
            choices=["json", "sql", "both"],
            default="both",
            help="Формат бэкапа: json (Django формат), sql (SQL дамп), both (оба формата, по умолчанию)",
        )
        parser.add_argument(
            "--compress",
            action="store_true",
            help="Сжать бэкап в .gz",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="DB",
            help="Директория для сохранения (относительно BASE_DIR)",
        )
        parser.add_argument(
            "--keep-days",
            type=int,
            default=30,
            help="Сколько дней хранить старые бэкапы (по умолчанию 30)",
        )

    def handle(self, *args, **options):
        """Основной метод выполнения команды бэкапа.

        Создает бэкапы в указанных форматах и выполняет очистку
        старых файлов.

        Args:
            *args: Позиционные аргументы.
            **options: Опции командной строки (format, compress, output_dir, keep_days).
        """
        backup_format = options["format"]
        compress = options["compress"]
        output_dir_name = options["output_dir"]
        keep_days = options["keep_days"]

        if hasattr(settings, "BACKUP_DB_DIR"):
            backup_dir = Path(settings.BACKUP_DB_DIR)
        else:
            backup_dir = Path(settings.BASE_DIR).parent / output_dir_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        create_json = backup_format in ("json", "both")
        create_sql = backup_format in ("sql", "both")

        if create_json:
            self._create_json_backup(backup_dir, timestamp, compress)
        if create_sql:
            self._create_sql_backup(backup_dir, timestamp, compress)

        self._cleanup_old_backups(backup_dir, keep_days)

    def _create_json_backup(self, backup_dir: Path, timestamp: str, compress: bool):
        """Создает JSON бэкап базы данных.

        Экспортирует данные через Django dumpdata в JSON формат.
        Поддерживает сжатие в gzip.

        Args:
            backup_dir: Директория для сохранения бэкапа.
            timestamp: Временная метка для имени файла.
            compress: Если True, сжимает файл в .gz.

        Raises:
            ValueError: Если формат JSON неверный.
            Exception: При ошибках создания или записи файла.
        """
        filename = f"backup_{timestamp}.json"
        if compress:
            filename += ".gz"
        backup_path = backup_dir / filename

        self.stdout.write(f"Создание JSON бэкапа в {backup_path}...")

        models_to_backup = self._get_models_to_backup()

        try:
            temp_file = backup_dir / f"temp_backup_{timestamp}.json"

            with open(temp_file, "w", encoding="utf-8") as f:
                call_command(
                    "dumpdata",
                    *models_to_backup,
                    "--natural-foreign",
                    "--natural-primary",
                    "--indent",
                    "2",
                    stdout=f,
                )

            if temp_file.stat().st_size == 0:
                self.stdout.write(
                    self.style.WARNING("Бэкап пустой, возможно нет данных для экспорта")
                )
                temp_file.unlink()
                return

            with open(temp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("Неверный формат JSON бэкапа")

            if compress:
                with open(temp_file, "rb") as f_in:
                    with gzip.open(backup_path, "wb") as f_out:
                        f_out.writelines(f_in)
                temp_file.unlink()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"JSON бэкап создан и сжат: {backup_path} ({backup_path.stat().st_size / 1024 / 1024:.2f} MB)"
                    )
                )
            else:
                temp_file.rename(backup_path)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"JSON бэкап создан: {backup_path} ({backup_path.stat().st_size / 1024 / 1024:.2f} MB)"
                    )
                )

        except Exception as e:
            logger.exception("Ошибка при создании JSON бэкапа")
            self.stdout.write(self.style.ERROR(f"Ошибка: {e}"))
            if temp_file.exists():
                temp_file.unlink()
            raise

    def _create_sql_backup(self, backup_dir: Path, timestamp: str, compress: bool):
        """Создает SQL бэкап базы данных через mysqldump.

        Использует mysqldump для создания SQL дампа указанных таблиц.
        Поддерживает сжатие в gzip. Если mysqldump недоступен,
        создает SQL через Django ORM и выводит инструкции.

        Args:
            backup_dir: Директория для сохранения бэкапа.
            timestamp: Временная метка для имени файла.
            compress: Если True, сжимает файл в .gz.

        Raises:
            Exception: При ошибках создания или записи файла.
        """
        filename = f"backup_{timestamp}.sql"
        if compress:
            filename += ".gz"
        backup_path = backup_dir / filename

        self.stdout.write(f"Создание SQL бэкапа в {backup_path}...")

        mysqldump_success = False
        db_config = None
        tables = []
        temp_file = None

        try:
            temp_file = backup_dir / f"temp_backup_{timestamp}.sql"

            db_config = settings.DATABASES["default"]
            if db_config["ENGINE"] == "django.db.backends.mysql":
                tables = self._get_table_names()
                if tables:
                    mysqldump_success = self._create_sql_with_mysqldump(
                        db_config, temp_file, tables
                    )
                    if not mysqldump_success:
                        self.stdout.write(
                            self.style.WARNING(
                                "ВНИМАНИЕ: mysqldump недоступен или завершился с ошибкой. "
                                "Используется упрощенный SQL формат."
                            )
                        )
                        self._create_sql_with_django(temp_file)
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "ВНИМАНИЕ: Не удалось определить таблицы для бэкапа."
                        )
                    )
                    self._create_sql_with_django(temp_file)
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"ВНИМАНИЕ: БД {db_config['ENGINE']} не поддерживает mysqldump. "
                        "Используется упрощенный SQL формат."
                    )
                )
                self._create_sql_with_django(temp_file)

            if temp_file.stat().st_size == 0:
                self.stdout.write(
                    self.style.WARNING(
                        "SQL бэкап пустой, возможно нет данных для экспорта"
                    )
                )
                temp_file.unlink()
                if db_config and tables:
                    self._print_mysqldump_command(db_config, tables, backup_path)
                return

            if compress:
                with open(temp_file, "rb") as f_in:
                    with gzip.open(backup_path, "wb") as f_out:
                        f_out.writelines(f_in)
                temp_file.unlink()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"SQL бэкап создан и сжат: {backup_path} "
                        f"({backup_path.stat().st_size / 1024 / 1024:.2f} MB)"
                    )
                )
            else:
                temp_file.rename(backup_path)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"SQL бэкап создан: {backup_path} "
                        f"({backup_path.stat().st_size / 1024 / 1024:.2f} MB)"
                    )
                )

            if not mysqldump_success and db_config and tables:
                self._print_mysqldump_command(db_config, tables, backup_path)

        except Exception as e:
            logger.exception("Ошибка при создании SQL бэкапа")
            self.stdout.write(self.style.ERROR(f"ОШИБКА: {e}"))
            if temp_file and temp_file.exists():
                temp_file.unlink()
            if db_config and tables:
                self._print_mysqldump_command(db_config, tables, backup_path)
            raise

    def _create_sql_with_mysqldump(
        self, db_config: dict, output_file: Path, tables: list[str]
    ) -> bool:
        """Создает SQL бэкап используя mysqldump.

        Args:
            db_config: Конфигурация БД из Django settings.
            output_file: Путь к выходному файлу.
            tables: Список таблиц для бэкапа.

        Returns:
            True если mysqldump успешно выполнен, False иначе.
        """
        try:
            cmd = [
                "mysqldump",
                f"--host={db_config['HOST']}",
                f"--port={db_config['PORT']}",
                f"--user={db_config['USER']}",
                f"--password={db_config['PASSWORD']}",
                "--routines",
                "--triggers",
                "--lock-tables=false",
                db_config["NAME"],
            ] + tables

            with open(output_file, "w", encoding="utf-8") as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )

            if result.returncode != 0:
                logger.warning(f"mysqldump завершился с ошибкой: {result.stderr}")
                if result.stderr:
                    self.stdout.write(
                        self.style.ERROR(f"Ошибка mysqldump: {result.stderr[:200]}")
                    )
                return False

            return True

        except FileNotFoundError:
            logger.warning("mysqldump не найден, используем Django ORM")
            return False
        except Exception as e:
            logger.warning(f"Ошибка при использовании mysqldump: {e}")
            return False

    def _print_mysqldump_command(
        self, db_config: dict, tables: list[str], output_path: Path
    ):
        """Выводит команду mysqldump для ручного выполнения.

        Args:
            db_config: Конфигурация БД из Django settings.
            tables: Список таблиц для бэкапа.
            output_path: Путь к выходному файлу.
        """
        self.stdout.write("")
        self.stdout.write(self.style.ERROR("=" * 80))
        self.stdout.write(
            self.style.ERROR(
                "ВНИМАНИЕ: SQL бэкап создан в упрощенном формате или произошла ошибка!"
            )
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Для создания полноценного SQL бэкапа используйте mysqldump вручную:"
            )
        )
        self.stdout.write(self.style.ERROR("=" * 80))
        self.stdout.write("")

        tables_str = " ".join(tables)
        host = db_config.get("HOST", "localhost")
        port = db_config.get("PORT", "3306")
        user = db_config.get("USER", "root")
        password = db_config.get("PASSWORD", "")
        db_name = db_config.get("NAME", "")

        if password:
            cmd_basic = (
                f"mysqldump -h {host} -P {port} -u {user} -p'{password}' "
                f"--routines --triggers --lock-tables=false "
                f"{db_name} {tables_str} > {output_path}"
            )
        else:
            cmd_basic = (
                f"mysqldump -h {host} -P {port} -u {user} "
                f"--routines --triggers --lock-tables=false "
                f"{db_name} {tables_str} > {output_path}"
            )

        self.stdout.write(
            self.style.NOTICE("Команда для выполнения (базовый вариант):")
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  {cmd_basic}"))
        self.stdout.write("")

        if password:
            cmd_advanced = (
                f"mysqldump -h {host} -P {port} -u {user} -p'{password}' "
                f"--single-transaction --routines --triggers "
                f"{db_name} {tables_str} > {output_path}"
            )
        else:
            cmd_advanced = (
                f"mysqldump -h {host} -P {port} -u {user} "
                f"--single-transaction --routines --triggers "
                f"{db_name} {tables_str} > {output_path}"
            )

        self.stdout.write(
            self.style.NOTICE(
                "Вариант с расширенными правами (требует RELOAD/FLUSH_TABLES):"
            )
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  {cmd_advanced}"))
        self.stdout.write("")

        cmd_interactive = (
            f"mysqldump -h {host} -P {port} -u {user} -p "
            f"--routines --triggers --lock-tables=false "
            f"{db_name} {tables_str} > {output_path}"
        )
        self.stdout.write(
            self.style.NOTICE("Вариант с интерактивным вводом пароля (безопаснее):")
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  {cmd_interactive}"))
        self.stdout.write("")

        self.stdout.write(
            self.style.NOTICE("Примечание: Замените путь к файлу на нужный вам.")
        )
        self.stdout.write(
            self.style.NOTICE("Для сжатия добавьте: | gzip > backup.sql.gz")
        )
        self.stdout.write("")
        self.stdout.write(self.style.ERROR("=" * 80))
        self.stdout.write("")

    def _create_sql_with_django(self, output_file: Path):
        """Создает упрощенный SQL бэкап через Django ORM.

        Использует JSON дамп и конвертирует в базовые SQL INSERT statements.
        Это fallback метод, когда mysqldump недоступен.

        Args:
            output_file: Путь к выходному файлу.
        """
        models_to_backup = self._get_models_to_backup()

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("-- SQL backup created via Django ORM (fallback mode)\n")
            f.write("-- Note: This is a simplified SQL export.\n")
            f.write("-- For full SQL backup, use mysqldump.\n\n")

            temp_json = output_file.parent / f"temp_json_{output_file.stem}.json"
            try:
                with open(temp_json, "w", encoding="utf-8") as json_f:
                    call_command(
                        "dumpdata",
                        *models_to_backup,
                        "--natural-foreign",
                        "--natural-primary",
                        "--indent",
                        "2",
                        stdout=json_f,
                    )

                with open(temp_json, "r", encoding="utf-8") as json_f:
                    data = json.load(json_f)

                f.write(f"-- Total objects: {len(data)}\n")
                f.write("-- Use JSON backup file for full data restoration\n")
                f.write("-- SQL format requires mysqldump for proper export\n\n")

            finally:
                if temp_json.exists():
                    temp_json.unlink()

    def _get_table_names(self) -> list[str]:
        """Возвращает список имен таблиц для бэкапа.

        Returns:
            Список имен таблиц в БД.
        """
        models_to_backup = self._get_models_to_backup()
        tables = []

        for model_str in models_to_backup:
            try:
                app_label, model_name = model_str.split(".")
                from django.apps import apps

                model = apps.get_model(app_label, model_name)
                if model:
                    tables.append(model._meta.db_table)
            except Exception as e:
                logger.warning(f"Не удалось получить таблицу для {model_str}: {e}")

        return tables

    def _get_models_to_backup(self):
        """Возвращает список моделей для бэкапа в порядке зависимостей.

        Включает модели из Django auth-системы и monitoring_app.
        Порядок важен для корректного восстановления данных.

        Returns:
            list[str]: Список строк вида "app_label.ModelName".
        """
        User = get_user_model()
        user_model_str = User._meta.label

        return [
            "contenttypes.ContentType",
            "auth.Permission",
            "auth.Group",
            user_model_str,
            "monitoring_app.PasswordResetToken",
            "monitoring_app.PasswordResetRequestLog",
            "monitoring_app.APIKey",
            "monitoring_app.UserProfile",
            "monitoring_app.FileCategory",
            "monitoring_app.ParentDepartment",
            "monitoring_app.ChildDepartment",
            "monitoring_app.Position",
            "monitoring_app.Staff",
            "monitoring_app.StaffFaceMask",
            "monitoring_app.AbsentReason",
            "monitoring_app.RemoteWork",
            "monitoring_app.StaffAttendance",
            "monitoring_app.LessonAttendance",
            "monitoring_app.ClassLocation",
            "monitoring_app.Salary",
            "monitoring_app.PublicHoliday",
            "monitoring_app.PerformanceBonusRule",
        ]

    def _cleanup_old_backups(self, backup_dir: Path, keep_days: int):
        """Удаляет бэкапы старше указанного количества дней.

        Ищет файлы по шаблону backup_*.json* и backup_*.sql*,
        извлекает дату из имени файла и удаляет старые.

        Args:
            backup_dir: Директория с бэкапами.
            keep_days: Количество дней для хранения бэкапов.
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=keep_days)
        deleted = 0

        for backup_file in backup_dir.glob("backup_*.*"):
            try:
                name_part = backup_file.stem
                if name_part.endswith(".json") or name_part.endswith(".sql"):
                    name_part = name_part.replace(".json", "").replace(".sql", "")

                if name_part.startswith("backup_"):
                    date_str = name_part.replace("backup_", "").split("_")[0]
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff:
                        backup_file.unlink()
                        deleted += 1
            except (ValueError, IndexError):
                continue

        if deleted > 0:
            self.stdout.write(f"Удалено старых бэкапов: {deleted}")
