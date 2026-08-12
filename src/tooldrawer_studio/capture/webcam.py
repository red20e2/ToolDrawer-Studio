from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

import cv2
import numpy as np

from .pending import CaptureSessionService, PendingCapture


@dataclass(frozen=True, slots=True)
class CameraInfo:
    index: int
    label: str


class CameraBackend(Protocol):
    def enumerate(self) -> tuple[CameraInfo, ...]: ...

    def open(self, index: int) -> None: ...

    def read(self) -> np.ndarray: ...

    def release(self) -> None: ...


class OpenCVCameraBackend:
    """Small OpenCV adapter so UI/services can be tested without real hardware."""

    def __init__(self, *, probe_limit: int = 10) -> None:
        if probe_limit <= 0:
            raise ValueError("Camera probe limit must be positive")
        self._probe_limit = probe_limit
        self._capture: cv2.VideoCapture | None = None

    @staticmethod
    def _new_capture(index: int) -> cv2.VideoCapture:
        if sys.platform == "win32":
            capture = cv2.VideoCapture(index, cv2.CAP_MSMF)
            if capture.isOpened():
                return capture
            capture.release()
        return cv2.VideoCapture(index, cv2.CAP_ANY)

    def enumerate(self) -> tuple[CameraInfo, ...]:
        cameras: list[CameraInfo] = []
        for index in range(self._probe_limit):
            capture = self._new_capture(index)
            try:
                if capture.isOpened():
                    cameras.append(CameraInfo(index=index, label=f"Camera {index + 1}"))
            finally:
                capture.release()
        return tuple(cameras)

    def open(self, index: int) -> None:
        self.release()
        capture = self._new_capture(index)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Could not open camera {index + 1}")
        self._capture = capture

    def read(self) -> np.ndarray:
        if self._capture is None:
            raise RuntimeError("Camera is not open")
        ok, frame = self._capture.read()
        if not ok or frame is None or frame.size == 0:
            raise RuntimeError("Could not read camera frame")
        return frame

    def release(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is not None:
            capture.release()


class WebcamCaptureService:
    def __init__(
        self,
        captures: CaptureSessionService,
        *,
        backend: CameraBackend | None = None,
    ) -> None:
        self._captures = captures
        self._backend = backend or OpenCVCameraBackend()
        self._is_open = False

    def list_cameras(self) -> tuple[CameraInfo, ...]:
        return self._backend.enumerate()

    def open(self, index: int) -> None:
        if self._is_open:
            self._backend.release()
            self._is_open = False
        try:
            self._backend.open(index)
        except Exception:
            self._is_open = False
            raise
        self._is_open = True

    def preview_frame(self) -> np.ndarray:
        if not self._is_open:
            raise RuntimeError("Camera is not open")
        return self._backend.read()

    def capture(self) -> PendingCapture:
        frame = self.preview_frame()
        ok, encoded = cv2.imencode(".png", frame)
        if not ok:
            raise RuntimeError("Could not encode camera frame")
        return self._captures.add_bytes(
            "webcam",
            encoded.tobytes(),
            f"webcam-{uuid4()}.png",
        )

    def close(self) -> None:
        if not self._is_open:
            return
        self._backend.release()
        self._is_open = False
