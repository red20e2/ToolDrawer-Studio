from __future__ import annotations

import importlib
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.capture.webcam import CameraInfo


class FakeWebcamService:
    def __init__(
        self,
        *,
        fail_open: bool = False,
        fail_capture: bool = False,
    ) -> None:
        self.fail_open = fail_open
        self.fail_capture = fail_capture
        self.enumerate_count = 0
        self.opened: list[int] = []
        self.close_count = 0
        self.capture_count = 0
        self.frame = np.zeros((20, 30, 3), dtype=np.uint8)
        self.frame[3:17, 5:25] = (255, 255, 255)

    def list_cameras(self):
        self.enumerate_count += 1
        return (CameraInfo(0, "Camera 1"), CameraInfo(2, "USB Camera"))

    def open(self, index: int) -> None:
        if self.fail_open:
            raise RuntimeError("Could not open camera")
        self.opened.append(index)

    def preview_frame(self) -> np.ndarray:
        return self.frame.copy()

    def capture(self):
        self.capture_count += 1
        if self.fail_capture:
            raise RuntimeError("Could not capture camera frame")
        return object()

    def close(self) -> None:
        self.close_count += 1


def _panel_module():
    return importlib.import_module("tooldrawer_studio.ui.webcam_panel")


def test_webcam_panel_does_not_probe_devices_until_explicit_refresh():
    app = QApplication.instance() or QApplication([])
    module = _panel_module()
    service = FakeWebcamService()

    panel = module.WebcamPanel(service)

    assert service.enumerate_count == 0
    panel.refresh_cameras()
    assert service.enumerate_count == 1
    panel.close()
    assert app is not None


def test_webcam_panel_lists_and_opens_selected_camera():
    app = QApplication.instance() or QApplication([])
    module = _panel_module()
    service = FakeWebcamService()
    panel = module.WebcamPanel(service)

    panel.refresh_cameras()
    assert panel.camera_combo.count() == 2
    assert panel.camera_combo.itemText(1) == "USB Camera"
    panel.camera_combo.setCurrentIndex(1)
    panel.open_button.click()

    assert service.opened == [2]
    assert panel.preview_timer.isActive()
    assert panel.status_label.text() == "Camera active"
    panel.close_camera()
    panel.close()
    assert app is not None


def test_webcam_open_failure_is_reported_without_starting_preview():
    app = QApplication.instance() or QApplication([])
    module = _panel_module()
    service = FakeWebcamService(fail_open=True)
    panel = module.WebcamPanel(service)
    panel.refresh_cameras()

    panel.open_button.click()

    assert panel.preview_timer.isActive() is False
    assert panel.capture_button.isEnabled() is False
    assert "Could not open camera" in panel.status_label.text()
    panel.close()
    assert app is not None


def test_webcam_panel_capture_notifies_tray_refresh_callback():
    app = QApplication.instance() or QApplication([])
    module = _panel_module()
    service = FakeWebcamService()
    refreshes: list[bool] = []
    panel = module.WebcamPanel(service, on_capture=lambda: refreshes.append(True))

    panel.refresh_cameras()
    panel.open_button.click()
    panel.capture_button.click()

    assert service.capture_count == 1
    assert refreshes == [True]
    assert panel.status_label.text() == "Captured to pending tray"
    panel.close_camera()
    panel.close()
    assert app is not None


def test_capture_failure_is_reported_without_notifying_tray():
    app = QApplication.instance() or QApplication([])
    module = _panel_module()
    service = FakeWebcamService(fail_capture=True)
    refreshes: list[bool] = []
    panel = module.WebcamPanel(service, on_capture=lambda: refreshes.append(True))
    panel.refresh_cameras()
    panel.open_button.click()

    panel.capture_button.click()

    assert service.capture_count == 1
    assert refreshes == []
    assert "Could not capture camera frame" in panel.status_label.text()
    assert panel.preview_timer.isActive()
    panel.close_camera()
    panel.close()
    assert app is not None


def test_close_camera_stops_preview_and_releases_service():
    app = QApplication.instance() or QApplication([])
    module = _panel_module()
    service = FakeWebcamService()
    panel = module.WebcamPanel(service)

    panel.refresh_cameras()
    panel.open_button.click()
    assert panel.preview_timer.isActive()

    panel.close_camera()

    assert panel.preview_timer.isActive() is False
    assert service.close_count == 1
    panel.close()
    assert app is not None
