from __future__ import annotations

from collections.abc import Callable

import cv2
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.capture.webcam import WebcamCaptureService


class WebcamPanel(QWidget):
    def __init__(
        self,
        service: WebcamCaptureService,
        *,
        on_capture: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._on_capture = on_capture
        self._camera_open = False

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.camera_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh Cameras")
        self.open_button = QPushButton("Open Camera")
        self.capture_button = QPushButton("Capture")
        self.capture_button.setEnabled(False)
        controls.addWidget(self.camera_combo, 1)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.open_button)
        controls.addWidget(self.capture_button)
        layout.addLayout(controls)

        self.preview_label = QLabel("Camera preview")
        self.preview_label.setMinimumSize(320, 220)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_label, 1)

        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(100)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.refresh_button.clicked.connect(self.refresh_cameras)
        self.open_button.clicked.connect(self._toggle_camera)
        self.capture_button.clicked.connect(self._capture)
        self.refresh_cameras()

    def refresh_cameras(self) -> None:
        current_index = self.camera_combo.currentData()
        self.camera_combo.clear()
        cameras = self._service.list_cameras()
        selected_row = 0
        for row, camera in enumerate(cameras):
            self.camera_combo.addItem(camera.label, camera.index)
            if camera.index == current_index:
                selected_row = row
        if self.camera_combo.count():
            self.camera_combo.setCurrentIndex(selected_row)
        self.open_button.setEnabled(self.camera_combo.count() > 0 or self._camera_open)

    def _toggle_camera(self) -> None:
        if self._camera_open:
            self.close_camera()
            return
        camera_index = self.camera_combo.currentData()
        if camera_index is None:
            return
        self._service.open(int(camera_index))
        self._camera_open = True
        self.open_button.setText("Close Camera")
        self.capture_button.setEnabled(True)
        self.preview_timer.start()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not self._camera_open:
            return
        try:
            frame = self._service.preview_frame()
        except RuntimeError:
            self.close_camera()
            self.preview_label.setText("Camera disconnected")
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        bytes_per_line = int(rgb.strides[0])
        image = QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image)
        target = self.preview_label.size()
        if target.width() > 0 and target.height() > 0:
            pixmap = pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.preview_label.setPixmap(pixmap)

    def _capture(self) -> None:
        if not self._camera_open:
            return
        self._service.capture()
        if self._on_capture is not None:
            self._on_capture()

    def close_camera(self) -> None:
        self.preview_timer.stop()
        if self._camera_open:
            self._service.close()
            self._camera_open = False
        self.open_button.setText("Open Camera")
        self.capture_button.setEnabled(False)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.close_camera()
        super().closeEvent(event)
