import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.generation.validation import validate_generation
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _tool(tool_id: str, name: str, depth: float | None = 6.0) -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(20.0, 0.0),
        Point2D(20.0, 10.0),
        Point2D(0.0, 10.0),
    ]
    return ToolObject(
        id=tool_id,
        name=name,
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.0,
        pocket_depth_override_mm=depth,
    )


def _project() -> Project:
    a = _tool("a", "Ratchet")
    b = _tool("b", "Extension")
    layout = LayoutState(
        mode="foam",
        foam_width_mm=100.0,
        foam_height_mm=70.0,
        spacing_mm=3.0,
        border_mm=4.0,
        placements=[
            ToolPlacement(tool_id="a", x_mm=25.0, y_mm=30.0, is_placed=True),
            ToolPlacement(tool_id="b", x_mm=70.0, y_mm=30.0, is_placed=True),
        ],
        review_required=False,
    )
    return Project(id="p", name="Drawer", tools=[a, b], layout=layout)


def _grid_project(
    *,
    center: tuple[float, float],
    size: float,
    depth: float,
    border_mm: float = 4.0,
    grab_side: str = "none",
    grab_override_mm: float | None = None,
) -> Project:
    half = size / 2.0
    contour = [
        Point2D(-half, -half),
        Point2D(half, -half),
        Point2D(half, half),
        Point2D(-half, half),
    ]
    tool = ToolObject(
        id="g",
        name="Grid Tool",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.0,
        pocket_depth_override_mm=depth,
    )
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=1,
        grid_rows=1,
        grid_pitch_mm=42.0,
        border_mm=border_mm,
        placements=[
            ToolPlacement(
                tool_id=tool.id,
                x_mm=center[0],
                y_mm=center[1],
                grab_side=grab_side,
                grab_clearance_override_mm=grab_override_mm,
                is_placed=True,
            )
        ],
        review_required=False,
    )
    return Project(id="gp", name="Grid", tools=[tool], layout=layout)


def test_review_required_layout_blocks_generation():
    project = _project()
    project.layout.review_required = True
    result = validate_generation(project)
    assert not result.valid
    assert any(issue.code == "layout_review_required" for issue in result.issues)


def test_missing_resolved_depth_names_the_tool():
    project = _project()
    project.tools[0].pocket_depth_override_mm = None
    result = validate_generation(project)
    issue = next(issue for issue in result.issues if issue.code == "missing_depth")
    assert "Ratchet" in issue.message
    assert issue.tool_ids == ("a",)


def test_manual_height_reports_required_floor():
    project = _project()
    project.tools[0].pocket_depth_override_mm = 9.0
    project.generation_settings.minimum_floor_mm = 2.0
    project.generation_settings.height_mode = "manual"
    project.generation_settings.manual_height_mm = 10.0
    result = validate_generation(project)
    assert any(
        issue.code == "minimum_floor" and issue.severity == "error"
        for issue in result.issues
    )


def test_unplaced_tool_blocks_generation():
    project = _project()
    project.layout.placements[1].is_placed = False
    project.layout.unplaced_tool_ids = ["b"]
    result = validate_generation(project)
    assert any(issue.code == "unplaced_tool" and issue.tool_ids == ("b",) for issue in result.issues)


def test_arrange_overlap_blocks_generation():
    project = _project()
    project.layout.placements[1].x_mm = 30.0
    result = validate_generation(project)
    assert any(issue.code.startswith("layout_") for issue in result.issues)


def test_cavity_boundary_breakout_blocks_generation():
    project = _project()
    project.layout.border_mm = 0.0
    project.layout.placements[0].x_mm = 2.0
    result = validate_generation(project)
    assert any(issue.code == "cavity_boundary" for issue in result.issues)


def test_minimum_wall_between_two_cavities_blocks_generation():
    project = _project()
    project.layout.spacing_mm = 0.0
    project.generation_settings.minimum_wall_mm = 4.0
    project.layout.placements[0].x_mm = 35.0
    project.layout.placements[1].x_mm = 57.0
    result = validate_generation(project)
    assert any(issue.code == "minimum_wall" for issue in result.issues)


def test_warning_does_not_make_result_invalid():
    project = _project()
    project.generation_settings.minimum_wall_mm = 2.0
    project.layout.spacing_mm = 0.0
    project.layout.placements[0].x_mm = 35.0
    project.layout.placements[1].x_mm = 57.2
    result = validate_generation(project)
    assert result.valid
    assert any(issue.severity == "warning" for issue in result.issues)


def test_issue_order_is_deterministic():
    project = _project()
    project.layout.review_required = True
    project.layout.placements[1].is_placed = False
    first = validate_generation(project).issues
    second = validate_generation(project).issues
    assert first == second
    assert first == tuple(sorted(first, key=lambda issue: (issue.severity, issue.code, issue.tool_ids, issue.message)))


def test_magnet_cavity_collision_is_hard_error():
    project = _grid_project(center=(8.0, 8.0), size=4.0, depth=20.0)
    result = validate_generation(project, body_height_mm=21.0)
    assert any(issue.code == "gridfinity_magnet_collision" for issue in result.issues)


def test_screw_cavity_collision_is_hard_error():
    project = _grid_project(center=(8.0, 8.0), size=4.0, depth=16.0)
    project.generation_settings.magnets_enabled = False
    project.generation_settings.screw_holes_enabled = True
    result = validate_generation(project, body_height_mm=21.0)
    assert any(issue.code == "gridfinity_screw_collision" for issue in result.issues)


def test_combined_holes_preserve_minimum_material():
    project = _grid_project(center=(21.0, 21.0), size=4.0, depth=6.0)
    project.generation_settings.screw_holes_enabled = True
    project.generation_settings.screw_diameter_mm = 6.2
    result = validate_generation(project, body_height_mm=21.0)
    assert any(issue.code == "gridfinity_combined_hole" for issue in result.issues)


def test_lip_only_interference_is_locally_omitted_with_warning():
    project = _grid_project(center=(4.5, 21.0), size=1.0, depth=6.0)
    result = validate_generation(project, body_height_mm=21.0)
    assert result.valid
    assert any(issue.code == "stacking_lip_omitted" for issue in result.issues)


def test_scoop_only_lip_interference_is_reported_as_omission_warning():
    project = _grid_project(
        center=(6.0, 21.0),
        size=1.0,
        depth=6.0,
        border_mm=0.0,
        grab_side="left",
        grab_override_mm=2.0,
    )
    result = validate_generation(project, body_height_mm=21.0)
    assert result.valid
    warnings = [issue for issue in result.issues if issue.code == "stacking_lip_omitted"]
    assert warnings
    assert any("scoop" in issue.message.lower() for issue in warnings)
