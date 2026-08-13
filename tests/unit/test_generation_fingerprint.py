import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.generation.fingerprint import (
    generation_fingerprint,
    required_body_height_mm,
    resolve_body_height_mm,
)
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _tool(tool_id: str, depth_mm: float) -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(20.0, 0.0),
        Point2D(20.0, 10.0),
        Point2D(0.0, 10.0),
    ]
    return ToolObject(
        id=tool_id,
        name=f"Tool {tool_id}",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.6,
        pocket_depth_override_mm=depth_mm,
    )


def _foam_project() -> Project:
    tools = [_tool("a", 8.0), _tool("b", 12.0)]
    layout = LayoutState(
        mode="foam",
        foam_width_mm=120.0,
        foam_height_mm=80.0,
        placements=[
            ToolPlacement(tool_id="a", x_mm=30.0, y_mm=30.0, is_placed=True),
            ToolPlacement(tool_id="b", x_mm=80.0, y_mm=40.0, rotation_deg=30.0, is_placed=True),
        ],
        review_required=False,
    )
    return Project(id="p", name="Drawer", tools=tools, layout=layout)


def _gridfinity_project() -> Project:
    tool = _tool("a", 15.4)
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=2,
        grid_rows=2,
        grid_pitch_mm=42.0,
        placements=[ToolPlacement(tool_id="a", x_mm=42.0, y_mm=42.0, is_placed=True)],
        review_required=False,
    )
    return Project(id="p", name="Grid", tools=[tool], layout=layout)


def test_fingerprint_changes_when_placement_moves():
    project = _foam_project()
    before = generation_fingerprint(project)
    project.layout.placements[0].x_mm += 1.0
    assert generation_fingerprint(project) != before


def test_fingerprint_changes_when_manufacturing_input_changes():
    project = _foam_project()
    before = generation_fingerprint(project)
    project.tools[0].clearance_mm += 0.1
    assert generation_fingerprint(project) != before


def test_fingerprint_changes_when_arrange_grab_clearance_changes():
    project = _foam_project()
    before = generation_fingerprint(project)
    project.layout.grab_clearance_mm = 4.0
    assert generation_fingerprint(project) != before


def test_fingerprint_ignores_generation_state():
    project = _foam_project()
    before = generation_fingerprint(project)
    project.generation_state.last_generated_fingerprint = "old"
    project.generation_state.review_required = False
    assert generation_fingerprint(project) == before


def test_project_name_does_not_invalidate_geometry_fingerprint():
    project = _foam_project()
    before = generation_fingerprint(project)
    project.name = "Renamed Drawer"
    assert generation_fingerprint(project) == before


def test_auto_foam_height_is_deepest_pocket_plus_floor():
    project = _foam_project()
    project.generation_settings.minimum_floor_mm = 2.0
    assert required_body_height_mm(project) == pytest.approx(14.0)
    assert resolve_body_height_mm(project) == pytest.approx(14.0)


def test_gridfinity_auto_height_snaps_up_to_7mm():
    project = _gridfinity_project()
    assert required_body_height_mm(project) == pytest.approx(17.4)
    assert resolve_body_height_mm(project) == pytest.approx(21.0)


def test_manual_height_is_exact():
    project = _foam_project()
    project.generation_settings.height_mode = "manual"
    project.generation_settings.manual_height_mm = 22.25
    assert resolve_body_height_mm(project) == pytest.approx(22.25)


def test_manual_height_below_requirement_raises():
    project = _foam_project()
    project.generation_settings.height_mode = "manual"
    project.generation_settings.manual_height_mm = 13.99
    with pytest.raises(ValueError, match="at least 14.000 mm"):
        resolve_body_height_mm(project)


def test_unresolved_placed_tool_depth_raises_clear_error():
    project = _foam_project()
    project.tools[0].pocket_depth_override_mm = None
    with pytest.raises(ValueError, match="Tool a.*resolved pocket depth"):
        required_body_height_mm(project)
