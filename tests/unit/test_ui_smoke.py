import os
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.calibration_view import CalibrationImageView
from tooldrawer_studio.ui.main_window import MainWindow
from tooldrawer_studio.ui.measure_panel import MeasurePanel
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _png_bytes(width: int = 50, height: int = 20) -> bytes:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[3:-3, 5:-5] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_main_window_constructs_with_five_workflow_stages():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.windowTitle() == "ToolDrawer Studio"
    assert window.tabs.count() == 5
    assert [window.tabs.tabText(index) for index in range(5)] == [
        "1. Import & Calibrate",
        "2. Detect & Edit",
        "3. Measure",
        "4. Pocket Settings",
        "5. Save & Export",
    ]
    assert isinstance(window.calibration_view, CalibrationImageView)
    assert isinstance(window.measure_panel, MeasurePanel)
    assert window.calibration_mode.count() == 5
    assert window.calibration_mode.itemText(0) == "Known distance"
    assert window.calibration_mode.itemText(4) == "Printable target"
    assert window.low_confidence_override.isHidden()
    assert not hasattr(window, "tool_depth")
    assert not hasattr(window, "pocket_depth")
    assert window.pocket_depth_label.text() == "No resolved pocket depth"
    window.close()
    assert app is not None


def test_low_confidence_calibration_stays_on_warning_screen(
    monkeypatch, simple_tools_image_path: Path
):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.controller.import_image(simple_tools_image_path)
    monkeypatch.setattr(
        window.calibration_view,
        "points_px",
        lambda: (PixelPoint(0.0, 0.0), PixelPoint(20.0, 0.0)),
    )
    window.known_distance.setValue(10.0)
    window.tabs.setCurrentIndex(0)

    window._calibrate()

    assert window.controller.active_calibration is not None
    assert window.controller.active_calibration.confidence < 0.75
    assert not window.low_confidence_override.isHidden()
    assert window.tabs.currentIndex() == 0
    window.close()
    assert app is not None


def test_opening_uncalibrated_project_disables_detect_stage(
    monkeypatch, tmp_path: Path, simple_tools_image_path: Path
):
    app = QApplication.instance() or QApplication([])
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    project_path = tmp_path / "uncalibrated.tds"
    controller.save(project_path)

    window = MainWindow()
    window.tabs.setTabEnabled(1, True)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(project_path), "ToolDrawer Studio (*.tds)"),
    )

    window._open_project()

    assert not window.tabs.isTabEnabled(1)
    assert not window.tabs.isTabEnabled(2)
    window.close()
    assert app is not None


def test_capture_controls_and_shared_tray_are_present():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.webcam_button.text() == "Webcam…"
    assert window.start_phone_button.text() == "Start Phone Session"
    assert window.stop_phone_button.text() == "Stop Phone Session"
    assert window.stop_phone_button.isEnabled() is False
    assert window.phone_status.text() == "Phone capture: stopped"
    assert window.capture_tray.list_widget.count() == 0
    window.close()
    assert app is not None


def test_promote_pending_capture_adds_to_project_without_consuming_tray_item():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    item = window.capture_session.add_bytes("phone", _png_bytes(), "phone.png")
    window.capture_tray.refresh()

    window._promote_pending_capture(item.id)

    assert len(window.controller.project.captures) == 1
    assert window.controller.active_capture_id is not None
    assert window.controller.active_calibration is None
    assert [pending.id for pending in window.capture_session.items()] == [item.id]
    assert window.capture_tray.list_widget.count() == 1
    assert all(window.tabs.isTabEnabled(index) is False for index in (1, 2, 3, 4))
    window.close()
    assert app is not None


def test_start_and_stop_phone_session_update_qr_ui_without_real_listener():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    class FakeServer:
        def __init__(self) -> None:
            self.is_running = False
            self.stop_count = 0

        def start(self):
            self.is_running = True
            return SimpleNamespace(
                host="192.168.1.20",
                port=8123,
                upload_url="http://192.168.1.20:8123/upload?token=test-token",
            )

        def stop(self) -> None:
            self.is_running = False
            self.stop_count += 1

    fake = FakeServer()
    window.phone_server = fake

    window._start_phone_session()
    assert window.phone_status.text() == "Phone capture: active"
    assert "192.168.1.20:8123" in window.phone_url_label.text()
    assert window.phone_qr_label.pixmap() is not None
    assert window.start_phone_button.isEnabled() is False
    assert window.stop_phone_button.isEnabled() is True

    window._stop_phone_session()
    assert fake.stop_count == 1
    assert window.phone_status.text() == "Phone capture: stopped"
    assert window.start_phone_button.isEnabled() is True
    assert window.stop_phone_button.isEnabled() is False
    window.close()
    assert app is not None


def test_qr_render_failure_stops_listener_and_clears_phone_ui(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    class FakeServer:
        def __init__(self) -> None:
            self.is_running = False
            self.stop_count = 0

        def start(self):
            self.is_running = True
            return SimpleNamespace(
                host="192.168.1.20",
                port=8123,
                upload_url="http://192.168.1.20:8123/upload?token=test-token",
            )

        def stop(self) -> None:
            self.is_running = False
            self.stop_count += 1

    def fail_qr(_url: str):
        raise RuntimeError("Could not render QR")

    fake = FakeServer()
    errors: list[Exception] = []
    window.phone_server = fake
    monkeypatch.setattr("tooldrawer_studio.ui.main_window.qr_image", fail_qr)
    monkeypatch.setattr(window, "_show_error", errors.append)

    window._start_phone_session()

    assert fake.stop_count == 1
    assert fake.is_running is False
    assert window.phone_status.text() == "Phone capture: could not start"
    assert window.start_phone_button.isEnabled() is True
    assert window.stop_phone_button.isEnabled() is False
    assert len(errors) == 1
    window.close()
    assert app is not None


def test_close_event_stops_phone_server_and_webcam_service():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    class FakeServer:
        is_running = False

        def __init__(self) -> None:
            self.stop_count = 0

        def stop(self) -> None:
            self.stop_count += 1

    class FakeWebcam:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1

    server = FakeServer()
    webcam = FakeWebcam()
    window.phone_server = server
    window.webcam_service = webcam
    window.webcam_panel = None

    window.close()

    assert server.stop_count == 1
    assert webcam.close_count == 1
    assert app is not None
