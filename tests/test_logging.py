"""Tests for logging infrastructure and error visibility.

Verifies that:
- All modules have loggers configured
- Silent error handling has been eliminated
- SQL_ECHO config is wired to engines
- Request logging middleware is installed
- Error handlers include exc_info for stack traces
"""
import ast
import logging
import os
from pathlib import Path


from app.config import Settings


# ---------------------------------------------------------------------------
# 1. Verify every service/task/connector/API module has a structlog logger
# ---------------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

# Modules that MUST have `logger = structlog.get_logger()` at module level
MODULES_REQUIRING_LOGGER = [
    "app.api.health",
    "app.api.markets",
    "app.api.arbitrage",
    "app.api.groups",
    "app.api.search",
    "app.api.synonyms",
    "app.api.deps",
    "app.services.market_service",
    "app.services.arbitrage_service",
    "app.services.group_service",
    "app.services.search_service",
    "app.services.live_search_service",
    "app.services.matching_service",
    "app.connectors.base",
    "app.connectors.polymarket",
    "app.connectors.kalshi",
    "app.tasks.fetch_markets",
    "app.tasks.fetch_prices",
    "app.tasks.match_markets",
    "app.tasks.group_markets",
    "app.tasks.cleanup",
    "app.tasks.backfill_prices",
    "app.tasks.scheduler",
    "app.database",
    "app.cache",
    "app.main",
]


class TestLoggerPresence:
    """Verify structlog logger is defined at module level in key modules."""

    def test_all_modules_have_logger(self):
        """Every module that handles errors or runs queries must have a logger."""
        missing = []
        for mod_path in MODULES_REQUIRING_LOGGER:
            file_path = APP_ROOT.parent / mod_path.replace(".", "/")
            file_path = file_path.with_suffix(".py")
            assert file_path.exists(), f"{mod_path} file not found at {file_path}"

            source = file_path.read_text()
            tree = ast.parse(source)

            has_logger = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "logger":
                            has_logger = True
                            break
            if not has_logger:
                missing.append(mod_path)

        assert missing == [], f"Modules missing logger: {missing}"


# ---------------------------------------------------------------------------
# 2. Verify no silent exception swallowing (except: pass)
# ---------------------------------------------------------------------------


class TestNoSilentErrors:
    """Verify there are no bare 'except: pass' or 'except Exception: pass' patterns."""

    def _check_file_for_silent_except(self, filepath: Path) -> list[int]:
        """Return line numbers where except blocks have only 'pass' as body."""
        source = filepath.read_text()
        tree = ast.parse(source)
        silent_lines = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Check if the body is just 'pass'
                if (
                    len(node.body) == 1
                    and isinstance(node.body[0], ast.Pass)
                ):
                    silent_lines.append(node.lineno)

        return silent_lines

    def test_no_silent_except_in_api(self):
        """API layer must not silently swallow exceptions."""
        api_dir = APP_ROOT / "api"
        for py_file in api_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            silent = self._check_file_for_silent_except(py_file)
            assert silent == [], f"{py_file.name} has silent except at lines {silent}"

    def test_no_silent_except_in_services(self):
        """Service layer must not silently swallow exceptions."""
        svc_dir = APP_ROOT / "services"
        for py_file in svc_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            silent = self._check_file_for_silent_except(py_file)
            assert silent == [], f"{py_file.name} has silent except at lines {silent}"

    def test_no_silent_except_in_tasks(self):
        """Task layer must not silently swallow exceptions."""
        task_dir = APP_ROOT / "tasks"
        for py_file in task_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            silent = self._check_file_for_silent_except(py_file)
            assert silent == [], f"{py_file.name} has silent except at lines {silent}"

    def test_no_silent_except_in_connectors(self):
        """Connector layer must not silently swallow exceptions."""
        conn_dir = APP_ROOT / "connectors"
        for py_file in conn_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            silent = self._check_file_for_silent_except(py_file)
            assert silent == [], f"{py_file.name} has silent except at lines {silent}"


# ---------------------------------------------------------------------------
# 3. Verify exc_info=True is present in all logger.error calls inside
#    except blocks (ensures stack traces are captured)
# ---------------------------------------------------------------------------


class TestExcInfoPresence:
    """Verify that logger.error() calls inside except blocks include exc_info."""

    def _find_error_calls_missing_exc_info(self, filepath: Path) -> list[int]:
        """Return line numbers of logger.error() inside except blocks missing exc_info."""
        source = filepath.read_text()
        tree = ast.parse(source)
        missing_lines = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                # Check if it's logger.error(...)
                func = child.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr == "error"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "logger"
                ):
                    continue
                # Check for exc_info keyword
                has_exc_info = any(
                    kw.arg == "exc_info" for kw in child.keywords
                )
                if not has_exc_info:
                    missing_lines.append(child.lineno)

        return missing_lines

    def test_tasks_have_exc_info(self):
        """All logger.error() in except blocks in tasks must have exc_info."""
        task_dir = APP_ROOT / "tasks"
        for py_file in task_dir.glob("*.py"):
            if py_file.name in ("__init__.py", "scheduler.py", "scheduler_thread.py"):
                continue
            missing = self._find_error_calls_missing_exc_info(py_file)
            assert missing == [], (
                f"{py_file.name} has logger.error() without exc_info at lines {missing}"
            )

    def test_connectors_have_exc_info(self):
        """All logger.error() in except blocks in connectors must have exc_info."""
        conn_dir = APP_ROOT / "connectors"
        for py_file in conn_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            missing = self._find_error_calls_missing_exc_info(py_file)
            assert missing == [], (
                f"{py_file.name} has logger.error() without exc_info at lines {missing}"
            )

    def test_api_have_exc_info(self):
        """All logger.error() in except blocks in API must have exc_info."""
        api_dir = APP_ROOT / "api"
        for py_file in api_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            missing = self._find_error_calls_missing_exc_info(py_file)
            assert missing == [], (
                f"{py_file.name} has logger.error() without exc_info at lines {missing}"
            )


# ---------------------------------------------------------------------------
# 4. Verify SQL_ECHO config setting
# ---------------------------------------------------------------------------


class TestSQLEchoConfig:
    """Verify SQL_ECHO setting is available and applied."""

    def test_sql_echo_setting_exists(self):
        """SQL_ECHO must be a boolean config option."""
        s = Settings(DATABASE_URL="sqlite:///x", REDIS_URL="redis://x")
        assert isinstance(s.SQL_ECHO, bool)

    def test_sql_echo_default_is_true(self):
        """Default SQL_ECHO should be True to log all queries."""
        s = Settings(DATABASE_URL="sqlite:///x", REDIS_URL="redis://x")
        assert s.SQL_ECHO is True

    def test_sql_echo_can_be_overridden(self):
        """SQL_ECHO can be set via env var."""
        os.environ["SQL_ECHO"] = "false"
        try:
            s = Settings(DATABASE_URL="sqlite:///x", REDIS_URL="redis://x")
            assert s.SQL_ECHO is False
        finally:
            del os.environ["SQL_ECHO"]


# ---------------------------------------------------------------------------
# 5. Verify request logging middleware is installed
# ---------------------------------------------------------------------------


class TestRequestLoggingMiddleware:
    """Verify the HTTP request logging middleware is wired up."""

    def test_middleware_class_exists(self):
        """RequestLoggingMiddleware must be importable."""
        from app.main import RequestLoggingMiddleware
        assert hasattr(RequestLoggingMiddleware, "dispatch")

    def test_middleware_is_registered_on_app(self):
        """The middleware registry must include RequestLoggingMiddleware."""
        from app.main import app, RequestLoggingMiddleware

        # FastAPI stores middleware in user_middleware before the stack is built
        middleware_classes = [m.cls for m in app.user_middleware]
        assert RequestLoggingMiddleware in middleware_classes, (
            "RequestLoggingMiddleware not registered in app.user_middleware"
        )


# ---------------------------------------------------------------------------
# 6. Verify logging setup configures SQLAlchemy engine logger
# ---------------------------------------------------------------------------


class TestLoggingSetup:
    """Verify the logging configuration includes sqlalchemy.engine."""

    def test_sqlalchemy_engine_logger_has_handlers(self):
        """After setup_logging(), sqlalchemy.engine logger must have handlers."""
        # setup_logging() is called at import time in app.main
        sa_logger = logging.getLogger("sqlalchemy.engine")
        assert len(sa_logger.handlers) > 0, (
            "sqlalchemy.engine logger has no handlers — SQL queries won't be logged"
        )

    def test_root_logger_has_handlers(self):
        """Root logger must have both file and console handlers."""
        root = logging.getLogger()
        assert len(root.handlers) >= 2, (
            f"Root logger has {len(root.handlers)} handlers, expected >= 2 (file + console)"
        )


# ---------------------------------------------------------------------------
# 7. Integration: health endpoint logs DB errors instead of swallowing them
# ---------------------------------------------------------------------------


class TestHealthEndpointErrorVisibility:
    """Verify health check doesn't silently swallow errors."""

    def test_health_check_source_has_no_bare_pass(self):
        """The health check source must not contain 'except ...: pass'."""
        health_file = APP_ROOT / "api" / "health.py"
        source = health_file.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                assert not (
                    len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
                ), "health.py still has 'except: pass' — errors are silently swallowed"

    def test_health_check_except_logs_error(self):
        """The health check except block must call logger.error()."""
        health_file = APP_ROOT / "api" / "health.py"
        source = health_file.read_text()
        tree = ast.parse(source)

        has_log_in_except = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "error"
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "logger"
                    ):
                        has_log_in_except = True

        assert has_log_in_except, "health.py except block does not call logger.error()"
