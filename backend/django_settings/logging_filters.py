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


class IgnorePylintFilter(logging.Filter):
    """Фильтр, блокирующий сообщения от Pylint и других линтеров."""

    def filter(self, record):
        logger_name = record.name.lower()
        if any(
            keyword in logger_name
            for keyword in [
                "pylint",
                "pygls",
                "lint",
                "linter",
                "flake8",
                "mypy",
                "black",
                "ruff",
            ]
        ):
            return False

        if hasattr(record, "pathname"):
            pathname = str(record.pathname).lower()
            if any(
                keyword in pathname
                for keyword in ["pylint", "pygls", ".pylint", "lint", "linter"]
            ):
                return False

        if hasattr(record, "funcName"):
            func_name = str(record.funcName).lower()
            if any(keyword in func_name for keyword in ["pylint", "lint", "linter"]):
                return False

        if record.getMessage():
            msg = record.getMessage().lower()
            lint_keywords = [
                "pylint",
                "unused argument",
                "reimport",
                "redefining name",
                "catching too general exception",
                "use lazy % formatting",
                "module level import not at top",
                "too many",
                "too few",
                "missing",
                "invalid",
                "consider",
                "should",
                "could",
                "prefer",
                "line too long",
                "trailing whitespace",
                "missing docstring",
                "access to",
                "protected",
                "duplicate",
                "cyclic import",
                "import-outside-toplevel",
                "no-member",
                "not-callable",
                "assignment-from-no-return",
                "unsubscriptable-object",
                "unsupported-assignment-operation",
                "no-value-for-parameter",
                "unexpected-keyword-arg",
                "pointless-string-statement",
                "fixme",
                "todo",
                "warning:",
                "error:",
                "info:",
                "note:",
            ]
            if any(keyword in msg for keyword in lint_keywords):
                return False

        return True


class AdminRequestFilter(logging.Filter):
    """Фильтр для логирования только admin-запросов."""

    def filter(self, record):
        logger_name = record.name.lower()
        if logger_name.startswith("admin_errors"):
            return True

        request = getattr(record, "request", None)
        if request is None:
            return False

        path = getattr(request, "path", "")
        if not isinstance(path, str) or not path.startswith("/admin/"):
            return False

        status_code = getattr(record, "status_code", None)
        try:
            if status_code is None:
                return True
            return int(status_code) >= 400
        except (TypeError, ValueError):
            return True
