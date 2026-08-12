from __future__ import annotations

import importlib

import cv2
import numpy as np
import pytest


def _pending_module():
    return importlib.import_module("tooldrawer_studio.capture.pending")


def _png_bytes(width: int = 40, height: int = 20) -> bytes:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[:, : max(1, width // 4)] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_phone_and_webcam_share_one_pending_model():
    pending = _pending_module()
    service = pending.CaptureSessionService()

    phone = service.add_bytes("phone", _png_bytes(), "phone.png")
    webcam = service.add_bytes("webcam", _png_bytes(), "webcam.png")

    assert [item.source for item in service.items()] == ["phone", "webcam"]
    assert [item.id for item in service.items()] == [phone.id, webcam.id]


def test_promotion_is_non_consuming_and_preserves_unrelated_items():
    pending = _pending_module()
    service = pending.CaptureSessionService()
    phone = service.add_bytes("phone", _png_bytes(50, 20), "phone.png")
    webcam = service.add_bytes("webcam", _png_bytes(30, 30), "webcam.png")

    service.select(phone.id)
    payload = service.promotion_bytes(phone.id)

    assert payload.filename == "phone.png"
    assert len(payload.raw) > 0
    assert service.selected().id == phone.id
    assert [item.id for item in service.items()] == [phone.id, webcam.id]


def test_rotated_promotion_uses_user_selected_orientation():
    pending = _pending_module()
    service = pending.CaptureSessionService()
    item = service.add_bytes("phone", _png_bytes(50, 20), "phone.png")

    service.rotate(item.id, clockwise=True)
    payload = service.promotion_bytes(item.id)
    decoded = cv2.imdecode(np.frombuffer(payload.raw, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert payload.filename == "phone.png"
    assert decoded is not None
    assert decoded.shape[:2] == (50, 20)
    assert service.items()[0].quarter_turns == 1


def test_four_rotations_return_preview_to_original_dimensions():
    pending = _pending_module()
    service = pending.CaptureSessionService()
    item = service.add_bytes("webcam", _png_bytes(44, 18), "webcam.png")

    for _ in range(4):
        service.rotate(item.id)
    preview = service.preview_png(item.id)
    decoded = cv2.imdecode(np.frombuffer(preview, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert decoded is not None
    assert decoded.shape[:2] == (18, 44)
    assert service.items()[0].quarter_turns == 0


def test_delete_removes_only_requested_pending_item():
    pending = _pending_module()
    service = pending.CaptureSessionService()
    first = service.add_bytes("phone", _png_bytes(), "first.png")
    second = service.add_bytes("webcam", _png_bytes(), "second.png")

    service.delete(first.id)

    assert [item.id for item in service.items()] == [second.id]
    assert service.selected().id == second.id


def test_unknown_pending_id_is_rejected():
    pending = _pending_module()
    service = pending.CaptureSessionService()

    with pytest.raises(KeyError, match="Unknown pending capture"):
        service.rotate("missing")
