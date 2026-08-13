import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.generation.scoops import build_scoop_cutter
from tooldrawer_studio.generation.validation import validate_generation
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _project(*, x_mm: float = 50.0, y_mm: float = 40.0) -> Project:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(20.0, 0.0),
        Point2D(20.0, 12.0),
        Point2D(0.0, 12.0),
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
        foam_width_mm=100.0,
        foam_height_mm=80.0,
        border_mm=0.0,
        grab_clearance_mm=12.0,
        placements=[
            ToolPlacement(
                tool_id=tool.id,
                x_mm=x_mm,
                y_mm=y_mm,
                grab_side="right",
                is_placed=True,
            )
        ],
        review_required=False,
    )
    project = Project(id="p", name="Drawer", tools=[tool], layout=layout)
    project.generation_settings.minimum_wall_mm = 2.0
    project.generation_settings.minimum_floor_mm = 2.0
    return project


def test_none_grab_side_produces_no_scoop():
    project = _project()
    placement = project.layout.placements[0]
    placement.grab_side = "none"
    assert (
        build_scoop_cutter(
            project.tools[0],
            placement,
            project.layout,
            project.generation_settings,
            12.0,
            6.0,
        )
        is None
    )


def test_off_override_disables_scoop():
    project = _project()
    tool = project.tools[0]
    project.generation_settings.tool_scoop_modes[tool.id] = "off"
    assert (
        build_scoop_cutter(
            tool,
            project.layout.placements[0],
            project.layout,
            project.generation_settings,
            12.0,
            6.0,
        )
        is None
    )


def test_scoop_direction_rotates_with_tool():
    project = _project()
    placement = project.layout.placements[0]
    placement.rotation_deg = 90.0
    result = build_scoop_cutter(
        project.tools[0],
        placement,
        project.layout,
        project.generation_settings,
        12.0,
        6.0,
    )
    assert result is not None
    cavity = oriented_cavity_polygon(project.tools[0], placement)
    assert result.cutter.val().BoundingBox().ymax > cavity.bounds[3]


def test_scoop_shrinks_before_violating_boundary():
    project = _project(x_mm=78.0)
    project.generation_settings.minimum_wall_mm = 3.0
    result = build_scoop_cutter(
        project.tools[0],
        project.layout.placements[0],
        project.layout,
        project.generation_settings,
        12.0,
        6.0,
    )
    assert result is not None
    assert result.shrunk is True
    assert result.width_mm < 12.0


def test_scoop_never_breaks_minimum_floor():
    project = _project()
    project.generation_settings.minimum_floor_mm = 3.0
    result = build_scoop_cutter(
        project.tools[0],
        project.layout.placements[0],
        project.layout,
        project.generation_settings,
        8.0,
        6.0,
    )
    assert result is not None
    assert result.depth_mm <= 5.0 + 1e-9


def test_scoop_respects_default_arrange_grab_clearance():
    project = _project()
    project.layout.grab_clearance_mm = 4.0
    result = build_scoop_cutter(
        project.tools[0],
        project.layout.placements[0],
        project.layout,
        project.generation_settings,
        12.0,
        6.0,
    )
    assert result is not None
    assert result.shrunk is True
    assert result.depth_mm <= 2.5 + 1e-9


def test_scoop_respects_per_tool_grab_clearance_override():
    project = _project()
    project.layout.placements[0].grab_clearance_override_mm = 3.2
    result = build_scoop_cutter(
        project.tools[0],
        project.layout.placements[0],
        project.layout,
        project.generation_settings,
        12.0,
        6.0,
    )
    assert result is not None
    assert result.depth_mm <= 2.0 + 1e-9


def test_impossible_scoop_returns_validation_error_not_silent_geometry_change():
    project = _project(x_mm=78.0)
    project.generation_settings.minimum_wall_mm = 10.0
    result = validate_generation(project, body_height_mm=12.0)
    assert any(
        issue.code == "scoop_invalid"
        and issue.severity == "error"
        and issue.tool_ids == ("tool-1",)
        for issue in result.issues
    )


def test_shrunk_scoop_emits_nonblocking_warning():
    project = _project(x_mm=78.0)
    project.generation_settings.minimum_wall_mm = 3.0
    result = validate_generation(project, body_height_mm=12.0)
    assert result.valid
    assert any(issue.code == "scoop_shrunk" for issue in result.issues)
