from __future__ import annotations

import importlib
import os

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.capture.pending import CaptureSessionService


def _ui_module():
    return importlib.import_module("tooldrawer_studio.ui.capture_tray")


def _png_bytes(width: int = 40, height: int = 24) -> bytes:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[4:-4, 6:-6] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_qr_image_is_square_and_nonempty():
    app = QApplication.instance() or QApplication([])
    module = _ui_module()

    image = module.qr_image("http://192.168.1.2:8123/upload?token=abc")

    assert image.isNull() is False
    assert image.width() == image.height()
    assert image.width() > 100
    assert app is not None


def test_capture_tray_shows_phone_and_webcam_items_and_preview():
    app = QApplication.instance() or QApplication([])
    module = _ui_module()
    service = CaptureSessionService()
    service.add_bytes("phone", _png_bytes(), "phone.png")
    service.add_bytes("webcam", _png_bytes(), "webcam.png")

    widget = module.CaptureTrayWidget(service)
    widget.refresh()

    assert widget.list_widget.count() == 2
    assert "phone" in widget.list_widget.item(0).text().lower()
    assert "webcam" in widget.list_widget.item(1).text().lower()
    assert widget.preview_label.pixmap() is not None
    widget.close()
    assert app is not None


def test_rotate_and_promote_apply_to_selected_item_without_consuming_anything():
    app = QApplication.instance() or QApplication([])
    module = _ui_module()
    service = CaptureSessionService()
    first = service.add_bytes("phone", _png_bytes(50, 20), "phone.png")
    second = service.add_bytes("webcam", _png_bytes(30, 30), "webcam.png")
    promoted: list[str] = []

    widget = module.CaptureTrayWidget(service)
    widget.set_promote_callback(promoted.append)
    widget.refresh()
    widget.list_widget.setCurrentRow(0)
    widget.rotate_button.click()
    widget.promote_button.click()

    assert service.items()[0].quarter_turns == 1
    assert promoted == [first.id]
    assert [item.id for item in service.items()] == [first.id, second.id]
    assert widget.list_widget.count() == 2
    widget.close()
    assert app is not None


def test_delete_removes_only_selected_item():
    app = QApplication.instance() or QApplication([])
    module = _ui_module()
    service = CaptureSessionService()
    first = service.add_bytes("phone", _png_bytes(), "one.png")
    second = service.add_bytes("webcam", _png_bytes(), "two.png")

    widget = module.CaptureTrayWidget(service)
    widget.refresh()
    widget.list_widget.setCurrentRow(0)
    widget.delete_button.click()

    assert [item.id for item in service.items()] == [second.id]
    assert widget.list_widget.count() == 1
    assert first.id != second.id
    widget.close()
    assert app is not None
