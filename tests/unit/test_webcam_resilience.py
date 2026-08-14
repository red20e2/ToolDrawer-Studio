from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from tooldrawer_studio.capture.webcam import CameraInfo, WebcamCaptureService
from tooldrawer_studio.ui.release_window import ReleaseMainWindow


class _Backend:
    def __init__(self, cameras=(), open_error: Exception | None = None):
        self.cameras = tuple(cameras)
        self.open_error = open_error

    def enumerate(self):
        return self.cameras

    def open(self, index: int) -> None:
        if self.open_error is not None:
            raise self.open_error

    def read(self):
        raise RuntimeError("not used")

    def release(self) -> None:
        return


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


def test_no_cameras_is_recoverable(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.webcam_service = WebcamCaptureService(window.capture_session, backend=_Backend())
        window._toggle_webcam_panel()
        assert window.webcam_panel is not None
        assert window.webcam_panel.status_label.text() == "No cameras found"
        assert _import_enabled(window)
    finally:
        window.close()


def test_camera_open_failure_does_not_disable_import(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        backend = _Backend((CameraInfo(0, "Fixture Camera"),), RuntimeError("camera busy"))
        window.webcam_service = WebcamCaptureService(window.capture_session, backend=backend)
        window._toggle_webcam_panel()
        assert window.webcam_panel is not None
        window.webcam_panel._toggle_camera()
        assert "camera busy" in window.webcam_panel.status_label.text()
        assert _import_enabled(window)
    finally:
        window.close()
