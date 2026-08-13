from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest


def _diagnostics_api():
    try:
        from tooldrawer_studio.diagnostics import (
            configure_logging,
            install_exception_hook,
            log_exception,
        )
    except ModuleNotFoundError:
        pytest.fail("release diagnostics are not implemented")
    return configure_logging, install_exception_hook, log_exception


def test_diagnostics_write_release_context_and_traceback(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    configure_logging, _install, log_exception = _diagnostics_api()
    path = configure_logging()

    try:
        raise ValueError("fixture failure")
    except ValueError as exc:
        log_exception("generate-organizer", exc)

    text = path.read_text(encoding="utf-8")
    assert path == tmp_path / "ToolDrawer Studio" / "logs" / "tooldrawer-studio.log"
    assert "app_version=0.1.0" in text
    assert "platform=" in text
    assert "context=generate-organizer" in text
    assert "ValueError: fixture failure" in text
    assert "Traceback" in text


def test_release_log_uses_bounded_rotation(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    configure_logging, _install, _log = _diagnostics_api()
    configure_logging()
    logger = logging.getLogger("tooldrawer_studio")
    handlers = [item for item in logger.handlers if isinstance(item, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 5 * 1024 * 1024
    assert handlers[0].backupCount == 3


def test_exception_hooks_are_installed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    configure_logging, install_exception_hook, _log = _diagnostics_api()
    configure_logging()
    old_sys = sys.excepthook
    old_thread = threading.excepthook
    try:
        install_exception_hook()
        assert sys.excepthook is not old_sys
        assert threading.excepthook is not old_thread
    finally:
        sys.excepthook = old_sys
        threading.excepthook = old_thread
