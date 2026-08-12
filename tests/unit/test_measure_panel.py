import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.ui.measure_panel import MeasurePanel
from tooldrawer_studio.ui.measurement_view import MeasurementImageView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _tool() -> ToolObject:
    contour = [Point2D(0, 0), Point2D(20, 0), Point2D(20, 10), Point2D(0, 10)]
    return ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="top-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )


def test_panel_owns_complete_measure_workflow_controls():
    app = _app()
    panel = MeasurePanel()

    assert isinstance(panel.measurement_view, MeasurementImageView)
    assert panel.attach_button.text() == "Add Side View"
    assert panel.calibrate_button.text() == "Calibrate Side View"
    assert panel.measure_button.text() == "Measure Automatically"
    assert panel.accept_button.text() == "Accept Measurement"
    assert panel.manual_points_button.text() == "Manual Two-Point"
    assert panel.reset_button.text() == "Reset to Automatic"
    assert panel.manual_thickness_apply.text() == "Use Exact Thickness"
    assert panel.source_combo is not None
    assert panel.project_exposed_height is not None
    assert panel.project_bottom_clearance is not None
    assert panel.exposed_override is not None
    assert panel.bottom_override is not None
    assert panel.suggested_depth_label is not None
    assert panel.final_depth_label is not None
    assert panel.pocket_override is not None
    assert panel.confidence_label is not None
    assert panel.warnings_label is not None
    panel.close()
    assert app is not None


def test_source_combo_uses_exact_project_and_pending_tuple_data():
    panel = MeasurePanel()
    panel.set_sources(
        [("capture-1", "top.png"), ("capture-2", "side.png")],
        [("pending-1", "phone.png")],
        selected_capture_id="capture-2",
    )

    values = [panel.source_combo.itemData(index) for index in range(panel.source_combo.count())]
    assert values == [
        ("project", "capture-1"),
        ("project", "capture-2"),
        ("pending", "pending-1"),
    ]
    assert panel.selected_source() == ("project", "capture-2")
    panel.close()


def test_no_automatic_result_disables_accept_and_inherited_value_is_distinct():
    panel = MeasurePanel()
    project = Project(id="project-1", name="Drawer")
    tool = _tool()

    panel.set_tool_state(project, tool, suggested_depth=None, final_depth=None)

    assert panel.accept_button.isEnabled() is False
    assert panel.exposed_override.isChecked() is False
    assert "project default" in panel.exposed_effective_label.text().lower()
    assert "4.000" in panel.exposed_effective_label.text()

    tool.exposed_height_override_mm = 2.5
    panel.set_tool_state(project, tool, suggested_depth=8.0, final_depth=8.0)
    assert panel.exposed_override.isChecked() is True
    assert "tool override" in panel.exposed_effective_label.text().lower()
    assert "2.500" in panel.exposed_effective_label.text()
    panel.close()


def test_automatic_result_enables_accept_and_state_labels_are_rendered():
    panel = MeasurePanel()
    project = Project(id="project-1", name="Drawer")
    tool = _tool()
    tool.automatic_thickness_mm = 12.0
    tool.automatic_thickness_confidence = 0.91
    tool.accepted_thickness_mm = 12.0
    tool.thickness_accepted = True

    panel.set_tool_state(project, tool, suggested_depth=8.8, final_depth=8.8)

    assert panel.accept_button.isEnabled() is True
    assert "91%" in panel.confidence_label.text()
    assert "8.800" in panel.suggested_depth_label.text()
    assert "8.800" in panel.final_depth_label.text()
    panel.close()
