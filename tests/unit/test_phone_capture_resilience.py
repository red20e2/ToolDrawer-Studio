from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from tooldrawer_studio.ui.release_window import ReleaseMainWindow


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    return ReleaseMainWindow()


def _import_enabled(window) -> bool:
    button = next(
        item for item in window.findChildren(QPushButton) if item.text() == "Import Photo"
    )
    return button.isEnabled()


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("No private/local IPv4 address is available for phone capture"),
        OSError("bind failed"),
    ],
)
def test_phone_start_failure_is_recoverable(monkeypatch, tmp_path, failure):
    window = _window(monkeypatch, tmp_path)
    errors: list[str] = []

    class FailingServer:
        is_running = False

        def start(self):
            raise failure

        def stop(self):
            return

    try:
        window.phone_server = FailingServer()
        monkeypatch.setattr(window, "_show_error", lambda exc: errors.append(str(exc)))
        window._start_phone_session()
        assert errors == [str(failure)]
        assert window.phone_status.text() == "Phone capture: could not start"
        assert window.start_phone_button.isEnabled()
        assert _import_enabled(window)
    finally:
        window.close()
