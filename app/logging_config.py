"""
Central logging configuration for KI Asset Management.

Why this module exists
----------------------
Every module in this project uses the standard ``logging.getLogger(__name__)``
pattern, but nothing ever configured a handler on the root logger. As a result
those loggers propagated to an *unconfigured* root logger and Python's
"last resort" handler dropped everything below WARNING. Symptoms users see:

    * ``logger.debug(...)`` / ``logger.info(...)`` calls in app/utils/*.py
      never appear anywhere.
    * Errors inside cache/calculation helpers are swallowed
      (``except Exception: pass``) with no trace at all.
    * The Board page charts render empty with no explanation in the log.

This module fixes that by configuring the root logger once, at app creation,
with:

    * a consistent, greppable line format including the logger name
    * console output (stderr) always
    * optional rotating file output under ``instance/logs/``
    * a per-request correlation id, plus user / ip / status / duration
    * noisy third-party loggers clamped to WARNING
    * helpers (``log_operation``, ``describe_series``) so data pipelines can
      explain *why* they produced no data

Environment variables
---------------------
LOG_LEVEL            root level (default: DEBUG when Flask debug, else INFO)
APP_LOG_LEVEL        level for the ``app.*`` namespace (default: LOG_LEVEL)
LOG_DIR              directory for log files (default: <instance>/logs)
LOG_FILE             log filename (default: app.log); set to "" to disable
LOG_MAX_BYTES        rotation size (default: 5242880 = 5 MiB)
LOG_BACKUP_COUNT     rotated files kept (default: 5)
LOG_HTTP_REQUESTS    "true" to log every request (default: true)
SLOW_REQUEST_MS      requests slower than this log at WARNING (default: 1000)
LOG_SQL              "true" to log every SQL statement (default: false)
"""

import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

# --------------------------------------------------------------------------
# Request correlation id
# --------------------------------------------------------------------------
# Stored in a ContextVar so it survives the async/threaded paths Flask uses
# without leaking between requests.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LINE_FORMAT = (
    "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
)
LINE_FORMAT_WITH_REQ = (
    "%(asctime)s %(levelname)-8s [%(name)s] [req:%(request_id)s] %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Third-party loggers that are extremely chatty at DEBUG/INFO. Clamped to
# WARNING so our own diagnostics stay readable.
NOISY_LOGGERS = (
    "urllib3",
    "requests",
    "werkzeug",
    "yahooquery",
    "yfinance",
    "matplotlib",
    "PIL",
    "sendgrid",
    "botocore",
    "apscheduler",
    "sqlalchemy.engine",
    "python_http_client",
    "charset_normalizer",
)


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every log record.

    Always sets the attribute (to "-" outside a request) so the formatter never
    raises a KeyError.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def _resolve_level(value, default: int) -> int:
    """Turn "debug"/"10"/None into a logging level int."""
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return getattr(logging, text.upper(), default)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the project namespace.

    Prefer this over ``logging.getLogger(__name__)`` in new code so that every
    project logger is a child of ``app`` and therefore controlled by
    ``APP_LOG_LEVEL``.
    """
    if name == "app" or name.startswith("app."):
        return logging.getLogger(name)
    return logging.getLogger(f"app.{name}")


def describe_series(payload, keys=None) -> str:
    """Render a compact human summary of a chart-series payload.

    Used by the chart pipelines so an empty chart is always accompanied in the
    log by an explanation of the data that was (not) produced, e.g.::

        describe_series(None)                  -> "None"
        describe_series({...}, ('dates',))     -> "dates=24"
        describe_series({'dates': [...]}, ('dates', 'spy_series'))
                                               -> "dates=24 spy_series=24"
    """
    if payload is None:
        return "None"
    if not isinstance(payload, dict):
        return f"{type(payload).__name__}(len={len(payload)})"
    if keys is None:
        keys = ("dates",)
    parts = []
    for key in keys:
        value = payload.get(key)
        if value is None:
            parts.append(f"{key}=None")
        else:
            try:
                parts.append(f"{key}={len(value)}")
            except TypeError:
                parts.append(f"{key}={value!r}")
    return " ".join(parts)


def log_operation(logger: logging.Logger, label: str, level: int = logging.DEBUG):
    """Context manager that logs the duration and outcome of a block.

    Example::

        with log_operation(logger, "board.portfolio_series"):
            result = _calculate()

    Logs at ``level`` on success (``ok`` + duration) and at ERROR with a full
    traceback on failure, re-raising so callers keep their existing behaviour.
    """
    return _OperationLogger(logger, label, level)


class _OperationLogger:
    def __init__(self, logger, label, level):
        self.logger = logger
        self.label = label
        self.level = level
        self.started = None

    def __enter__(self):
        self.started = time.perf_counter()
        self.logger.log(self.level, "%s: start", self.label)
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed_ms = (time.perf_counter() - self.started) * 1000
        if exc_type is not None:
            self.logger.error(
                "%s: FAILED after %.1fms - %s: %s",
                self.label,
                elapsed_ms,
                exc_type.__name__,
                exc,
                exc_info=True,
            )
            return False
        self.logger.log(self.level, "%s: ok (%.1fms)", self.label, elapsed_ms)
        return False


def configure_logging(app) -> None:
    """Configure root logging + HTTP request logging for the Flask app.

    Safe to call more than once: handlers are tagged and replaced rather than
    duplicated, which matters because the dev reloader re-imports the app.
    """
    debug = bool(app.config.get("DEBUG"))
    root_level = _resolve_level(
        os.environ.get("LOG_LEVEL"), logging.DEBUG if debug else logging.INFO
    )
    app_level = _resolve_level(os.environ.get("APP_LOG_LEVEL"), root_level)

    formatter = logging.Formatter(LINE_FORMAT_WITH_REQ, DATE_FORMAT)
    request_filter = RequestIdFilter()

    root = logging.getLogger()
    root.setLevel(root_level)

    # Replace handlers we installed on a previous run (dev reloader, tests).
    for handler in list(root.handlers):
        if getattr(handler, "_ki_managed", False):
            root.removeHandler(handler)
            handler.close()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(request_filter)
    console._ki_managed = True
    root.addHandler(console)

    file_handler = _build_file_handler(app, formatter, request_filter)
    if file_handler is not None:
        root.addHandler(file_handler)

    # Project namespace gets its own level (usually the most verbose we allow).
    logging.getLogger("app").setLevel(app_level)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # SQL echo is opt-in: it is very noisy and only useful when debugging
    # query counts / N+1 problems.
    if _env_flag("LOG_SQL", False):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        app.config["SQLALCHEMY_ECHO"] = True

    _install_request_logging(app)

    logger = logging.getLogger("app.logging")
    logger.info(
        "logging configured: root=%s app=%s file=%s http=%s slow_ms=%s",
        logging.getLevelName(root_level),
        logging.getLevelName(app_level),
        file_handler.baseFilename if file_handler else "disabled",
        _env_flag("LOG_HTTP_REQUESTS", True),
        os.environ.get("SLOW_REQUEST_MS", "1000"),
    )


def _build_file_handler(app, formatter, request_filter):
    """Create the rotating file handler, or return None if disabled."""
    log_file = os.environ.get("LOG_FILE", "app.log")
    if log_file == "":
        return None

    log_dir = os.environ.get("LOG_DIR") or os.path.join(app.instance_path, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, log_file)
        handler = RotatingFileHandler(
            path,
            maxBytes=int(os.environ.get("LOG_MAX_BYTES", 5 * 1024 * 1024)),
            backupCount=int(os.environ.get("LOG_BACKUP_COUNT", 5)),
            encoding="utf-8",
        )
    except OSError as exc:  # read-only FS (e.g. some PaaS) must not crash boot
        logging.getLogger("app.logging").warning(
            "could not open log file in %s (%s); continuing with console only",
            log_dir,
            exc,
        )
        return None

    handler.setFormatter(formatter)
    handler.addFilter(request_filter)
    handler._ki_managed = True
    return handler


def _install_request_logging(app) -> None:
    """Wire per-request timing/user/status logging and error reporting."""
    if getattr(app, "_ki_request_logging", False):
        return
    app._ki_request_logging = True

    log_http = _env_flag("LOG_HTTP_REQUESTS", True)
    slow_ms = float(os.environ.get("SLOW_REQUEST_MS", 1000))
    logger = logging.getLogger("app.request")

    @app.before_request
    def _ki_start_timer():
        from flask import g, request

        request_id_var.set(uuid.uuid4().hex[:8])
        g._ki_started = time.perf_counter()
        if log_http and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "-> %s %s query=%s", request.method, request.full_path.rstrip("?"), len(request.args)
            )

    @app.after_request
    def _ki_log_response(response):
        from flask import g, request

        started = getattr(g, "_ki_started", None)
        elapsed_ms = (time.perf_counter() - started) * 1000 if started else -1.0
        status = response.status_code

        # Severity tracks the outcome so `grep ERROR app.log` finds real issues
        # and a slow page is visible without reading every line.
        if status >= 500:
            level = logging.ERROR
        elif status >= 400 or elapsed_ms >= slow_ms:
            level = logging.WARNING
        else:
            level = logging.INFO

        if log_http or level >= logging.WARNING:
            user = "-"
            try:
                from flask_login import current_user

                if current_user and current_user.is_authenticated:
                    user = current_user.email
            except Exception:  # noqa: BLE001 - logging must never break a request
                pass

            logger.log(
                level,
                "%s %s -> %s %.1fms user=%s type=%s",
                request.method,
                request.full_path.rstrip("?"),
                status,
                elapsed_ms,
                user,
                response.mimetype,
            )
        response.headers.setdefault("X-Request-Id", request_id_var.get())
        return response

    @app.teardown_request
    def _ki_log_exception(exc):
        if exc is not None:
            logger.error(
                "unhandled exception during request: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=exc,
            )


def log_dataframe_diagnostic(logger, label, df) -> None:
    """Log shape/null info for a pandas DataFrame (or explain why it is empty)."""
    if df is None:
        logger.warning("%s: DataFrame is None", label)
        return
    try:
        rows, cols = df.shape
    except Exception:  # noqa: BLE001
        logger.warning("%s: not a DataFrame (%r)", label, type(df).__name__)
        return
    if rows == 0:
        logger.warning("%s: DataFrame is EMPTY (0 rows)", label)
    else:
        logger.debug("%s: %s rows x %s cols", label, rows, cols)
