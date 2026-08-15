from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.preferences import Preferences
from tooldrawer_studio.ui.theme import muted_label


class HandoffDialog(QDialog):
    def __init__(self, preferences: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure handoff")
        self._preferences = preferences
        layout = QVBoxLayout(self)
        layout.addWidget(
            muted_label(
                "ToolDrawer Studio opens exported files in these local apps. "
                "Nothing is uploaded. Leave a path blank to auto-detect."
            )
        )
        form = QFormLayout()
        self.orca_path = QLineEdit(preferences.orca_slicer_path or "")
        self.freecad_path = QLineEdit(preferences.freecad_path or "")
        self.custom_name = QLineEdit(preferences.custom_handoff_name or "CNC / laser")
        self.custom_path = QLineEdit(preferences.custom_handoff_executable or "")
        self.custom_format = QComboBox()
        for label, value in (
            ("DXF", "dxf"),
            ("SVG", "svg"),
            ("PDF", "pdf"),
            ("STL", "stl"),
            ("STEP", "step"),
        ):
            self.custom_format.addItem(label, value)
        index = self.custom_format.findData(preferences.custom_handoff_format)
        self.custom_format.setCurrentIndex(max(0, index))
        form.addRow("OrcaSlicer", self._browse_row(self.orca_path))
        form.addRow("FreeCAD", self._browse_row(self.freecad_path))
        form.addRow("Custom app name", self.custom_name)
        form.addRow("Custom executable", self._browse_row(self.custom_path))
        form.addRow("Custom file type", self.custom_format)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_row(self, field: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._choose_executable(field))
        layout.addWidget(browse)
        return row

    def _choose_executable(self, field: QLineEdit) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select application",
            field.text(),
            "Programs (*.exe);;All files (*.*)",
        )
        if filename:
            field.setText(str(Path(filename)))

    def apply_to(self, preferences: Preferences) -> None:
        preferences.orca_slicer_path = self.orca_path.text().strip() or None
        preferences.freecad_path = self.freecad_path.text().strip() or None
        preferences.custom_handoff_name = self.custom_name.text().strip() or None
        preferences.custom_handoff_executable = self.custom_path.text().strip() or None
        preferences.custom_handoff_format = str(self.custom_format.currentData())
