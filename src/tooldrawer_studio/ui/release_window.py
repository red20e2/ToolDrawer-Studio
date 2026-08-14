from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressBar

from tooldrawer_studio.preferences import Preferences
from tooldrawer_studio.project_state import ProjectEditTracker
from tooldrawer_studio.ui.busy_scope import busy_ui
from tooldrawer_studio.ui.calibration_main_window import CalibrationMainWindow
from tooldrawer_studio.ui.workflow_controller import WorkflowController


class ReleaseMainWindow(CalibrationMainWindow):
    """Production shell for release-only persistence and safety behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.preferences = Preferences.load()
        self.project_edit_tracker = ProjectEditTracker(self.controller.project)
        self.operation_progress = QProgressBar(self)
        self.operation_progress.setVisible(False)
        self.operation_progress.setTextVisible(True)
        self.operation_progress.setMinimumWidth(220)
        self.statusBar().addPermanentWidget(self.operation_progress)

    def _dialog_directory(self, kind: str) -> str:
        values = {
            "project": self.preferences.project_directory,
            "export": self.preferences.export_directory,
            "photo": self.preferences.photo_import_directory,
        }
        if kind not in values:
            raise KeyError(f"Unknown dialog directory kind: {kind}")
        return values[kind] or ""

    def _remember_project_path(self, path: Path) -> None:
        self.preferences.set_project_directory(path.parent)
        self.preferences.add_recent_project(path)
        self.preferences.save()

    def _remember_export_directory(self, path: Path) -> None:
        self.preferences.set_export_directory(path)
        self.preferences.save()

    def _remember_photo_directory(self, path: Path) -> None:
        self.preferences.set_photo_import_directory(path)
        self.preferences.save()

    def _confirm_discard_unsaved(self) -> bool:
        if not self.project_edit_tracker.has_unsaved_changes():
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save changes before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return bool(self._save_project())
        if choice == QMessageBox.StandardButton.Discard:
            return True
        return False

    def _import_photo(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Tool Photo",
            self._dialog_directory("photo"),
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not filename or not self._confirm_discard_unsaved():
            return
        try:
            path = Path(filename)
            new_controller = WorkflowController()
            new_tracker = ProjectEditTracker(new_controller.project)
            new_controller.import_image(path)
            self.controller = new_controller
            self.project_edit_tracker = new_tracker
            self._measurement_warnings.clear()
            self._reset_for_uncalibrated_active_image()
            self._remember_photo_directory(path.parent)
        except Exception as exc:
            self._show_error(exc)

    def _save_project(self) -> bool:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save ToolDrawer Project",
            self._dialog_directory("project"),
            "ToolDrawer Studio (*.tds)",
        )
        if not filename:
            return False
        try:
            path = Path(filename)
            if path.suffix.lower() != ".tds":
                path = path.with_suffix(".tds")
            self.controller.save(path)
            self.project_edit_tracker.mark_saved()
            self._remember_project_path(path)
            self.export_status.setText(f"Saved {path}")
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def _open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open ToolDrawer Project",
            self._dialog_directory("project"),
            "ToolDrawer Studio (*.tds)",
        )
        if not filename or not self._confirm_discard_unsaved():
            return
        try:
            path = Path(filename)
            new_controller = WorkflowController.open(path)
            self.controller = new_controller
            self.project_edit_tracker = ProjectEditTracker(new_controller.project)
            self._measurement_warnings.clear()
            if self.controller.project.tools:
                self.controller.activate_capture(
                    self.controller.project.tools[0].source_capture_id
                )
            if self.controller.project.captures:
                self.calibration_view.set_image_bytes(
                    self.controller.active_image_display_bytes()
                )
            calibration = self.controller.active_calibration
            if calibration is not None:
                self._set_mode_from_calibration(calibration)
                self._update_calibration_status(calibration)
            else:
                self.calibration_status.setText("Calibration: not set")
                self.calibration_sidebar.set_calibration_status("Calibration: not set")
                self.low_confidence_override.setChecked(False)
                self.low_confidence_override.setVisible(False)
                self.tabs.setTabEnabled(1, bool(self.controller.project.tools))
            self._populate_tools()
            has_tools = bool(self.controller.project.tools)
            self.tabs.setTabEnabled(2, has_tools)
            self.tabs.setTabEnabled(3, has_tools)
            self.tabs.setTabEnabled(
                4, has_tools and self.controller.project.layout is not None
            )
            self.tabs.setTabEnabled(5, has_tools)
            if has_tools:
                self._refresh_measure_state()
            else:
                self._refresh_arrange_state()
            self._remember_project_path(path)
        except Exception as exc:
            self._show_error(exc)

    def _generate_model(self) -> None:
        with busy_ui(self, "Generating organizer"):
            super()._generate_model()
        self._refresh_generate_state()

    def _export_generated_files(self, formats: set[str]) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Export Manufacturing Files",
            self._dialog_directory("export"),
        )
        if not directory:
            return
        with busy_ui(self, "Exporting organizer"):
            try:
                path = Path(directory)
                paths = self.controller.export_organizer(path, formats)
                exported = [
                    str(exported_path)
                    for exported_path in (paths.step, paths.stl, paths.dxf)
                    if exported_path is not None
                ]
                self.export_status.setText("Exported:\n" + "\n".join(exported))
                self._remember_export_directory(path)
            except Exception as exc:
                self._show_error(exc)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.isVisible() and not self._confirm_discard_unsaved():
            event.ignore()
            return
        super().closeEvent(event)
