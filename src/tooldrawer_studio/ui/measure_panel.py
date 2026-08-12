from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.ui.measurement_view import MeasurementImageView


class MeasurePanel(QWidget):
    attachRequested = Signal()
    calibrateRequested = Signal()
    measureRequested = Signal()
    acceptRequested = Signal()
    manualEndpointsRequested = Signal()
    resetAutomaticRequested = Signal()
    manualThicknessRequested = Signal(float)
    exposedHeightChanged = Signal(object)
    bottomClearanceChanged = Signal(object)
    pocketOverrideChanged = Signal(object)
    endpointsChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False

        layout = QVBoxLayout(self)

        self.tool_label = QLabel("Tool: none selected")
        layout.addWidget(self.tool_label)

        source_row = QHBoxLayout()
        self.source_combo = QComboBox()
        self.attach_button = QPushButton("Add Side View")
        self.calibrate_button = QPushButton("Calibrate Side View")
        source_row.addWidget(QLabel("Side-view source"))
        source_row.addWidget(self.source_combo, 1)
        source_row.addWidget(self.attach_button)
        source_row.addWidget(self.calibrate_button)
        layout.addLayout(source_row)

        self.calibration_label = QLabel("Side-view calibration: not set")
        layout.addWidget(self.calibration_label)

        self.measurement_view = MeasurementImageView()
        self.measurement_view.setMinimumHeight(280)
        layout.addWidget(self.measurement_view, 1)

        measurement_actions = QHBoxLayout()
        self.measure_button = QPushButton("Measure Automatically")
        self.accept_button = QPushButton("Accept Measurement")
        self.manual_points_button = QPushButton("Manual Two-Point")
        self.reset_button = QPushButton("Reset to Automatic")
        self.accept_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        measurement_actions.addWidget(self.measure_button)
        measurement_actions.addWidget(self.accept_button)
        measurement_actions.addWidget(self.manual_points_button)
        measurement_actions.addWidget(self.reset_button)
        layout.addLayout(measurement_actions)

        result_form = QFormLayout()
        self.automatic_thickness_label = QLabel("--")
        self.accepted_thickness_label = QLabel("--")
        self.confidence_label = QLabel("Confidence: --")
        self.warnings_label = QLabel("None")
        self.warnings_label.setWordWrap(True)
        result_form.addRow("Automatic thickness", self.automatic_thickness_label)
        result_form.addRow("Accepted thickness", self.accepted_thickness_label)
        result_form.addRow("Confidence", self.confidence_label)
        result_form.addRow("Warnings", self.warnings_label)
        layout.addLayout(result_form)

        manual_row = QHBoxLayout()
        self.manual_thickness = self._millimetres(0.001, 1000.0, 10.0)
        self.manual_thickness_apply = QPushButton("Use Exact Thickness")
        manual_row.addWidget(QLabel("Exact physical thickness"))
        manual_row.addWidget(self.manual_thickness)
        manual_row.addWidget(self.manual_thickness_apply)
        manual_row.addStretch()
        layout.addLayout(manual_row)

        defaults_form = QFormLayout()
        self.project_exposed_height = self._millimetres(0.0, 1000.0, 4.0)
        self.project_bottom_clearance = self._millimetres(0.0, 1000.0, 0.8)
        defaults_form.addRow("Project exposed-height default", self.project_exposed_height)
        defaults_form.addRow("Project bottom-clearance default", self.project_bottom_clearance)
        layout.addLayout(defaults_form)

        exposed_row = QHBoxLayout()
        self.exposed_override = QCheckBox("Override for this tool")
        self.exposed_override_value = self._millimetres(0.0, 1000.0, 4.0)
        self.exposed_effective_label = QLabel("Effective: --")
        exposed_row.addWidget(self.exposed_override)
        exposed_row.addWidget(self.exposed_override_value)
        exposed_row.addWidget(self.exposed_effective_label, 1)
        layout.addLayout(exposed_row)

        bottom_row = QHBoxLayout()
        self.bottom_override = QCheckBox("Override for this tool")
        self.bottom_override_value = self._millimetres(0.0, 1000.0, 0.8)
        self.bottom_effective_label = QLabel("Effective: --")
        bottom_row.addWidget(self.bottom_override)
        bottom_row.addWidget(self.bottom_override_value)
        bottom_row.addWidget(self.bottom_effective_label, 1)
        layout.addLayout(bottom_row)

        depth_form = QFormLayout()
        self.suggested_depth_label = QLabel("--")
        self.final_depth_label = QLabel("--")
        depth_form.addRow("Suggested pocket depth", self.suggested_depth_label)
        depth_form.addRow("Final pocket depth", self.final_depth_label)
        layout.addLayout(depth_form)

        pocket_row = QHBoxLayout()
        self.pocket_override = QCheckBox("Override final pocket depth")
        self.pocket_override_value = self._millimetres(0.001, 1000.0, 5.0)
        pocket_row.addWidget(self.pocket_override)
        pocket_row.addWidget(self.pocket_override_value)
        pocket_row.addStretch()
        layout.addLayout(pocket_row)

        self.review_label = QLabel()
        self.review_label.setWordWrap(True)
        layout.addWidget(self.review_label)

        self.attach_button.clicked.connect(self.attachRequested.emit)
        self.calibrate_button.clicked.connect(self.calibrateRequested.emit)
        self.measure_button.clicked.connect(self.measureRequested.emit)
        self.accept_button.clicked.connect(self.acceptRequested.emit)
        self.manual_points_button.clicked.connect(self.manualEndpointsRequested.emit)
        self.reset_button.clicked.connect(self.resetAutomaticRequested.emit)
        self.manual_thickness_apply.clicked.connect(
            lambda: self.manualThicknessRequested.emit(self.manual_thickness.value())
        )
        self.measurement_view.endpointsChanged.connect(self.endpointsChanged.emit)

        self.project_exposed_height.valueChanged.connect(
            self._project_exposed_changed
        )
        self.project_bottom_clearance.valueChanged.connect(
            self._project_bottom_changed
        )
        self.exposed_override.toggled.connect(self._tool_exposed_changed)
        self.exposed_override_value.valueChanged.connect(self._tool_exposed_value_changed)
        self.bottom_override.toggled.connect(self._tool_bottom_changed)
        self.bottom_override_value.valueChanged.connect(self._tool_bottom_value_changed)
        self.pocket_override.toggled.connect(self._pocket_override_changed)
        self.pocket_override_value.valueChanged.connect(
            self._pocket_override_value_changed
        )

        self._sync_override_enablement()

    @staticmethod
    def _millimetres(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(3)
        widget.setValue(value)
        widget.setSuffix(" mm")
        return widget

    def set_sources(
        self,
        project_captures: Iterable[tuple[str, str]],
        pending_captures: Iterable[tuple[str, str]],
        *,
        selected_capture_id: str | None = None,
    ) -> None:
        self._updating = True
        try:
            self.source_combo.clear()
            selected_index = -1
            for capture_id, filename in project_captures:
                self.source_combo.addItem(f"Project: {filename}", ("project", capture_id))
                if capture_id == selected_capture_id:
                    selected_index = self.source_combo.count() - 1
            for pending_id, filename in pending_captures:
                self.source_combo.addItem(f"Pending: {filename}", ("pending", pending_id))
            if selected_index >= 0:
                self.source_combo.setCurrentIndex(selected_index)
        finally:
            self._updating = False

    def selected_source(self) -> tuple[str, str] | None:
        data = self.source_combo.currentData()
        if not isinstance(data, tuple) or len(data) != 2:
            return None
        return str(data[0]), str(data[1])

    @staticmethod
    def _mm_text(value: float | None) -> str:
        return "--" if value is None else f"{value:.3f} mm"

    def set_tool_state(
        self,
        project: Project,
        tool: ToolObject,
        *,
        suggested_depth: float | None,
        final_depth: float | None,
        calibration_text: str | None = None,
        warnings: Iterable[str] = (),
    ) -> None:
        self._updating = True
        try:
            self.tool_label.setText(f"Tool: {tool.name}")
            self.attach_button.setText(
                "Replace Side View" if tool.side_view_capture_id else "Add Side View"
            )
            self.calibration_label.setText(
                calibration_text or "Side-view calibration: not set"
            )

            self.project_exposed_height.setValue(project.default_exposed_height_mm)
            self.project_bottom_clearance.setValue(project.default_bottom_clearance_mm)

            exposed_overridden = tool.exposed_height_override_mm is not None
            self.exposed_override.setChecked(exposed_overridden)
            exposed_effective = (
                project.default_exposed_height_mm
                if tool.exposed_height_override_mm is None
                else tool.exposed_height_override_mm
            )
            self.exposed_override_value.setValue(exposed_effective)
            source = "tool override" if exposed_overridden else "project default"
            self.exposed_effective_label.setText(
                f"Effective: {exposed_effective:.3f} mm ({source})"
            )

            bottom_overridden = tool.bottom_clearance_override_mm is not None
            self.bottom_override.setChecked(bottom_overridden)
            bottom_effective = (
                project.default_bottom_clearance_mm
                if tool.bottom_clearance_override_mm is None
                else tool.bottom_clearance_override_mm
            )
            self.bottom_override_value.setValue(bottom_effective)
            source = "tool override" if bottom_overridden else "project default"
            self.bottom_effective_label.setText(
                f"Effective: {bottom_effective:.3f} mm ({source})"
            )

            self.pocket_override.setChecked(tool.pocket_depth_override_mm is not None)
            if tool.pocket_depth_override_mm is not None:
                self.pocket_override_value.setValue(tool.pocket_depth_override_mm)

            self.automatic_thickness_label.setText(
                self._mm_text(tool.automatic_thickness_mm)
            )
            self.accepted_thickness_label.setText(
                self._mm_text(tool.accepted_thickness_mm)
            )
            self.confidence_label.setText(
                "Confidence: --"
                if tool.automatic_thickness_confidence is None
                else f"Confidence: {tool.automatic_thickness_confidence:.0%}"
            )
            warning_list = list(warnings)
            self.warnings_label.setText("; ".join(warning_list) if warning_list else "None")
            self.suggested_depth_label.setText(self._mm_text(suggested_depth))
            self.final_depth_label.setText(self._mm_text(final_depth))
            self.review_label.setText(
                "Review required: preserved manual value may be stale for this side view."
                if tool.thickness_review_required
                else ""
            )

            has_automatic = tool.automatic_thickness_mm is not None
            self.accept_button.setEnabled(has_automatic)
            self.reset_button.setEnabled(has_automatic)
            self.calibrate_button.setEnabled(tool.side_view_capture_id is not None)
            self.measure_button.setEnabled(tool.side_view_capture_id is not None)
            self.manual_points_button.setEnabled(tool.side_view_capture_id is not None)
        finally:
            self._sync_override_enablement()
            self._updating = False

    def set_warnings(self, warnings: Iterable[str]) -> None:
        items = list(warnings)
        self.warnings_label.setText("; ".join(items) if items else "None")

    def _sync_override_enablement(self) -> None:
        self.exposed_override_value.setEnabled(self.exposed_override.isChecked())
        self.bottom_override_value.setEnabled(self.bottom_override.isChecked())
        self.pocket_override_value.setEnabled(self.pocket_override.isChecked())

    def _project_exposed_changed(self, value: float) -> None:
        if not self._updating:
            self.exposedHeightChanged.emit(("project", float(value)))

    def _project_bottom_changed(self, value: float) -> None:
        if not self._updating:
            self.bottomClearanceChanged.emit(("project", float(value)))

    def _tool_exposed_changed(self, checked: bool) -> None:
        self._sync_override_enablement()
        if not self._updating:
            self.exposedHeightChanged.emit(
                ("tool", float(self.exposed_override_value.value()) if checked else None)
            )

    def _tool_exposed_value_changed(self, value: float) -> None:
        if not self._updating and self.exposed_override.isChecked():
            self.exposedHeightChanged.emit(("tool", float(value)))

    def _tool_bottom_changed(self, checked: bool) -> None:
        self._sync_override_enablement()
        if not self._updating:
            self.bottomClearanceChanged.emit(
                ("tool", float(self.bottom_override_value.value()) if checked else None)
            )

    def _tool_bottom_value_changed(self, value: float) -> None:
        if not self._updating and self.bottom_override.isChecked():
            self.bottomClearanceChanged.emit(("tool", float(value)))

    def _pocket_override_changed(self, checked: bool) -> None:
        self._sync_override_enablement()
        if not self._updating:
            self.pocketOverrideChanged.emit(
                float(self.pocket_override_value.value()) if checked else None
            )

    def _pocket_override_value_changed(self, value: float) -> None:
        if not self._updating and self.pocket_override.isChecked():
            self.pocketOverrideChanged.emit(float(value))
