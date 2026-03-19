import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import structlog

from app.config import settings

LOG_DIR = settings.LOG_DIR
LOG_FILE = os.path.join(LOG_DIR, "polyarb.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
LOG_BACKUP_COUNT = 5  # keep 5 rotated files


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Shared structlog processors for both console and file
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # JSON formatter for file output (easy to parse)
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    # Human-readable formatter for console
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
    )

    # Rotating file handler
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Quiet down noisy third-party loggers
    for noisy in ("httpx", "httpcore", "asyncio", "urllib3", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # uvicorn access log also goes to file
    for uvi_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvi_logger = logging.getLogger(uvi_logger_name)
        uvi_logger.handlers.clear()
        uvi_logger.addHandler(file_handler)
        uvi_logger.addHandler(console_handler)
        uvi_logger.setLevel(log_level)

    # APScheduler
    aps_logger = logging.getLogger("apscheduler")
    aps_logger.handlers.clear()
    aps_logger.addHandler(file_handler)
    aps_logger.addHandler(console_handler)
    aps_logger.setLevel(log_level)

    structlog.get_logger().info(
        "logging_configured",
        log_dir=LOG_DIR,
        log_file=LOG_FILE,
        log_level=settings.LOG_LEVEL,
        max_bytes=LOG_MAX_BYTES,
        backup_count=LOG_BACKUP_COUNT,
    )
