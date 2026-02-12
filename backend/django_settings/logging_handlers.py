import os
import sys
import time
import shutil
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Безопасный обработчик ротации логов для Windows и Linux."""

    def doRollover(self):
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
            finally:
                self.stream = None

        current_time = int(time.time())
        dst_now = time.localtime(current_time)[-1]

        t = self.rolloverAt - self.interval
        if self.utc:
            time_tuple = time.gmtime(t)
        else:
            time_tuple = time.localtime(t)
            dst_then = time_tuple[-1]
            if dst_now != dst_then:
                if dst_now:
                    addend = 3600
                else:
                    addend = -3600
                time_tuple = time.localtime(t + addend)

        dfn = self.rotation_filename(
            "%s.%s" % (self.baseFilename, time.strftime(self.suffix, time_tuple))
        )

        if os.path.exists(self.baseFilename):
            try:
                if sys.platform == "win32":
                    self._rotate_windows(self.baseFilename, dfn)
                else:
                    self._rotate_unix(self.baseFilename, dfn)
            except Exception as e:
                import logging

                logging.error(f"Error during log rotation: {e}", exc_info=True)

        self._cleanup_old_files()

        if not self.delay:
            try:
                self.stream = self._open()
            except Exception:
                pass

        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at = new_rollover_at + self.interval

        if (self.when == "MIDNIGHT" or self.when.startswith("W")) and not self.utc:
            dst_at_rollover = time.localtime(new_rollover_at)[-1]
            if dst_now != dst_at_rollover:
                if not dst_now:
                    addend = -3600
                else:
                    addend = 3600
                new_rollover_at += addend

        self.rolloverAt = new_rollover_at

    def _rotate_windows(self, source: str, destination: str) -> None:
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                if os.path.exists(destination):
                    try:
                        os.remove(destination)
                    except (OSError, PermissionError):
                        pass

                if os.path.exists(source) and os.path.getsize(source) > 0:
                    shutil.copy2(source, destination)

                try:
                    with open(source, "w+", encoding=self.encoding or "utf-8") as f:
                        f.truncate(0)
                except (OSError, PermissionError):
                    pass

                return

            except (OSError, PermissionError):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
            except Exception:
                return

    def _rotate_unix(self, source: str, destination: str) -> None:
        try:
            if os.path.exists(destination):
                try:
                    os.remove(destination)
                except (OSError, PermissionError):
                    pass

            os.rename(source, destination)
        except (OSError, PermissionError):
            try:
                if os.path.exists(source) and os.path.getsize(source) > 0:
                    shutil.copy2(source, destination)
                    with open(source, "w+", encoding=self.encoding or "utf-8") as f:
                        f.truncate(0)
            except Exception:
                pass

    def _cleanup_old_files(self) -> None:
        if self.backupCount <= 0:
            return

        files_to_delete = []
        try:
            files_to_delete = self.getFilesToDelete()
        except Exception:
            files_to_delete = self._find_old_files()

        for filepath in files_to_delete:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except (OSError, PermissionError):
                continue
            except Exception:
                continue

    def _find_old_files(self) -> list:
        if not self.baseFilename or self.backupCount <= 0:
            return []

        try:
            log_dir = Path(self.baseFilename).parent
            base_name = Path(self.baseFilename).name

            matching_files = []
            for file_path in log_dir.glob(f"{base_name}.*"):
                if file_path.is_file() and str(file_path) != self.baseFilename:
                    matching_files.append(str(file_path))

            matching_files.sort(key=os.path.getmtime, reverse=True)

            if len(matching_files) > self.backupCount:
                return matching_files[self.backupCount :]

        except Exception:
            pass

        return []
