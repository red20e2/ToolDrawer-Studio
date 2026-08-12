from __future__ import annotations

import importlib

import cv2
import numpy as np
import pytest

from tooldrawer_studio.capture.pending import CaptureSessionService


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _session_module():
    return importlib.import_module("tooldrawer_studio.capture.phone_session")


def _png_bytes() -> bytes:
    pixels = np.zeros((24, 36, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_start_creates_tokenized_upload_url():
    module = _session_module()
    session = module.PhoneSession(
        CaptureSessionService(),
        token_factory=lambda: "token-a",
    )

    session.start("192.168.1.50", 8123)

    assert session.is_active is True
    assert session.token == "token-a"
    assert session.host == "192.168.1.50"
    assert session.port == 8123
    assert session.url == "http://192.168.1.50:8123/upload?token=token-a"


def test_invalid_activity_does_not_extend_idle_timeout():
    module = _session_module()
    clock = FakeClock()
    session = module.PhoneSession(
        CaptureSessionService(),
        clock=clock,
        token_factory=lambda: "token-a",
    )
    session.start("192.168.1.50", 8123)

    clock.advance(1799)
    assert session.record_page_activity("wrong") is False
    clock.advance(1)

    assert session.expire_if_idle() is True
    assert session.is_active is False


def test_authenticated_page_activity_refreshes_idle_timeout():
    module = _session_module()
    clock = FakeClock()
    session = module.PhoneSession(
        CaptureSessionService(),
        clock=clock,
        token_factory=lambda: "token-a",
    )
    session.start("192.168.1.50", 8123)

    clock.advance(1700)
    assert session.record_page_activity("token-a") is True
    refreshed_at = session.last_activity
    clock.advance(200)

    assert session.expire_if_idle() is False
    assert session.last_activity == refreshed_at
    assert session.is_active is True


def test_successful_upload_refreshes_activity_and_allows_multiple_images():
    module = _session_module()
    clock = FakeClock()
    captures = CaptureSessionService()
    session = module.PhoneSession(
        captures,
        clock=clock,
        token_factory=lambda: "token-a",
    )
    session.start("192.168.1.50", 8123)

    clock.advance(1000)
    first = session.accept_upload("token-a", _png_bytes(), "one.png")
    first_activity = session.last_activity
    clock.advance(100)
    second = session.accept_upload("token-a", _png_bytes(), "two.png")

    assert first.source == "phone"
    assert second.source == "phone"
    assert len(captures.items()) == 2
    assert session.last_activity > first_activity


def test_rejected_image_does_not_refresh_activity():
    module = _session_module()
    clock = FakeClock()
    session = module.PhoneSession(
        CaptureSessionService(),
        clock=clock,
        token_factory=lambda: "token-a",
    )
    session.start("192.168.1.50", 8123)
    started_at = session.last_activity

    clock.advance(1200)
    with pytest.raises(ValueError, match="Unsupported or invalid image"):
        session.accept_upload("token-a", b"not-image", "bad.jpg")

    assert session.last_activity == started_at


def test_invalid_token_rejects_upload_without_adding_capture():
    module = _session_module()
    captures = CaptureSessionService()
    session = module.PhoneSession(captures, token_factory=lambda: "token-a")
    session.start("192.168.1.50", 8123)

    with pytest.raises(PermissionError, match="Invalid or expired phone session"):
        session.accept_upload("wrong", _png_bytes(), "photo.png")

    assert captures.items() == ()


def test_stop_and_restart_invalidate_old_token_and_create_new_one():
    module = _session_module()
    tokens = iter(["token-a", "token-b"])
    session = module.PhoneSession(
        CaptureSessionService(),
        token_factory=lambda: next(tokens),
    )
    session.start("192.168.1.50", 8123)
    assert session.authorize("token-a") is True

    session.stop()
    assert session.authorize("token-a") is False
    with pytest.raises(RuntimeError, match="not active"):
        _ = session.url

    session.start("192.168.1.50", 8124)
    assert session.token == "token-b"
    assert session.authorize("token-a") is False
    assert session.authorize("token-b") is True
