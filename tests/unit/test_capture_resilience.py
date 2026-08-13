from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from tooldrawer_studio.capture.pending import CaptureSessionService
from tooldrawer_studio.capture.phone_server import PhoneUploadServer
from tooldrawer_studio.capture.phone_session import PhoneSession
from tooldrawer_studio.capture.webcam import CameraInfo, WebcamCaptureService
from tooldrawer_studio.ui.release_window import ReleaseMainWindow


class _CameraBackend:
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


def _import_button(window: ReleaseMainWindow) -> QPushButton:
    return next(
        button
        for button in window.findChildren(QPushButton)
        if button.text() == "Import Photo"
    )


def _window(monkeypatch, tmp_path) -> ReleaseMainWindow:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    return ReleaseMainWindow()


def test_no_cameras_is_recoverable_and_import_stays_available(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.webcam_service = WebcamCaptureService(
            window.capture_session, backend=_CameraBackend()
        )
        window._toggle_webcam_panel()
        assert window.webcam_panel is not None
        assert window.webcam_panel.status_label.text() == "No cameras found"
        assert _import_button(window).isEnabled()
    finally:
        window.close()


def test_camera_open_failure_stays_inside_webcam_feature(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        backend = _CameraBackend(
            (CameraInfo(0, "Fixture Camera"),), RuntimeError("camera busy")
        )
        window.webcam_service = WebcamCaptureService(window.capture_session, backend=backend)
        window._toggle_webcam_panel()
        assert window.webcam_panel is not None
        window.webcam_panel._toggle_camera()
        assert "camera busy" in window.webcam_panel.status_label.text()
        assert _import_button(window).isEnabled()
    finally:
        window.close()


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

    class _FailingPhoneServer:
        is_running = False

        def start(self):
            raise failure

        def stop(self):
            return

    try:
        window.phone_server = _FailingPhoneServer()
        monkeypatch.setattr(window, "_show_error", lambda exc: errors.append(str(exc)))
        window._start_phone_session()
        assert errors == [str(failure)]
        assert window.phone_status.text() == "Phone capture: could not start"
        assert window.start_phone_button.isEnabled()
        assert _import_button(window).isEnabled()
    finally:
        window.close()


def test_phone_session_stops_when_bound_address_disappears():
    captures = CaptureSessionService()
    session = PhoneSession(captures)
    addresses = ["127.0.0.1"]
    server = PhoneUploadServer(
        session,
        allow_test_loopback=True,
        address_supplier=lambda: tuple(addresses),
        watcher_interval=60.0,
    )
    try:
        server.start(host="127.0.0.1")
        addresses.clear()
        assert server.check_health() is False
        assert server.is_running is False
        assert session.is_active is False
    finally:
        server.stop()


def test_phone_session_fails_closed_if_address_refresh_raises():
    captures = CaptureSessionService()
    session = PhoneSession(captures)
    state = {"raise": False}

    def addresses():
        if state["raise"]:
            raise OSError("network enumeration failed")
        return ("127.0.0.1",)

    server = PhoneUploadServer(
        session,
        allow_test_loopback=True,
        address_supplier=addresses,
        watcher_interval=60.0,
    )
    try:
        server.start(host="127.0.0.1")
        state["raise"] = True
        assert server.check_health() is False
        assert server.is_running is False
        assert session.is_active is False
    finally:
        server.stop()
