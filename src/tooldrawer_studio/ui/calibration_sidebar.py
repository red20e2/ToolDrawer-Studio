from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.capture.pending import CaptureSessionService
from tooldrawer_studio.ui.capture_tray import CaptureTrayWidget


class CalibrationSidebar(QScrollArea):
    importRequested = Signal()
    openProjectRequested = Signal()
    webcamRequested = Signal()
    startPhoneRequested = Signal()
    stopPhoneRequested = Signal()
    clearPointsRequested = Signal()
    calibrateRequested = Signal()
    saveTargetRequested = Signal()
    detectTargetRequested = Signal()
    fitRequested = Signal()
    actualSizeRequested = Signal()

    def __init__(
        self,
        capture_service: CaptureSessionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(300)
        self.setMaximumWidth(340)

        self.content_widget = QWidget()
        self.setWidget(self.content_widget)
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(self._section_label("Project & Capture"))
        self.import_button = QPushButton("Import Photo")
        self.open_project_button = QPushButton("Open .tds Project")
        self.webcam_button = QPushButton("Webcam…")
        self.start_phone_button = QPushButton("Start Phone Session")
        self.stop_phone_button = QPushButton("Stop Phone Session")
        self.stop_phone_button.setEnabled(False)
        for button in (
            self.import_button,
            self.open_project_button,
            self.webcam_button,
            self.start_phone_button,
            self.stop_phone_button,
        ):
            layout.addWidget(button)

        self.import_button.clicked.connect(self.importRequested)
        self.open_project_button.clicked.connect(self.openProjectRequested)
        self.webcam_button.clicked.connect(self.webcamRequested)
        self.start_phone_button.clicked.connect(self.startPhoneRequested)
        self.stop_phone_button.clicked.connect(self.stopPhoneRequested)

        self.phone_status = QLabel("Phone capture: stopped")
        self.phone_status.setWordWrap(True)
        self.phone_url_label = QLabel()
        self.phone_url_label.setWordWrap(True)
        self.phone_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.phone_qr_label = QLabel()
        self.phone_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phone_qr_label.setMaximumHeight(180)
        self.phone_qr_label.setVisible(False)
        layout.addWidget(self.phone_status)
        layout.addWidget(self.phone_url_label)
        layout.addWidget(self.phone_qr_label)

        self.webcam_host = QWidget()
        self.webcam_host_layout = QVBoxLayout(self.webcam_host)
        self.webcam_host_layout.setContentsMargins(0, 0, 0, 0)
        self.webcam_host_layout.setSpacing(4)
        layout.addWidget(self.webcam_host)

        self.capture_tray = CaptureTrayWidget(capture_service, compact=True)
        layout.addWidget(self.capture_tray)

        layout.addWidget(self._section_label("View"))
        view_actions = QHBoxLayout()
        self.fit_button = QPushButton("Fit Image")
        self.actual_size_button = QPushButton("100%")
        view_actions.addWidget(self.fit_button)
        view_actions.addWidget(self.actual_size_button)
        layout.addLayout(view_actions)
        self.zoom_label = QLabel("Zoom: 100.0%")
        layout.addWidget(self.zoom_label)
        self.fit_button.clicked.connect(self.fitRequested)
        self.actual_size_button.clicked.connect(self.actualSizeRequested)

        layout.addWidget(self._section_label("Calibration"))
        form = QFormLayout()
        self.calibration_mode = QComboBox()
        self.calibration_mode.addItem("Known distance", "known_distance")
        self.calibration_mode.addItem("A4 sheet", "paper_a4")
        self.calibration_mode.addItem("US Letter", "paper_letter")
        self.calibration_mode.addItem("Known-size object", "known_object")
        self.calibration_mode.addItem("Printable target", "target")
        form.addRow("Method", self.calibration_mode)

        self.known_distance_label = QLabel("Known distance")
        self.known_distance = self._number(0.001, 100000.0, 100.0)
        form.addRow(self.known_distance_label, self.known_distance)

        self.object_width_label = QLabel("Object width")
        self.object_width = self._number(0.001, 100000.0, 100.0)
        form.addRow(self.object_width_label, self.object_width)

        self.object_height_label = QLabel("Object height")
        self.object_height = self._number(0.001, 100000.0, 50.0)
        form.addRow(self.object_height_label, self.object_height)

        self.target_paper_label = QLabel("Target paper")
        self.target_paper = QComboBox()
        self.target_paper.addItem("A4", "a4")
        self.target_paper.addItem("US Letter", "letter")
        form.addRow(self.target_paper_label, self.target_paper)
        layout.addLayout(form)

        self.calibration_instruction = QLabel()
        self.calibration_instruction.setWordWrap(True)
        layout.addWidget(self.calibration_instruction)

        self.point_count_label = QLabel("Selected points: 0 / 2")
        self.pixel_distance_label = QLabel("Pixel distance: --")
        self.scale_label = QLabel("Calculated scale: --")
        layout.addWidget(self.point_count_label)
        layout.addWidget(self.pixel_distance_label)
        layout.addWidget(self.scale_label)

        actions = QHBoxLayout()
        self.clear_points_button = QPushButton("Clear Points")
        self.calibrate_button = QPushButton("Calibrate")
        actions.addWidget(self.clear_points_button)
        actions.addWidget(self.calibrate_button)
        layout.addLayout(actions)
        self.save_target_button = QPushButton("Save Printable Target…")
        self.detect_target_button = QPushButton("Detect Target")
        layout.addWidget(self.save_target_button)
        layout.addWidget(self.detect_target_button)

        self.clear_points_button.clicked.connect(self.clearPointsRequested)
        self.calibrate_button.clicked.connect(self.calibrateRequested)
        self.save_target_button.clicked.connect(self.saveTargetRequested)
        self.detect_target_button.clicked.connect(self.detectTargetRequested)

        layout.addWidget(self._section_label("Status"))
        self.calibration_status = QLabel("Calibration: not set")
        self.calibration_status.setWordWrap(True)
        self.confidence_label = QLabel()
        self.confidence_label.setVisible(False)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        self.low_confidence_override = QCheckBox(
            "Allow low-confidence automatic tracing"
        )
        self.low_confidence_override.setVisible(False)
        layout.addWidget(self.calibration_status)
        layout.addWidget(self.confidence_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.low_confidence_override)
        layout.addStretch()

        self.calibration_mode.currentIndexChanged.connect(
            self._calibration_mode_changed
        )
        self.set_calibration_mode_state("known_distance")

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(f"<b>{text}</b>")
        return label

    @staticmethod
    def _number(
        minimum: float,
        maximum: float,
        value: float,
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setValue(value)
        widget.setSuffix(" mm")
        return widget

    def _calibration_mode_changed(self, _index: int) -> None:
        self.set_calibration_mode_state(str(self.calibration_mode.currentData()))

    def set_calibration_mode_state(self, mode: str) -> None:
        required = {
            "known_distance": 2,
            "paper_a4": 4,
            "paper_letter": 4,
            "known_object": 4,
            "target": 0,
        }
        if mode not in required:
            raise ValueError(f"Unknown calibration mode: {mode}")

        index = self.calibration_mode.findData(mode)
        if index >= 0 and self.calibration_mode.currentIndex() != index:
            self.calibration_mode.blockSignals(True)
            self.calibration_mode.setCurrentIndex(index)
            self.calibration_mode.blockSignals(False)

        known_distance = mode == "known_distance"
        known_object = mode == "known_object"
        target = mode == "target"
        for widget in (self.known_distance_label, self.known_distance):
            widget.setVisible(known_distance)
        for widget in (
            self.object_width_label,
            self.object_width,
            self.object_height_label,
            self.object_height,
        ):
            widget.setVisible(known_object)
        for widget in (self.target_paper_label, self.target_paper):
            widget.setVisible(target)
        self.save_target_button.setVisible(target)
        self.detect_target_button.setVisible(target)
        self.calibrate_button.setVisible(not target)

        instructions = {
            "known_distance": "Click two points with a known real-world distance between them.",
            "paper_a4": "Click A4 corners in order: top-left, top-right, bottom-right, bottom-left.",
            "paper_letter": "Click Letter corners in order: top-left, top-right, bottom-right, bottom-left.",
            "known_object": "Click object corners in order: top-left, top-right, bottom-right, bottom-left, then enter its real dimensions.",
            "target": "Print the ToolDrawer target at 100% scale, photograph it with the tools, then use Detect Target.",
        }
        self.calibration_instruction.setText(instructions[mode])
        self.set_point_preview(0, required[mode], None, None)

    def set_point_preview(
        self,
        selected: int,
        required: int,
        pixel_distance: float | None,
        scale_px_per_mm: float | None,
    ) -> None:
        self.point_count_label.setText(f"Selected points: {selected} / {required}")
        self.pixel_distance_label.setText(
            "Pixel distance: --"
            if pixel_distance is None
            else f"Pixel distance: {pixel_distance:.1f} px"
        )
        self.scale_label.setText(
            "Calculated scale: --"
            if scale_px_per_mm is None
            else f"Calculated scale: {scale_px_per_mm:.3f} px/mm"
        )

    def set_zoom_percent(self, percent: float) -> None:
        self.zoom_label.setText(f"Zoom: {float(percent):.1f}%")

    def set_calibration_status(
        self,
        text: str,
        confidence: float | None = None,
    ) -> None:
        self.calibration_status.setText(text)
        if confidence is None:
            self.confidence_label.clear()
            self.confidence_label.setVisible(False)
        else:
            self.confidence_label.setText(f"Confidence: {confidence:.0%}")
            self.confidence_label.setVisible(True)

    def set_warning(self, text: str | None) -> None:
        self.warning_label.setText(text or "")
        self.warning_label.setVisible(bool(text))

    def set_phone_state(
        self,
        status: str,
        upload_url: str | None = None,
        qr: QPixmap | None = None,
    ) -> None:
        self.phone_status.setText(status)
        self.phone_url_label.setText(upload_url or "")
        if qr is None or qr.isNull():
            self.phone_qr_label.clear()
            self.phone_qr_label.setVisible(False)
        else:
            self.phone_qr_label.setPixmap(qr)
            self.phone_qr_label.setVisible(True)
        active = bool(upload_url) or qr is not None or "active" in status.lower()
        self.start_phone_button.setEnabled(not active)
        self.stop_phone_button.setEnabled(active)
