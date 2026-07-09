"""Loguru configuration and stdlib-logging interception.

Call :func:`configure_logging` once at startup. It routes stdlib logging
(uvicorn, tortoise, etc.) through loguru so everything shares one format.
"""

from __future__ import annotations

import logging
import sys

from loguru import logger

from config.settings import settings


class InterceptHandler(logging.Handler):
    """Redirect stdlib ``logging`` records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging() -> None:
    """Set up loguru sinks and hijack the stdlib root logger."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
        enqueue=True,
    )

    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        settings.LOG_DIR / "app.log",
        level=settings.LOG_LEVEL,
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        enqueue=True,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "tortoise", "aerich"):
        std = logging.getLogger(name)
        std.handlers = [InterceptHandler()]
        std.propagate = False

    logger.debug("Logging configured (level={})", settings.LOG_LEVEL)
