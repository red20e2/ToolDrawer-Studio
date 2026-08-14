from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.capture.pending import CaptureSessionService


def _sidebar_type():
    module = importlib.import_module("tooldrawer_studio.ui.calibration_sidebar")
    return module.CalibrationSidebar


def test_sidebar_is_narrow_scrollable_and_defaults_to_known_distance():
    app = QApplication.instance() or QApplication([])
    CalibrationSidebar = _sidebar_type()
    sidebar = CalibrationSidebar(CaptureSessionService())
    sidebar.show()
    app.processEvents()

    assert sidebar.minimumWidth() >= 300
    assert sidebar.maximumWidth() <= 340
    assert sidebar.widgetResizable() is True
    assert sidebar.calibration_mode.currentData() == "known_distance"
    assert sidebar.known_distance.value() == pytest.approx(100.0)
    assert sidebar.capture_tray.compact is True
    sidebar.close()


def test_sidebar_only_shows_fields_relevant_to_current_calibration_mode():
    app = QApplication.instance() or QApplication([])
    CalibrationSidebar = _sidebar_type()
    sidebar = CalibrationSidebar(CaptureSessionService())
    sidebar.show()
    app.processEvents()

    sidebar.set_calibration_mode_state("known_distance")
    assert sidebar.known_distance.isVisible() is True
    assert sidebar.object_width.isVisible() is False
    assert sidebar.object_height.isVisible() is False
    assert sidebar.target_paper.isVisible() is False
    assert sidebar.calibrate_button.isVisible() is True

    sidebar.set_calibration_mode_state("known_object")
    assert sidebar.known_distance.isVisible() is False
    assert sidebar.object_width.isVisible() is True
    assert sidebar.object_height.isVisible() is True
    assert sidebar.target_paper.isVisible() is False

    sidebar.set_calibration_mode_state("target")
    assert sidebar.known_distance.isVisible() is False
    assert sidebar.object_width.isVisible() is False
    assert sidebar.target_paper.isVisible() is True
    assert sidebar.calibrate_button.isVisible() is False
    assert sidebar.save_target_button.isVisible() is True
    assert sidebar.detect_target_button.isVisible() is True
    sidebar.close()


def test_point_preview_and_zoom_labels_show_engineering_values():
    app = QApplication.instance() or QApplication([])
    CalibrationSidebar = _sidebar_type()
    sidebar = CalibrationSidebar(CaptureSessionService())
    sidebar.show()
    app.processEvents()

    sidebar.set_zoom_percent(137.5)
    sidebar.set_point_preview(2, 2, 1842.6, 12.284)

    assert "137.5%" in sidebar.zoom_label.text()
    assert "2 / 2" in sidebar.point_count_label.text()
    assert "1842.6 px" in sidebar.pixel_distance_label.text()
    assert "12.284 px/mm" in sidebar.scale_label.text()
    sidebar.close()


def test_phone_state_keeps_qr_and_url_context_inside_sidebar():
    app = QApplication.instance() or QApplication([])
    CalibrationSidebar = _sidebar_type()
    sidebar = CalibrationSidebar(CaptureSessionService())
    sidebar.show()
    app.processEvents()

    sidebar.set_phone_state("Phone capture: active", "http://192.168.1.2:8123/upload")
    assert "active" in sidebar.phone_status.text().lower()
    assert "192.168.1.2" in sidebar.phone_url_label.text()
    assert sidebar.stop_phone_button.isEnabled() is True
    assert sidebar.start_phone_button.isEnabled() is False

    sidebar.set_phone_state("Phone capture: stopped")
    assert sidebar.phone_url_label.text() == ""
    assert sidebar.stop_phone_button.isEnabled() is False
    assert sidebar.start_phone_button.isEnabled() is True
    sidebar.close()
