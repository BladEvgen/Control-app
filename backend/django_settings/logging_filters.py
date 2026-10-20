import logging


class IgnoreShutdownErrorsFilter(logging.Filter):
    """Фильтр, игнорирующий ошибки shutdown при логировании."""

    def filter(self, record):
        if record.exc_info:
            _, exc_value, _ = record.exc_info
            if exc_value:
                error_str = str(exc_value).lower()
                shutdown_keywords = [
                    "cannot schedule new futures",
                    "after shutdown",
                    "after interpreter shutdown",
                    "single thread executor already being used",
                    "would deadlock",
                    "finalizing",
                ]
                if any(keyword in error_str for keyword in shutdown_keywords):
                    return False

        if record.getMessage():
            msg = record.getMessage().lower()
            shutdown_keywords = [
                "cannot schedule new futures",
                "after shutdown",
                "shutdown detected",
                "single thread executor",
                "would deadlock",
            ]
            if any(keyword in msg for keyword in shutdown_keywords):
                return False

        return True
