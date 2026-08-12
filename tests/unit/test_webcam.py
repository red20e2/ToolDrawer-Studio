from __future__ import annotations

import importlib

import numpy as np
import pytest

from tooldrawer_studio.capture.pending import CaptureSessionService


class FakeBackend:
    def __init__(self, *, fail_read: bool = False, fail_open: bool = False) -> None:
        self.fail_read = fail_read
        self.fail_open = fail_open
        self.opened_index: int | None = None
        self.release_count = 0
        self.open_calls: list[int] = []
        self.frame = np.zeros((24, 36, 3), dtype=np.uint8)
        self.frame[4:20, 6:30] = (255, 255, 255)

    def enumerate(self):
        module = _webcam_module()
        return (
            module.CameraInfo(0, "Camera 1"),
            module.CameraInfo(1, "Camera 2"),
        )

    def open(self, index: int) -> None:
        self.open_calls.append(index)
        if self.fail_open:
            raise RuntimeError("Could not open camera")
        self.opened_index = index

    def read(self) -> np.ndarray:
        if self.opened_index is None:
            raise RuntimeError("Camera is not open")
        if self.fail_read:
            raise RuntimeError("Could not read camera frame")
        return self.frame.copy()

    def release(self) -> None:
        if self.opened_index is not None:
            self.release_count += 1
            self.opened_index = None


def _webcam_module():
    return importlib.import_module("tooldrawer_studio.capture.webcam")


def test_list_cameras_uses_backend_enumeration():
    module = _webcam_module()
    backend = FakeBackend()
    service = module.WebcamCaptureService(CaptureSessionService(), backend=backend)

    cameras = service.list_cameras()

    assert [(camera.index, camera.label) for camera in cameras] == [
        (0, "Camera 1"),
        (1, "Camera 2"),
    ]


def test_webcam_capture_enters_shared_pending_service():
    module = _webcam_module()
    captures = CaptureSessionService()
    backend = FakeBackend()
    service = module.WebcamCaptureService(captures, backend=backend)

    service.open(0)
    preview = service.preview_frame()
    item = service.capture()

    assert preview.shape == (24, 36, 3)
    assert item.source == "webcam"
    assert item.id == captures.items()[0].id
    assert len(captures.items()) == 1


def test_failed_read_creates_no_pending_capture():
    module = _webcam_module()
    captures = CaptureSessionService()
    backend = FakeBackend(fail_read=True)
    service = module.WebcamCaptureService(captures, backend=backend)
    service.open(0)

    with pytest.raises(RuntimeError, match="read camera frame"):
        service.capture()

    assert captures.items() == ()


def test_failed_open_leaves_service_without_camera():
    module = _webcam_module()
    captures = CaptureSessionService()
    backend = FakeBackend(fail_open=True)
    service = module.WebcamCaptureService(captures, backend=backend)

    with pytest.raises(RuntimeError, match="open camera"):
        service.open(0)

    with pytest.raises(RuntimeError, match="not open"):
        service.preview_frame()
    assert captures.items() == ()


def test_opening_replacement_camera_releases_previous_handle():
    module = _webcam_module()
    backend = FakeBackend()
    service = module.WebcamCaptureService(CaptureSessionService(), backend=backend)

    service.open(0)
    service.open(1)

    assert backend.release_count == 1
    assert backend.open_calls == [0, 1]
    assert backend.opened_index == 1


def test_close_is_idempotent_and_releases_open_camera_once():
    module = _webcam_module()
    backend = FakeBackend()
    service = module.WebcamCaptureService(CaptureSessionService(), backend=backend)
    service.open(0)

    service.close()
    service.close()

    assert backend.release_count == 1
    with pytest.raises(RuntimeError, match="not open"):
        service.preview_frame()
