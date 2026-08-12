from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.capture.pending import CaptureSessionService
from tooldrawer_studio.capture.webcam import CameraInfo, WebcamCaptureService
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _png_bytes(width: int = 120, height: int = 80) -> bytes:
    pixels = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(
        pixels,
        (max(2, width // 8), max(2, height // 6)),
        (max(3, width // 2), max(3, height * 4 // 5)),
        (0, 0, 0),
        -1,
    )
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


class FakeCameraBackend:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.opened = False
        self.release_count = 0

    def enumerate(self) -> tuple[CameraInfo, ...]:
        return (CameraInfo(0, "Fake Camera"),)

    def open(self, index: int) -> None:
        assert index == 0
        self.opened = True

    def read(self) -> np.ndarray:
        if not self.opened:
            raise RuntimeError("Camera is not open")
        return self.frame.copy()

    def release(self) -> None:
        if self.opened:
            self.release_count += 1
        self.opened = False


def test_phone_pending_promotes_calibrates_and_roundtrips_project(tmp_path: Path):
    pending = CaptureSessionService()
    item = pending.add_bytes("phone", _png_bytes(), "phone.png")
    payload = pending.promotion_bytes(item.id)

    controller = WorkflowController()
    capture_id = controller.import_image_bytes(payload.raw, payload.filename)
    record = controller.calibrate_known_distance(
        PixelPoint(10.0, 10.0),
        PixelPoint(110.0, 10.0),
        100.0,
    )
    project_path = tmp_path / "phone-capture.tds"
    controller.save(project_path)

    reopened = WorkflowController.open(project_path)

    assert any(capture.id == capture_id for capture in reopened.project.captures)
    assert reopened.active_capture_id == capture_id
    assert reopened.active_calibration is not None
    assert reopened.active_calibration.capture_id == capture_id
    assert reopened.active_calibration.method == record.method
    assert [pending_item.id for pending_item in pending.items()] == [item.id]


def test_fake_webcam_capture_promotes_and_roundtrips_project(tmp_path: Path):
    captures = CaptureSessionService()
    pixels = cv2.imdecode(
        np.frombuffer(_png_bytes(96, 64), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert pixels is not None
    backend = FakeCameraBackend(pixels)
    webcam = WebcamCaptureService(captures, backend=backend)
    webcam.open(0)
    item = webcam.capture()
    webcam.close()

    payload = captures.promotion_bytes(item.id)
    controller = WorkflowController()
    capture_id = controller.import_image_bytes(payload.raw, payload.filename)
    project_path = tmp_path / "webcam-capture.tds"
    controller.save(project_path)

    reopened = WorkflowController.open(project_path)

    assert reopened.active_capture_id == capture_id
    assert reopened.project.captures[-1].filename.startswith("webcam-")
    assert backend.release_count == 1
    assert captures.items()[0].source == "webcam"


def test_rotated_pending_capture_keeps_orientation_after_project_reopen(tmp_path: Path):
    pending = CaptureSessionService()
    item = pending.add_bytes("phone", _png_bytes(70, 30), "rotated-source.png")
    pending.rotate(item.id, clockwise=True)
    payload = pending.promotion_bytes(item.id)

    controller = WorkflowController()
    capture_id = controller.import_image_bytes(payload.raw, payload.filename)
    capture = next(c for c in controller.project.captures if c.id == capture_id)
    assert (capture.width_px, capture.height_px) == (30, 70)

    project_path = tmp_path / "rotated.tds"
    controller.save(project_path)
    reopened = WorkflowController.open(project_path)
    reopened_capture = next(c for c in reopened.project.captures if c.id == capture_id)
    reopened_pixels = cv2.imdecode(
        np.frombuffer(reopened.active_image_display_bytes(), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )

    assert (reopened_capture.width_px, reopened_capture.height_px) == (30, 70)
    assert reopened_pixels is not None
    assert reopened_pixels.shape[:2] == (70, 30)


def test_multiple_promoted_captures_coexist_in_one_project(tmp_path: Path):
    pending = CaptureSessionService()
    phone = pending.add_bytes("phone", _png_bytes(80, 50), "phone.png")
    webcam = pending.add_bytes("webcam", _png_bytes(60, 40), "webcam.png")
    controller = WorkflowController()

    first = pending.promotion_bytes(phone.id)
    first_id = controller.import_image_bytes(first.raw, first.filename)
    second = pending.promotion_bytes(webcam.id)
    second_id = controller.import_image_bytes(second.raw, second.filename)

    assert [capture.id for capture in controller.project.captures] == [
        first_id,
        second_id,
    ]
    assert [item.id for item in pending.items()] == [phone.id, webcam.id]

    project_path = tmp_path / "multi-capture.tds"
    controller.save(project_path)
    reopened = WorkflowController.open(project_path)

    assert [capture.id for capture in reopened.project.captures] == [
        first_id,
        second_id,
    ]
    assert reopened.active_capture_id == second_id
