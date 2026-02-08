import gzip
import json
import logging
import subprocess
import time
from collections import defaultdict
from importlib import import_module
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save, pre_save

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Команда для восстановления базы данных из бэкапа.

    Поддерживает восстановление из JSON и SQL форматов. Автоматически определяет
    формат по расширению файла. Работает в транзакции для обеспечения целостности
    данных.
    """

    help = "Восстановить БД из бэкапа"

    def __init__(self, *args, **kwargs):
        """Инициализирует команду.

        Args:
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.
        """
        super().__init__(*args, **kwargs)
        self.options = {}

    def add_arguments(self, parser):
        """Добавляет аргументы командной строки для команды.

        Args:
            parser: Парсер аргументов argparse.
        """
        parser.add_argument(
            "backup_file",
            type=str,
            help="Путь к файлу бэкапа (.json/.json.gz или .sql/.sql.gz)",
        )
        parser.add_argument(
            "--input-dir",
            type=str,
            default=None,
            help="Директория с бэкапами (если backup_file относительный)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Проверить файл без восстановления",
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["auto", "json", "sql"],
            default="auto",
            help=("Формат файла " "(auto - определяется автоматически по расширению)"),
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Автоматически подтвердить восстановление без запроса",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить БД перед восстановлением (удалить все данные)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=300,
            help="Таймаут блокировок MySQL в секундах (по умолчанию 300)",
        )

    def handle(self, *args, **options):
        """Основной метод выполнения команды восстановления.

        Определяет формат файла, запрашивает подтверждение и вызывает
        соответствующий метод восстановления.

        Args:
            *args: Позиционные аргументы.
            **options: Опции командной строки.

        Raises:
            CommandError: Если файл не найден или формат не определен.
        """
        self.options = options

        backup_file_arg = options["backup_file"]
        input_dir = options.get("input_dir")
        dry_run = options["dry_run"]

        backup_path = Path(backup_file_arg)
        if not backup_path.is_absolute():
            if input_dir:
                backup_path = Path(input_dir) / backup_path
            elif hasattr(settings, "BACKUP_DB_DIR"):
                backup_path = Path(settings.BACKUP_DB_DIR) / backup_path
            else:
                backup_path = Path(settings.BASE_DIR).parent / "DB" / backup_path

        if not backup_path.exists():
            raise CommandError(f"Файл бэкапа не найден: {backup_path}")

        file_format = options["format"]
        if file_format == "auto":
            name_lower = backup_path.name.lower()
            if name_lower.endswith((".sql.gz", ".sql")):
                file_format = "sql"
            elif name_lower.endswith((".json.gz", ".json")):
                file_format = "json"
            else:
                raise CommandError(
                    "Не удалось определить формат файла. "
                    "Используйте --format json или --format sql."
                )

        self.stdout.write(
            f"Восстановление из {backup_path} (формат: {file_format.upper()})..."
        )

        self.stdout.write(
            self.style.WARNING("ВНИМАНИЕ: Это перезапишет существующие данные в БД!")
        )
        if not dry_run:
            if not options.get("yes", False):
                confirm = input("Продолжить? (yes/no): ")
                if confirm.lower() != "yes":
                    self.stdout.write("Отменено")
                    return
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "Автоматическое подтверждение: "
                        "восстановление будет выполнено"
                    )
                )

        if not dry_run and options.get("clear", False):
            self._clear_database()

        try:
            if file_format == "json":
                self._restore_json(backup_path, dry_run)
            elif file_format == "sql":
                self._restore_sql(backup_path, dry_run)
        except Exception as exc:
            logger.exception("Ошибка при восстановлении бэкапа")
            raise CommandError(f"Ошибка восстановления: {exc}") from exc

    def _restore_json(self, backup_path: Path, dry_run: bool):
        """Восстанавливает данные из JSON бэкапа.

        JSON файл читается полностью в память, валидируется и затем загружается
        через оптимизированную загрузку или стандартную команду loaddata.

        Args:
            backup_path: Путь к файлу JSON или JSON.GZ.
            dry_run: Если True, файл только проверяется без записи в БД.
        """
        is_gzipped = backup_path.suffix == ".gz" or backup_path.name.endswith(
            ".json.gz"
        )

        if is_gzipped:
            with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(backup_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        if not isinstance(data, list):
            raise CommandError("Неверный формат JSON бэкапа: ожидается список объектов")

        self.stdout.write(f"Найдено объектов: {len(data)}")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry-run: JSON файл валиден, восстановление не выполнено"
                )
            )
            return

        self._prepare_mysql_for_restore()
        self._disconnect_signals()

        self.stdout.write("Загрузка данных из JSON бэкапа...")
        self.stdout.write(f"Всего объектов для загрузки: {len(data)}")

        try:
            self._restore_json_optimized(data)
        except Exception as e:
            logger.warning(f"Оптимизированная загрузка не удалась: {e}, пробуем loaddata...")
            temp_file = (
                backup_path.parent
                / f"temp_restore_{backup_path.stem.replace('.json', '')}.json"
            )
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                self.stdout.write("Используется стандартный loaddata...")
                call_command("loaddata", str(temp_file), verbosity=1)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"JSON бэкап успешно восстановлен из {backup_path}"
                    )
                )
            except Exception as load_error:
                error_str = str(load_error).lower()
                if "lock wait timeout" in error_str:
                    self.stdout.write(
                        self.style.WARNING(
                            "Обнаружена блокировка БД. "
                            "Попробуйте остановить сервер Django и повторить."
                        )
                    )
                raise CommandError(
                    f"Ошибка загрузки данных: {load_error}"
                ) from load_error
            finally:
                self._safe_unlink(temp_file)
        finally:
            self._reconnect_signals()
            self._restore_mysql_settings()

    def _restore_sql(self, backup_path: Path, dry_run: bool):
        """Восстанавливает данные из SQL бэкапа.

        Пытается использовать mysql клиент для восстановления (надежнее).
        Если mysql недоступен, использует Django connection как fallback.

        Args:
            backup_path: Путь к файлу SQL или SQL.GZ.
            dry_run: Если True, выполняется только базовая валидация файла.

        Raises:
            CommandError: Если файл пустой или произошла ошибка восстановления.
        """
        is_gzipped = backup_path.suffix == ".gz" or backup_path.name.endswith(".sql.gz")

        if is_gzipped:
            with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                sql_content = f.read(1024)
        else:
            with open(backup_path, "r", encoding="utf-8") as f:
                sql_content = f.read(1024)

        if not sql_content.strip():
            raise CommandError("SQL файл пустой")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry-run: SQL файл валиден, восстановление не выполнено"
                )
            )
            return

        self._prepare_mysql_for_restore()

        db_config = settings.DATABASES["default"]
        if db_config["ENGINE"] == "django.db.backends.mysql":
            if self._restore_sql_with_mysql(db_config, backup_path, is_gzipped):
                return

        self.stdout.write(
            self.style.WARNING(
                "ВНИМАНИЕ: mysql клиент недоступен, "
                "используется Django connection. "
                "Многострочные команды могут работать некорректно."
            )
        )
        try:
            self._restore_sql_with_django(backup_path, is_gzipped)
        finally:
            self._restore_mysql_settings()

    def _restore_sql_with_mysql(
        self, db_config: dict, backup_path: Path, is_gzipped: bool
    ) -> bool:
        """Восстанавливает SQL бэкап используя mysql клиент.

        Args:
            db_config: Конфигурация БД из Django settings.
            backup_path: Путь к файлу SQL или SQL.GZ.
            is_gzipped: Если True, файл сжат в gzip.

        Returns:
            True если восстановление успешно, False иначе.
        """
        try:
            cmd = [
                "mysql",
                f"--host={db_config['HOST']}",
                f"--port={db_config['PORT']}",
                f"--user={db_config['USER']}",
                f"--password={db_config['PASSWORD']}",
                db_config["NAME"],
            ]

            self.stdout.write("Восстановление через mysql клиент...")

            if is_gzipped:
                gunzip_cmd = ["gunzip", "-c", str(backup_path)]
                gunzip_process = subprocess.Popen(
                    gunzip_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                result = subprocess.run(
                    cmd,
                    stdin=gunzip_process.stdout,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                gunzip_process.wait()
            else:
                with open(backup_path, "rb") as f:
                    result = subprocess.run(
                        cmd,
                        stdin=f,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )

            if result.returncode != 0:
                if result.stderr:
                    error_msg = result.stderr[:500]
                    self.stdout.write(self.style.ERROR(f"Ошибка mysql: {error_msg}"))
                logger.warning(f"mysql завершился с ошибкой: {result.stderr}")
                return False

            self.stdout.write(
                self.style.SUCCESS(
                    f"SQL бэкап успешно восстановлен из {backup_path} "
                    "через mysql клиент"
                )
            )
            self._restore_mysql_settings()
            return True

        except FileNotFoundError:
            logger.warning("mysql клиент не найден, используем Django connection")
            return False
        except Exception as e:
            logger.warning(f"Ошибка при использовании mysql клиента: {e}")
            return False

    def _restore_sql_with_django(self, backup_path: Path, is_gzipped: bool):
        """Восстанавливает SQL бэкап через Django connection (fallback).

        Args:
            backup_path: Путь к файлу SQL или SQL.GZ.
            is_gzipped: Если True, файл сжат в gzip.
        """
        if is_gzipped:
            with gzip.open(backup_path, "rt", encoding="utf-8") as f:
                sql_content = f.read()
        else:
            with open(backup_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

        self.stdout.write("Выполнение SQL команд через Django connection...")

        with transaction.atomic():
            cursor = connection.cursor()

            commands = [
                cmd.strip()
                for cmd in sql_content.split(";")
                if cmd.strip()
                and not cmd.strip().startswith("--")
                and not cmd.strip().startswith("/*")
            ]

            executed = 0
            for cmd in commands:
                if not cmd or len(cmd) < 3:
                    continue
                try:
                    cursor.execute(cmd)
                    executed += 1
                except Exception as e:
                    error_str = str(e).lower()
                    if any(
                        keyword in error_str
                        for keyword in [
                            "foreign_key_checks",
                            "unique_checks",
                            "already exists",
                            "unknown",
                        ]
                    ):
                        continue
                    logger.warning(f"Ошибка выполнения SQL команды: {cmd[:100]}... - {e}")

            self.stdout.write(
                self.style.SUCCESS(
                    f"SQL бэкап восстановлен через Django connection "
                    f"(выполнено команд: {executed})"
                )
            )

    def _prepare_mysql_for_restore(self):
        """Подготавливает MySQL для восстановления.

        Увеличивает таймауты блокировок и отключает проверки для ускорения
        восстановления.
        """
        db_config = settings.DATABASES.get("default", {})
        if db_config.get("ENGINE") != "django.db.backends.mysql":
            return

        try:
            cursor = connection.cursor()
            timeout = self.options.get("timeout", 300)

            try:
                cursor.execute(f"SET SESSION innodb_lock_wait_timeout = {timeout}")
                cursor.execute(f"SET SESSION lock_wait_timeout = {timeout}")
            except Exception:
                pass

            try:
                cursor.execute("SET SESSION foreign_key_checks = 0")
                cursor.execute("SET SESSION unique_checks = 0")
            except Exception:
                pass

            try:
                cursor.execute("SET SESSION sql_log_bin = 0")
            except Exception:
                pass

            self.stdout.write(
                self.style.SUCCESS(f"MySQL настроен для восстановления (таймаут: {timeout}с)")
            )
        except Exception as e:
            logger.warning(f"Не удалось настроить MySQL: {e}")

    def _restore_mysql_settings(self):
        """Восстанавливает стандартные настройки MySQL после восстановления."""
        db_config = settings.DATABASES.get("default", {})
        if db_config.get("ENGINE") != "django.db.backends.mysql":
            return

        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SET SESSION foreign_key_checks = 1")
                cursor.execute("SET SESSION unique_checks = 1")
            except Exception:
                pass

            try:
                cursor.execute("SET SESSION sql_log_bin = 1")
            except Exception:
                pass
        except Exception as e:
            error_str = str(e).lower()
            if "access denied" not in error_str and "privilege" not in error_str:
                logger.warning(f"Не удалось восстановить настройки MySQL: {e}")

    def _safe_unlink(self, file_path: Path, max_attempts: int = 5):
        """Безопасно удаляет файл с повторными попытками.

        Args:
            file_path: Путь к файлу для удаления.
            max_attempts: Максимальное количество попыток.
        """
        if not file_path.exists():
            return

        for attempt in range(max_attempts):
            try:
                file_path.unlink()
                return
            except PermissionError:
                if attempt < max_attempts - 1:
                    time.sleep(0.5)
                else:
                    logger.warning(
                        f"Не удалось удалить временный файл {file_path} "
                        f"после {max_attempts} попыток. "
                        "Файл может быть занят другим процессом. "
                        "Удалите его вручную."
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"Временный файл не удален: {file_path}. "
                            "Удалите его вручную."
                        )
                    )
            except Exception as e:
                logger.warning(f"Ошибка при удалении файла {file_path}: {e}")
                break

    def _clear_database(self):
        """Очищает базу данных перед восстановлением.

        Удаляет все данные из всех таблиц для обеспечения чистого состояния
        перед восстановлением.
        """
        self.stdout.write(
            self.style.WARNING("Очистка базы данных перед восстановлением...")
        )
        try:
            cursor = connection.cursor()
            db_config = settings.DATABASES.get("default", {})

            if db_config.get("ENGINE") == "django.db.backends.mysql":
                cursor.execute("SET SESSION foreign_key_checks = 0")
                cursor.execute("SET SESSION unique_checks = 0")

                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]

                if tables:
                    for table in tables:
                        try:
                            cursor.execute(f"TRUNCATE TABLE `{table}`")
                        except Exception as e:
                            logger.warning(f"Не удалось очистить таблицу {table}: {e}")
                            try:
                                cursor.execute(f"DELETE FROM `{table}`")
                            except Exception as delete_error:
                                logger.warning(
                                    f"Не удалось удалить данные из {table}: "
                                    f"{delete_error}"
                                )

                    self.stdout.write(
                        self.style.SUCCESS(f"Очищено таблиц: {len(tables)}")
                    )

                cursor.execute("SET SESSION foreign_key_checks = 1")
                cursor.execute("SET SESSION unique_checks = 1")
            else:
                call_command("flush", "--noinput", verbosity=0)
                self.stdout.write(self.style.SUCCESS("База данных очищена"))

        except Exception as e:
            logger.error(f"Ошибка при очистке БД: {e}")
            self.stdout.write(
                self.style.ERROR(
                    f"Ошибка очистки БД: {e}. Продолжаем восстановление..."
                )
            )

    def _get_certs_signal_bindings(self):
        """Возвращает список привязок сигналов certs, если app доступен.

        Формат элемента: (signal, receiver, sender).
        Если приложение certs не установлено или не импортируется, возвращает пустой список.
        """
        if not apps.is_installed("certs"):
            logger.info("Приложение certs не установлено; операции с его сигналами пропущены.")
            return []

        try:
            signals_module = import_module("certs.signals")
            models_module = import_module("certs.models")
        except ImportError as exc:
            logger.info("Не удалось импортировать certs.signals/certs.models: %s", exc)
            return []

        definitions = [
            (post_save, "request_saved", "Request"),
            (post_save, "request_status_changed", "Request"),
            (post_delete, "request_deleted", "Request"),
            (pre_save, "request_pre_save", "Request"),
            (post_save, "request_step_saved", "RequestStep"),
            (post_delete, "request_step_deleted", "RequestStep"),
            (post_save, "assignment_saved", "Assignment"),
            (post_delete, "assignment_deleted", "Assignment"),
            (post_save, "request_file_saved", "RequestFile"),
            (post_delete, "request_file_deleted", "RequestFile"),
        ]

        bindings = []
        for signal, receiver_name, sender_name in definitions:
            receiver = getattr(signals_module, receiver_name, None)
            sender = getattr(models_module, sender_name, None)
            if receiver is None or sender is None:
                logger.warning(
                    "Пропуск привязки certs signal: receiver=%s, sender=%s",
                    receiver_name,
                    sender_name,
                )
                continue
            bindings.append((signal, receiver, sender))

        return bindings

    def _disconnect_signals(self):
        """Отключает Django signals во время восстановления БД.

        Предотвращает отправку WebSocket уведомлений во время восстановления,
        что позволяет избежать ошибок подключения к Redis.
        """
        try:
            bindings = self._get_certs_signal_bindings()
            if not bindings:
                return

            for signal, receiver, sender in bindings:
                signal.disconnect(receiver, sender=sender)

            self.stdout.write("Сигналы Django отключены для восстановления (certs)")
        except Exception as e:
            logger.warning(f"Не удалось отключить сигналы: {e}")

    def _reconnect_signals(self):
        """Включает Django signals обратно после восстановления БД."""
        try:
            bindings = self._get_certs_signal_bindings()
            if not bindings:
                return

            for signal, receiver, sender in bindings:
                signal.connect(receiver, sender=sender)

            self.stdout.write("Сигналы Django включены обратно (certs)")
        except Exception as e:
            logger.warning(f"Не удалось включить сигналы: {e}")

    def _restore_json_optimized(self, data: list):
        """Оптимизированная загрузка JSON данных через Django ORM с батчами.

        Группирует объекты по моделям и загружает их батчами для повышения
        производительности. Показывает прогресс загрузки.

        Args:
            data: Список объектов для загрузки в формате Django fixtures.
        """
        objects_by_model = defaultdict(list)
        for obj in data:
            model_label = f"{obj['model']}"
            objects_by_model[model_label].append(obj)

        total_models = len(objects_by_model)
        self.stdout.write(f"Найдено моделей: {total_models}")

        total_loaded = 0
        start_time = time.time()

        for idx, (model_label, objects) in enumerate(objects_by_model.items(), 1):
            try:
                app_label, model_name = model_label.split(".")
                apps.get_model(app_label, model_name)

                self.stdout.write(
                    f"[{idx}/{total_models}] Загрузка {model_label}: "
                    f"{len(objects)} объектов..."
                )

                deserialized_objects = []
                for obj_data in objects:
                    try:
                        obj = serializers.deserialize("json", json.dumps([obj_data]))
                        deserialized_objects.extend(list(obj))
                    except Exception as e:
                        logger.warning(
                            f"Ошибка десериализации объекта {model_label}: {e}"
                        )
                        continue

                batch_size = 100
                saved_count = 0

                for i in range(0, len(deserialized_objects), batch_size):
                    batch = deserialized_objects[i : i + batch_size]
                    try:
                        with transaction.atomic():
                            for deserialized_obj in batch:
                                try:
                                    deserialized_obj.save()
                                    saved_count += 1
                                except Exception as e:
                                    error_str = str(e).lower()
                                    if (
                                        "duplicate" not in error_str
                                        and "unique" not in error_str
                                    ):
                                        logger.warning(
                                            f"Ошибка сохранения {model_label}: {e}"
                                        )

                        if saved_count % 1000 == 0:
                            elapsed = time.time() - start_time
                            self.stdout.write(
                                f"  Загружено: "
                                f"{saved_count}/{len(deserialized_objects)} "
                                f"({elapsed:.1f}с)"
                            )
                    except Exception as e:
                        logger.error(f"Ошибка батча {model_label}: {e}")
                        for deserialized_obj in batch:
                            try:
                                deserialized_obj.save()
                                saved_count += 1
                            except Exception:
                                pass

                total_loaded += saved_count
                elapsed = time.time() - start_time
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {model_label}: {saved_count}/{len(objects)} "
                        f"объектов ({elapsed:.1f}с)"
                    )
                )

            except LookupError:
                logger.warning(f"Модель {model_label} не найдена, пропускаем")
            except Exception as e:
                logger.error(f"Ошибка загрузки {model_label}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Ошибка загрузки {model_label}: {e}")
                )

        total_elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Восстановление завершено: {total_loaded} объектов "
                f"за {total_elapsed:.1f}с"
            )
        )
