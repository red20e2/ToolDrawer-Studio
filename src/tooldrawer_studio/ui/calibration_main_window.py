from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget

from tooldrawer_studio.domain.models import CalibrationRecord
from tooldrawer_studio.ui.calibration_workspace import CalibrationWorkspace
from tooldrawer_studio.ui.main_window import MainWindow as LegacyMainWindow
from tooldrawer_studio.ui.workflow_controller import (
    MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE,
)


class CalibrationMainWindow(LegacyMainWindow):
    """Main workflow shell with the V0.1.1 canvas-first calibration stage."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(1100, 700)
        self.resize(1400, 900)

    def _capture_stage(self) -> QWidget:
        self.calibration_workspace = CalibrationWorkspace(self.capture_session)
        self.calibration_view = self.calibration_workspace.view
        self.calibration_sidebar = self.calibration_workspace.sidebar
        self.capture_tray = self.calibration_sidebar.capture_tray
        self.capture_tray.set_promote_callback(self._promote_pending_capture)

        # Compatibility aliases let the established workflow/controller methods keep
        # doing their jobs while the actual widgets now live inside the sidebar.
        self.webcam_button = self.calibration_sidebar.webcam_button
        self.start_phone_button = self.calibration_sidebar.start_phone_button
        self.stop_phone_button = self.calibration_sidebar.stop_phone_button
        self.phone_qr_label = self.calibration_sidebar.phone_qr_label
        self.phone_status = self.calibration_sidebar.phone_status
        self.phone_url_label = self.calibration_sidebar.phone_url_label
        self.capture_layout = self.calibration_sidebar.webcam_host_layout

        self.calibration_mode = self.calibration_sidebar.calibration_mode
        self.known_distance_label = self.calibration_sidebar.known_distance_label
        self.known_distance = self.calibration_sidebar.known_distance
        self.object_width_label = self.calibration_sidebar.object_width_label
        self.object_width = self.calibration_sidebar.object_width
        self.object_height_label = self.calibration_sidebar.object_height_label
        self.object_height = self.calibration_sidebar.object_height
        self.target_paper_label = self.calibration_sidebar.target_paper_label
        self.target_paper = self.calibration_sidebar.target_paper
        self.calibration_instruction = self.calibration_sidebar.calibration_instruction
        self.calibrate_button = self.calibration_sidebar.calibrate_button
        self.save_target_button = self.calibration_sidebar.save_target_button
        self.detect_target_button = self.calibration_sidebar.detect_target_button
        self.calibration_status = self.calibration_sidebar.calibration_status
        self.low_confidence_override = self.calibration_sidebar.low_confidence_override

        sidebar = self.calibration_sidebar
        sidebar.importRequested.connect(self._import_photo)
        sidebar.openProjectRequested.connect(self._open_project)
        sidebar.webcamRequested.connect(self._toggle_webcam_panel)
        sidebar.startPhoneRequested.connect(self._start_phone_session)
        sidebar.stopPhoneRequested.connect(self._stop_phone_session)
        sidebar.clearPointsRequested.connect(self.calibration_view.clear_points)
        sidebar.calibrateRequested.connect(self._calibrate)
        sidebar.saveTargetRequested.connect(self._save_target)
        sidebar.detectTargetRequested.connect(self._detect_target_calibration)
        sidebar.fitRequested.connect(self.calibration_view.fit_image)
        sidebar.actualSizeRequested.connect(self.calibration_view.set_actual_size)

        self.calibration_view.zoomChanged.connect(sidebar.set_zoom_percent)
        self.calibration_view.pointsChanged.connect(self._update_calibration_preview)
        self.known_distance.valueChanged.connect(self._update_calibration_preview)
        self.calibration_mode.currentIndexChanged.connect(self._calibration_mode_changed)
        self._calibration_mode_changed()
        return self.calibration_workspace

    def _calibration_mode_changed(self, _index: int | None = None) -> None:
        mode = str(self.calibration_mode.currentData())
        required = {
            "known_distance": 2,
            "paper_a4": 4,
            "paper_letter": 4,
            "known_object": 4,
            "target": 0,
        }[mode]
        self.calibration_view.set_required_points(required)
        self.calibration_sidebar.set_calibration_mode_state(mode)
        self._update_calibration_preview()

    def _update_calibration_preview(self, _value: object | None = None) -> None:
        mode = str(self.calibration_mode.currentData())
        required = {
            "known_distance": 2,
            "paper_a4": 4,
            "paper_letter": 4,
            "known_object": 4,
            "target": 0,
        }[mode]
        points = self.calibration_view.points_px()
        pixel_distance: float | None = None
        scale_px_per_mm: float | None = None
        if mode == "known_distance" and len(points) == 2:
            pixel_distance = math.hypot(
                points[1].x_px - points[0].x_px,
                points[1].y_px - points[0].y_px,
            )
            known_mm = float(self.known_distance.value())
            if known_mm > 0.0:
                scale_px_per_mm = pixel_distance / known_mm
        self.calibration_sidebar.set_point_preview(
            len(points),
            required,
            pixel_distance,
            scale_px_per_mm,
        )

    def _update_calibration_status(self, record: CalibrationRecord) -> None:
        super()._update_calibration_status(record)
        if self._measure_calibration_tool_id is not None:
            text = (
                f"Side-view calibration: {record.method}, "
                f"confidence {record.confidence:.0%}"
            )
        else:
            text = (
                f"Calibration: {record.method}, "
                f"confidence {record.confidence:.0%}"
            )
        self.calibration_sidebar.set_calibration_status(text, record.confidence)
        low = (
            self._measure_calibration_tool_id is None
            and record.confidence < MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE
        )
        self.low_confidence_override.setVisible(low)

    def _reset_for_uncalibrated_active_image(self) -> None:
        super()._reset_for_uncalibrated_active_image()
        self.calibration_sidebar.set_calibration_status("Calibration: not set")
        self._update_calibration_preview()
