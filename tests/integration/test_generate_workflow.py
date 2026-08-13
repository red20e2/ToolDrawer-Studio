from pathlib import Path

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _generated_controller() -> WorkflowController:
    contour = [
        Point2D(-10.0, -5.0),
        Point2D(10.0, -5.0),
        Point2D(10.0, 5.0),
        Point2D(-10.0, 5.0),
    ]
    tools = [
        ToolObject(
            id="ratchet",
            name="Ratchet",
            source_capture_id="capture-1",
            base_contour_mm=list(contour),
            contour_mm=list(contour),
            clearance_mm=0.0,
            pocket_depth_override_mm=6.0,
        ),
        ToolObject(
            id="socket",
            name="Socket",
            source_capture_id="capture-1",
            base_contour_mm=list(contour),
            contour_mm=list(contour),
            clearance_mm=0.0,
            pocket_depth_override_mm=8.0,
        ),
    ]
    layout = LayoutState(
        mode="foam",
        foam_width_mm=120.0,
        foam_height_mm=70.0,
        border_mm=4.0,
        placements=[
            ToolPlacement(tool_id="ratchet", x_mm=35.0, y_mm=35.0, is_placed=True),
            ToolPlacement(tool_id="socket", x_mm=85.0, y_mm=35.0, rotation_deg=90.0, is_placed=True),
        ],
        review_required=False,
    )
    controller = WorkflowController()
    controller.bundle.project = Project(
        id="project-1",
        name="Shop Drawer",
        tools=tools,
        layout=layout,
    )
    controller.select_tool("ratchet")
    return controller


def test_generate_workflow_builds_exports_and_reopens_without_silent_regeneration(
    tmp_path: Path,
):
    controller = _generated_controller()

    result = controller.generate_organizer()

    assert result.body_height_mm == 10.0
    assert result.model.val().isValid()
    assert controller.generation_is_current()

    export_dir = tmp_path / "exports"
    outputs = controller.export_organizer(export_dir)
    assert outputs.step is not None and outputs.step.exists()
    assert outputs.stl is not None and outputs.stl.exists()
    assert outputs.dxf is not None and outputs.dxf.exists()
    assert outputs.step.stat().st_size > 100
    assert outputs.stl.stat().st_size > 100
    assert outputs.dxf.stat().st_size > 100

    project_path = tmp_path / "drawer.tds"
    controller.save(project_path)
    reopened = WorkflowController.open(project_path)

    assert reopened.generated_result is None
    assert not reopened.generation_is_current()
    assert reopened.project.generation_state.review_required is True

    regenerated = reopened.generate_organizer()
    assert regenerated.fingerprint == result.fingerprint
    assert reopened.generation_is_current()


def test_generate_workflow_stales_export_after_upstream_placement_change(tmp_path: Path):
    controller = _generated_controller()
    controller.generate_organizer()
    controller.move_tool("ratchet", 36.0, 35.0)

    assert not controller.generation_is_current()

    try:
        controller.export_organizer(tmp_path / "stale")
    except ValueError as exc:
        assert "Generate the current organizer" in str(exc)
    else:
        raise AssertionError("Stale organizer export should be blocked")
