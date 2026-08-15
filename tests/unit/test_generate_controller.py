from pathlib import Path

import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _controller() -> WorkflowController:
    contour = [
        Point2D(-10.0, -5.0),
        Point2D(10.0, -5.0),
        Point2D(10.0, 5.0),
        Point2D(-10.0, 5.0),
    ]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.0,
        pocket_depth_override_mm=6.0,
    )
    layout = LayoutState(
        mode="foam",
        foam_width_mm=80.0,
        foam_height_mm=50.0,
        border_mm=4.0,
        placements=[
            ToolPlacement(tool_id="tool-1", x_mm=40.0, y_mm=25.0, is_placed=True)
        ],
        review_required=False,
    )
    controller = WorkflowController()
    controller.bundle.project = Project(
        id="project-1",
        name="Drawer",
        tools=[tool],
        layout=layout,
    )
    controller.select_tool(tool.id)
    return controller


def test_successful_generate_records_current_fingerprint():
    controller = _controller()
    assert not controller.generation_is_current()
    result = controller.generate_organizer()
    assert controller.generation_is_current()
    assert controller.project.generation_state.review_required is False
    assert controller.project.generation_state.last_generated_fingerprint == result.fingerprint
    assert controller.generated_result is result


def test_geometry_change_marks_generation_stale_without_regenerating():
    controller = _controller()
    old = controller.generate_organizer()
    controller.move_tool("tool-1", 41.0, 25.0)
    assert controller.project.generation_state.review_required is True
    assert not controller.generation_is_current()
    assert controller.generated_result is None
    assert controller.project.generation_state.last_generated_fingerprint == old.fingerprint


def test_measure_depth_change_marks_generation_stale():
    controller = _controller()
    controller.generate_organizer()
    controller.set_pocket_depth_override("tool-1", 7.0)
    assert controller.project.generation_state.review_required is True
    assert not controller.generation_is_current()


def test_generation_setting_change_marks_generation_stale():
    controller = _controller()
    controller.generate_organizer()
    controller.set_generation_settings(minimum_floor_mm=2.5)
    assert controller.project.generation_settings.minimum_floor_mm == pytest.approx(2.5)
    assert not controller.generation_is_current()


def test_tool_rename_stales_generation_when_labels_are_enabled():
    controller = _controller()
    controller.generate_organizer()
    controller.rename_tool("tool-1", "Renamed Ratchet")
    assert not controller.generation_is_current()


def test_tool_rename_does_not_stale_when_labels_are_disabled():
    controller = _controller()
    controller.set_generation_settings(labels_enabled=False)
    controller.generate_organizer()
    controller.rename_tool("tool-1", "Renamed Ratchet")
    assert controller.generation_is_current()


def test_export_before_current_generation_is_blocked(tmp_path: Path):
    controller = _controller()
    with pytest.raises(ValueError, match="Generate the current organizer"):
        controller.export_organizer(tmp_path, {"step"})


def test_selective_export_uses_current_generated_model(tmp_path: Path):
    controller = _controller()
    controller.generate_organizer()
    paths = controller.export_organizer(tmp_path, {"step", "dxf"})
    assert paths.step is not None and paths.step.exists()
    assert paths.dxf is not None and paths.dxf.exists()
    assert paths.stl is None


def test_reopen_does_not_restore_in_memory_generated_cad(tmp_path: Path):
    controller = _controller()
    controller.generate_organizer()
    project_path = tmp_path / "drawer.tds"
    controller.save(project_path)

    reopened = WorkflowController.open(project_path)
    assert reopened.generated_result is None
    assert not reopened.generation_is_current()
    assert reopened.project.generation_state.review_required is True
