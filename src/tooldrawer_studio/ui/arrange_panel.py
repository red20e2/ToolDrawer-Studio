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
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.ui.theme import mark_primary, muted_label


class ArrangePanel(QWidget):
    layoutRequested = Signal(object)
    defaultsChanged = Signal(object)
    snapChanged = Signal(bool)
    autoArrangeRequested = Signal()
    repackRequested = Signal()
    rotationPolicyChanged = Signal(str)
    grabSideChanged = Signal(str)
    grabOverrideChanged = Signal(object)
    lockChanged = Signal(bool)
    rotateRequested = Signal(float)
    alignRequested = Signal(str)
    distributeRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Foam / Drawer", "foam")
        self.mode_combo.addItem("Gridfinity", "gridfinity")
        form.addRow("Layout mode", self.mode_combo)

        self.foam_width_label = QLabel("Inside width")
        self.foam_width = self._mm(1.0, 5000.0, 300.0)
        self.foam_height_label = QLabel("Inside depth")
        self.foam_height = self._mm(1.0, 5000.0, 200.0)
        form.addRow(self.foam_width_label, self.foam_width)
        form.addRow(self.foam_height_label, self.foam_height)

        self.grid_columns_label = QLabel("Grid columns")
        self.grid_columns = QSpinBox()
        self.grid_columns.setRange(1, 100)
        self.grid_columns.setValue(6)
        self.grid_rows_label = QLabel("Grid rows")
        self.grid_rows = QSpinBox()
        self.grid_rows.setRange(1, 100)
        self.grid_rows.setValue(5)
        self.grid_pitch_label = QLabel("Grid pitch")
        self.grid_pitch = self._mm(1.0, 500.0, 42.0)
        self.grid_dimensions_label = QLabel("Physical size")
        self.grid_dimensions = QLabel()
        form.addRow(self.grid_columns_label, self.grid_columns)
        form.addRow(self.grid_rows_label, self.grid_rows)
        form.addRow(self.grid_pitch_label, self.grid_pitch)
        form.addRow(self.grid_dimensions_label, self.grid_dimensions)

        self.spacing = self._mm(0.0, 100.0, 3.0)
        self.border = self._mm(0.0, 100.0, 4.0)
        self.default_grab = self._mm(0.0, 200.0, 12.0)
        self.snap_enabled = QCheckBox("Enable snapping")
        self.snap_increment = self._mm(0.001, 100.0, 1.0)
        form.addRow("Tool-to-tool structural spacing", self.spacing)
        form.addRow("Outer border margin", self.border)
        form.addRow("Default grab-side clearance", self.default_grab)
        form.addRow("Snap", self.snap_enabled)
        form.addRow("Movement snap increment", self.snap_increment)
        root.addLayout(form)

        self.spacing_note = muted_label(
            "Layout spacing is separate from each tool's manufacturing pocket clearance."
        )
        root.addWidget(self.spacing_note)

        setup_actions = QHBoxLayout()
        self.apply_layout_button = QPushButton("Apply Layout Size")
        self.auto_button = mark_primary(QPushButton("Auto Arrange"))
        self.repack_button = QPushButton("Re-pack Unlocked")
        setup_actions.addWidget(self.apply_layout_button)
        setup_actions.addWidget(self.auto_button)
        setup_actions.addWidget(self.repack_button)
        root.addLayout(setup_actions)

        tool_form = QFormLayout()
        self.rotation_policy = QComboBox()
        self.rotation_policy.addItem("Free", "free")
        self.rotation_policy.addItem("90° only", "orthogonal")
        self.rotation_policy.addItem("Fixed", "fixed")
        self.grab_side = QComboBox()
        for label, value in (
            ("None", "none"),
            ("Left", "left"),
            ("Right", "right"),
            ("Top", "top"),
            ("Bottom", "bottom"),
        ):
            self.grab_side.addItem(label, value)
        self.grab_override = QCheckBox("Override grab clearance")
        self.grab_override_value = self._mm(0.0, 200.0, 12.0)
        grab_row = QHBoxLayout()
        grab_row.addWidget(self.grab_override)
        grab_row.addWidget(self.grab_override_value)
        self.locked = QCheckBox("Lock selected tool")
        self.rotation_value = QDoubleSpinBox()
        self.rotation_value.setRange(-3600.0, 3600.0)
        self.rotation_value.setDecimals(2)
        self.rotation_value.setSuffix("°")
        self.rotate_button = QPushButton("Rotate")
        rotate_row = QHBoxLayout()
        rotate_row.addWidget(self.rotation_value)
        rotate_row.addWidget(self.rotate_button)
        tool_form.addRow("Selected tool rotation rule", self.rotation_policy)
        tool_form.addRow("Grab side", self.grab_side)
        tool_form.addRow("Grab clearance", grab_row)
        tool_form.addRow("Lock", self.locked)
        tool_form.addRow("Set rotation", rotate_row)
        root.addLayout(tool_form)

        align_row = QHBoxLayout()
        self.align_combo = QComboBox()
        for label, value in (
            ("Left", "left"),
            ("Right", "right"),
            ("Top", "top"),
            ("Bottom", "bottom"),
            ("Center X", "center_x"),
            ("Center Y", "center_y"),
        ):
            self.align_combo.addItem(label, value)
        self.align_button = QPushButton("Align Selection")
        self.distribute_horizontal = QPushButton("Distribute Horizontal")
        self.distribute_vertical = QPushButton("Distribute Vertical")
        align_row.addWidget(self.align_combo)
        align_row.addWidget(self.align_button)
        align_row.addWidget(self.distribute_horizontal)
        align_row.addWidget(self.distribute_vertical)
        root.addLayout(align_row)

        self.status_label = QLabel("Arrange: no layout configured")
        self.status_label.setWordWrap(True)
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addWidget(self.validation_label)
        self.unplaced_label = QLabel("Unplaced tools")
        root.addWidget(self.unplaced_label)
        self.unplaced_list = QListWidget()
        self.unplaced_list.setMaximumHeight(110)
        root.addWidget(self.unplaced_list)
        root.addStretch()

        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.grid_columns.valueChanged.connect(self._update_grid_dimensions)
        self.grid_rows.valueChanged.connect(self._update_grid_dimensions)
        self.grid_pitch.valueChanged.connect(self._update_grid_dimensions)
        self.apply_layout_button.clicked.connect(self._emit_layout_request)
        self.spacing.valueChanged.connect(
            lambda value: self._emit_default("spacing_mm", value)
        )
        self.border.valueChanged.connect(
            lambda value: self._emit_default("border_mm", value)
        )
        self.default_grab.valueChanged.connect(
            lambda value: self._emit_default("grab_clearance_mm", value)
        )
        self.snap_increment.valueChanged.connect(
            lambda value: self._emit_default("snap_increment_mm", value)
        )
        self.snap_enabled.toggled.connect(self._emit_snap)
        self.auto_button.clicked.connect(self.autoArrangeRequested.emit)
        self.repack_button.clicked.connect(self.repackRequested.emit)
        self.rotation_policy.currentIndexChanged.connect(self._emit_rotation_policy)
        self.grab_side.currentIndexChanged.connect(self._emit_grab_side)
        self.grab_override.toggled.connect(self._emit_grab_override)
        self.grab_override_value.valueChanged.connect(self._emit_grab_override_value)
        self.locked.toggled.connect(self._emit_lock)
        self.rotate_button.clicked.connect(
            lambda: self.rotateRequested.emit(float(self.rotation_value.value()))
        )
        self.align_button.clicked.connect(
            lambda: self.alignRequested.emit(str(self.align_combo.currentData()))
        )
        self.distribute_horizontal.clicked.connect(
            lambda: self.distributeRequested.emit("horizontal")
        )
        self.distribute_vertical.clicked.connect(
            lambda: self.distributeRequested.emit("vertical")
        )

        self._mode_changed()
        self._update_grid_dimensions()
        self._sync_grab_override()

    @staticmethod
    def _mm(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(3)
        widget.setValue(value)
        widget.setSuffix(" mm")
        return widget

    def _mode_changed(self, _index: int | None = None) -> None:
        is_grid = self.mode_combo.currentData() == "gridfinity"
        for widget in (
            self.grid_columns_label,
            self.grid_columns,
            self.grid_rows_label,
            self.grid_rows,
            self.grid_pitch_label,
            self.grid_pitch,
            self.grid_dimensions_label,
            self.grid_dimensions,
        ):
            widget.setVisible(is_grid)
        for widget in (
            self.foam_width_label,
            self.foam_width,
            self.foam_height_label,
            self.foam_height,
        ):
            widget.setVisible(not is_grid)

    def _update_grid_dimensions(self, _value: float | int | None = None) -> None:
        width = self.grid_columns.value() * self.grid_pitch.value()
        height = self.grid_rows.value() * self.grid_pitch.value()
        self.grid_dimensions.setText(f"{width:.3f} × {height:.3f} mm")

    def _emit_layout_request(self) -> None:
        if self._updating:
            return
        if self.mode_combo.currentData() == "gridfinity":
            self.layoutRequested.emit(
                (
                    "gridfinity",
                    int(self.grid_columns.value()),
                    int(self.grid_rows.value()),
                    float(self.grid_pitch.value()),
                )
            )
        else:
            self.layoutRequested.emit(
                (
                    "foam",
                    float(self.foam_width.value()),
                    float(self.foam_height.value()),
                )
            )

    def _emit_default(self, name: str, value: float) -> None:
        if not self._updating:
            self.defaultsChanged.emit((name, float(value)))

    def _emit_snap(self, checked: bool) -> None:
        if not self._updating:
            self.snapChanged.emit(bool(checked))

    def _emit_rotation_policy(self, _index: int) -> None:
        if not self._updating:
            self.rotationPolicyChanged.emit(str(self.rotation_policy.currentData()))

    def _emit_grab_side(self, _index: int) -> None:
        if not self._updating:
            self.grabSideChanged.emit(str(self.grab_side.currentData()))

    def _sync_grab_override(self) -> None:
        self.grab_override_value.setEnabled(self.grab_override.isChecked())

    def _emit_grab_override(self, checked: bool) -> None:
        self._sync_grab_override()
        if not self._updating:
            self.grabOverrideChanged.emit(
                float(self.grab_override_value.value()) if checked else None
            )

    def _emit_grab_override_value(self, value: float) -> None:
        if not self._updating and self.grab_override.isChecked():
            self.grabOverrideChanged.emit(float(value))

    def _emit_lock(self, checked: bool) -> None:
        if not self._updating:
            self.lockChanged.emit(bool(checked))

    def set_state(
        self,
        project: Project,
        layout: LayoutState | None,
        placement: ToolPlacement | None,
        *,
        placed_count: int,
        total_count: int,
        validation_messages: Iterable[str] = (),
    ) -> None:
        self._updating = True
        try:
            if layout is not None:
                index = self.mode_combo.findData(layout.mode)
                if index >= 0:
                    self.mode_combo.setCurrentIndex(index)
                if layout.mode == "gridfinity":
                    assert layout.grid_columns is not None
                    assert layout.grid_rows is not None
                    self.grid_columns.setValue(layout.grid_columns)
                    self.grid_rows.setValue(layout.grid_rows)
                    self.grid_pitch.setValue(layout.grid_pitch_mm)
                else:
                    assert layout.foam_width_mm is not None
                    assert layout.foam_height_mm is not None
                    self.foam_width.setValue(layout.foam_width_mm)
                    self.foam_height.setValue(layout.foam_height_mm)
                self.spacing.setValue(layout.spacing_mm)
                self.border.setValue(layout.border_mm)
                self.default_grab.setValue(layout.grab_clearance_mm)
                self.snap_enabled.setChecked(layout.snap_enabled)
                self.snap_increment.setValue(layout.snap_increment_mm)
            else:
                self.spacing.setValue(project.default_layout_spacing_mm)
                self.border.setValue(project.default_layout_border_mm)
                self.default_grab.setValue(project.default_grab_clearance_mm)
                self.snap_increment.setValue(project.default_snap_increment_mm)
                self.grid_pitch.setValue(project.gridfinity_pitch_mm)

            if placement is not None:
                index = self.rotation_policy.findData(placement.rotation_policy)
                if index >= 0:
                    self.rotation_policy.setCurrentIndex(index)
                index = self.grab_side.findData(placement.grab_side)
                if index >= 0:
                    self.grab_side.setCurrentIndex(index)
                overridden = placement.grab_clearance_override_mm is not None
                self.grab_override.setChecked(overridden)
                self.grab_override_value.setValue(
                    placement.grab_clearance_override_mm
                    if overridden
                    else (layout.grab_clearance_mm if layout is not None else project.default_grab_clearance_mm)
                )
                self.locked.setChecked(placement.locked)
                self.rotation_value.setValue(placement.rotation_deg)
            else:
                self.locked.setChecked(False)

            unplaced_ids = list(layout.unplaced_tool_ids) if layout is not None else []
            tool_names = {tool.id: tool.name for tool in project.tools}
            self.unplaced_list.clear()
            for tool_id in unplaced_ids:
                self.unplaced_list.addItem(tool_names.get(tool_id, tool_id))
            self.unplaced_label.setVisible(bool(unplaced_ids))
            self.unplaced_list.setVisible(bool(unplaced_ids))

            unplaced = len(unplaced_ids) if layout is not None else total_count - placed_count
            parts = [f"Placed: {placed_count} / {total_count}"]
            if unplaced:
                parts.append(f"Unplaced: {unplaced}")
            if layout is not None and layout.review_required:
                parts.append("Review required")
            self.status_label.setText(" | ".join(parts))
            messages = list(validation_messages)
            self.validation_label.setText("; ".join(messages) if messages else "Layout validation: OK")
        finally:
            self._mode_changed()
            self._update_grid_dimensions()
            self._sync_grab_override()
            self._updating = False
