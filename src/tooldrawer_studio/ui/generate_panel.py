from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.generation.models import GenerationValidationResult


class GeneratePanel(QWidget):
    settingsChanged = Signal(object)
    toolScoopModeChanged = Signal(str, str)
    generateRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False
        self._project: Project | None = None

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.height_mode = QComboBox()
        self.height_mode.addItem("Automatic", "auto")
        self.height_mode.addItem("Manual", "manual")
        form.addRow("Organizer height", self.height_mode)

        self.manual_height_label = QLabel("Manual height")
        self.manual_height = self._mm(0.1, 500.0, 20.0)
        form.addRow(self.manual_height_label, self.manual_height)

        self.minimum_floor = self._mm(0.0, 100.0, 2.0)
        self.minimum_wall = self._mm(0.0, 100.0, 2.0)
        self.scoops_enabled = QCheckBox("Generate finger scoops from Arrange grab sides")
        self.scoops_enabled.setChecked(True)
        form.addRow("Minimum floor", self.minimum_floor)
        form.addRow("Minimum wall", self.minimum_wall)
        form.addRow("Scoops", self.scoops_enabled)

        self.tool_selector_label = QLabel("Tool scoop override")
        self.tool_selector = QComboBox()
        form.addRow(self.tool_selector_label, self.tool_selector)
        self.tool_scoop_mode_label = QLabel("Selected tool scoop")
        self.tool_scoop_mode = QComboBox()
        self.tool_scoop_mode.addItem("Auto", "auto")
        self.tool_scoop_mode.addItem("Off", "off")
        form.addRow(self.tool_scoop_mode_label, self.tool_scoop_mode)

        self.magnets_label = QLabel("Magnets")
        self.magnets_enabled = QCheckBox("6 mm magnet recesses")
        self.magnets_enabled.setChecked(True)
        form.addRow(self.magnets_label, self.magnets_enabled)
        self.magnet_diameter_label = QLabel("Magnet diameter")
        self.magnet_diameter = self._mm(0.1, 30.0, 6.0)
        form.addRow(self.magnet_diameter_label, self.magnet_diameter)
        self.magnet_depth_label = QLabel("Magnet depth")
        self.magnet_depth = self._mm(0.1, 20.0, 2.0)
        form.addRow(self.magnet_depth_label, self.magnet_depth)

        self.screw_holes_label = QLabel("Screw holes")
        self.screw_holes = QCheckBox("M3-compatible screw passages")
        form.addRow(self.screw_holes_label, self.screw_holes)
        self.screw_diameter_label = QLabel("Screw diameter")
        self.screw_diameter = self._mm(0.1, 20.0, 3.2)
        form.addRow(self.screw_diameter_label, self.screw_diameter)

        self.stacking_lip_label = QLabel("Stacking lip")
        self.stacking_lip = QCheckBox("Enable Gridfinity stacking lip")
        self.stacking_lip.setChecked(True)
        form.addRow(self.stacking_lip_label, self.stacking_lip)
        self.height_snap_label = QLabel("Height snap")
        self.height_snap = QCheckBox("Snap automatic height upward to 7 mm units")
        self.height_snap.setChecked(True)
        form.addRow(self.height_snap_label, self.height_snap)
        root.addLayout(form)

        self.generate_button = QPushButton("Generate Organizer")
        root.addWidget(self.generate_button)
        self.currentness_label = QLabel("Generate: not generated")
        self.currentness_label.setWordWrap(True)
        root.addWidget(self.currentness_label)
        self.validation_label = QLabel("Validation: configure and review Arrange first")
        self.validation_label.setWordWrap(True)
        root.addWidget(self.validation_label)
        root.addStretch()

        self.height_mode.currentIndexChanged.connect(self._height_mode_changed)
        self.manual_height.valueChanged.connect(
            lambda value: self._emit_setting("manual_height_mm", float(value))
        )
        self.minimum_floor.valueChanged.connect(
            lambda value: self._emit_setting("minimum_floor_mm", float(value))
        )
        self.minimum_wall.valueChanged.connect(
            lambda value: self._emit_setting("minimum_wall_mm", float(value))
        )
        self.scoops_enabled.toggled.connect(
            lambda value: self._emit_setting("scoops_enabled", bool(value))
        )
        self.magnets_enabled.toggled.connect(
            lambda value: self._emit_setting("magnets_enabled", bool(value))
        )
        self.magnet_diameter.valueChanged.connect(
            lambda value: self._emit_setting("magnet_diameter_mm", float(value))
        )
        self.magnet_depth.valueChanged.connect(
            lambda value: self._emit_setting("magnet_depth_mm", float(value))
        )
        self.screw_holes.toggled.connect(
            lambda value: self._emit_setting("screw_holes_enabled", bool(value))
        )
        self.screw_diameter.valueChanged.connect(
            lambda value: self._emit_setting("screw_diameter_mm", float(value))
        )
        self.stacking_lip.toggled.connect(
            lambda value: self._emit_setting("stacking_lip_enabled", bool(value))
        )
        self.height_snap.toggled.connect(
            lambda value: self._emit_setting("gridfinity_height_snap", bool(value))
        )
        self.tool_selector.currentIndexChanged.connect(self._tool_selection_changed)
        self.tool_scoop_mode.currentIndexChanged.connect(self._emit_tool_scoop_mode)
        self.generate_button.clicked.connect(self.generateRequested.emit)
        self._height_mode_changed()
        self._set_gridfinity_visible(False)

    @staticmethod
    def _mm(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(3)
        widget.setValue(value)
        widget.setSuffix(" mm")
        return widget

    def _emit_setting(self, key: str, value: object) -> None:
        if not self._updating:
            self.settingsChanged.emit({key: value})

    def _height_mode_changed(self, _index: int | None = None) -> None:
        manual = self.height_mode.currentData() == "manual"
        self.manual_height_label.setVisible(manual)
        self.manual_height.setVisible(manual)
        if not self._updating:
            self.settingsChanged.emit(
                {
                    "height_mode": str(self.height_mode.currentData()),
                    "manual_height_mm": (
                        float(self.manual_height.value()) if manual else None
                    ),
                }
            )

    def _set_gridfinity_visible(self, visible: bool) -> None:
        for widget in (
            self.magnets_label,
            self.magnets_enabled,
            self.magnet_diameter_label,
            self.magnet_diameter,
            self.magnet_depth_label,
            self.magnet_depth,
            self.screw_holes_label,
            self.screw_holes,
            self.screw_diameter_label,
            self.screw_diameter,
            self.stacking_lip_label,
            self.stacking_lip,
            self.height_snap_label,
            self.height_snap,
        ):
            widget.setVisible(visible)

    def _tool_selection_changed(self, _index: int | None = None) -> None:
        if self._project is None:
            return
        tool_id = self.tool_selector.currentData()
        mode = self._project.generation_settings.tool_scoop_modes.get(
            str(tool_id), "auto"
        )
        self._updating = True
        try:
            index = self.tool_scoop_mode.findData(mode)
            self.tool_scoop_mode.setCurrentIndex(max(0, index))
        finally:
            self._updating = False

    def _emit_tool_scoop_mode(self, _index: int | None = None) -> None:
        if self._updating:
            return
        tool_id = self.tool_selector.currentData()
        if tool_id is None:
            return
        self.toolScoopModeChanged.emit(
            str(tool_id), str(self.tool_scoop_mode.currentData())
        )

    def set_project(self, project: Project) -> None:
        self._project = project
        settings = project.generation_settings
        self._updating = True
        try:
            self.height_mode.setCurrentIndex(self.height_mode.findData(settings.height_mode))
            self.manual_height.setValue(
                20.0 if settings.manual_height_mm is None else settings.manual_height_mm
            )
            self.minimum_floor.setValue(settings.minimum_floor_mm)
            self.minimum_wall.setValue(settings.minimum_wall_mm)
            self.scoops_enabled.setChecked(settings.scoops_enabled)
            self.magnets_enabled.setChecked(settings.magnets_enabled)
            self.magnet_diameter.setValue(settings.magnet_diameter_mm)
            self.magnet_depth.setValue(settings.magnet_depth_mm)
            self.screw_holes.setChecked(settings.screw_holes_enabled)
            self.screw_diameter.setValue(settings.screw_diameter_mm)
            self.stacking_lip.setChecked(settings.stacking_lip_enabled)
            self.height_snap.setChecked(settings.gridfinity_height_snap)
            previous = self.tool_selector.currentData()
            self.tool_selector.clear()
            for tool in project.tools:
                self.tool_selector.addItem(tool.name, tool.id)
            if previous is not None:
                index = self.tool_selector.findData(previous)
                if index >= 0:
                    self.tool_selector.setCurrentIndex(index)
            self._height_mode_changed()
        finally:
            self._updating = False
        is_grid = project.layout is not None and project.layout.mode == "gridfinity"
        self._set_gridfinity_visible(is_grid)
        self._tool_selection_changed()

    def set_validation(self, result: GenerationValidationResult) -> None:
        if not result.issues:
            self.validation_label.setText("Validation: ready")
            return
        lines = [
            ("ERROR" if issue.severity == "error" else "Warning")
            + f": {issue.message}"
            for issue in result.issues
        ]
        self.validation_label.setText("\n".join(lines))

    def set_currentness(self, current: bool) -> None:
        if current:
            self.currentness_label.setText("Generate: current and ready to export")
        elif self._project is not None and self._project.generation_state.last_generated_fingerprint:
            self.currentness_label.setText("Generate: stale, regenerate before export")
        else:
            self.currentness_label.setText("Generate: not generated")
