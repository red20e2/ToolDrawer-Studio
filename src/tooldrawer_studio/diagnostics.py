from __future__ import annotations

import logging
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from tooldrawer_studio.app_paths import logs_dir
from tooldrawer_studio.version import __version__

LOGGER_NAME = "tooldrawer_studio"


def configure_logging() -> Path:
    directory = logs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "tooldrawer-studio.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.info("application-start app_version=%s platform=%s", __version__, platform.platform())
    handler.flush()
    return path


def log_exception(context: str, exc: BaseException) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.error(
        "app_version=%s platform=%s context=%s exception=%s",
        __version__,
        platform.platform(),
        context,
        type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    for handler in logger.handlers:
        handler.flush()


def install_exception_hook() -> None:
    def process_hook(kind, value, trace):
        logging.getLogger(LOGGER_NAME).critical(
            "app_version=%s platform=%s context=unhandled-main-thread exception=%s",
            __version__,
            platform.platform(),
            kind.__name__,
            exc_info=(kind, value, trace),
        )

    def thread_hook(args):
        logging.getLogger(LOGGER_NAME).critical(
            "app_version=%s platform=%s context=unhandled-worker-thread exception=%s",
            __version__,
            platform.platform(),
            args.exc_type.__name__,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    setattr(sys, "excepthook", process_hook)
    setattr(threading, "excepthook", thread_hook)
