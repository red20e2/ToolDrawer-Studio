import cadquery as cq
import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.generation.builder import (
    GenerationBlockedError,
    generate_organizer,
)
from tooldrawer_studio.generation.fingerprint import generation_fingerprint
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _tool(tool_id: str, depth: float) -> ToolObject:
    contour = [
        Point2D(-10.0, -5.0),
        Point2D(10.0, -5.0),
        Point2D(10.0, 5.0),
        Point2D(-10.0, 5.0),
    ]
    return ToolObject(
        id=tool_id,
        name=f"Tool {tool_id}",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.0,
        pocket_depth_override_mm=depth,
    )


def _foam_project() -> Project:
    tools = [_tool("a", 4.0), _tool("b", 8.0)]
    layout = LayoutState(
        mode="foam",
        foam_width_mm=100.0,
        foam_height_mm=60.0,
        spacing_mm=3.0,
        border_mm=4.0,
        placements=[
            ToolPlacement(tool_id="a", x_mm=25.0, y_mm=30.0, is_placed=True),
            ToolPlacement(tool_id="b", x_mm=70.0, y_mm=30.0, is_placed=True),
        ],
        review_required=False,
    )
    return Project(id="fp", name="Foam Drawer", tools=tools, layout=layout)


def _grid_project() -> Project:
    tool = _tool("g", 6.0)
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=1,
        grid_rows=1,
        grid_pitch_mm=42.0,
        border_mm=4.0,
        placements=[
            ToolPlacement(tool_id="g", x_mm=21.0, y_mm=21.0, is_placed=True)
        ],
        review_required=False,
    )
    return Project(id="gp", name="Grid Drawer", tools=[tool], layout=layout)


def test_generate_foam_organizer_cuts_all_tool_cavities():
    project = _foam_project()
    result = generate_organizer(project)
    assert result.body_height_mm == pytest.approx(10.0)
    assert len(result.model.solids().vals()) == 1
    assert result.model.val().isValid()
    assert result.fingerprint == generation_fingerprint(project)


def test_generate_gridfinity_organizer_is_single_valid_solid():
    result = generate_organizer(_grid_project())
    assert result.body_height_mm == pytest.approx(14.0)
    assert len(result.model.solids().vals()) == 1
    assert result.model.val().isValid()
    assert result.model.val().BoundingBox().zmax == pytest.approx(18.4, abs=1e-3)


def test_builder_refuses_hard_validation_error():
    project = _foam_project()
    project.layout.review_required = True
    with pytest.raises(GenerationBlockedError) as exc:
        generate_organizer(project)
    assert any(issue.code == "layout_review_required" for issue in exc.value.issues)


def test_builder_returns_nonblocking_warnings():
    project = _foam_project()
    project.layout.spacing_mm = 0.0
    project.generation_settings.minimum_wall_mm = 2.0
    project.layout.placements[0].x_mm = 35.0
    project.layout.placements[1].x_mm = 57.2
    result = generate_organizer(project)
    assert any(issue.severity == "warning" for issue in result.warnings)


def test_different_tool_depths_are_visible_in_final_solid():
    result = generate_organizer(_foam_project())
    shape = result.model.val()
    # At z=5, the 4 mm pocket has already ended (solid), while the 8 mm
    # pocket is still open (void).
    assert shape.isInside(cq.Vector(25.0, 30.0, 5.0))
    assert not shape.isInside(cq.Vector(70.0, 30.0, 5.0))


def test_repeated_generation_of_same_inputs_has_same_bounds_and_fingerprint():
    project = _foam_project()
    first = generate_organizer(project)
    second = generate_organizer(project)
    first_box = first.model.val().BoundingBox()
    second_box = second.model.val().BoundingBox()
    assert first.fingerprint == second.fingerprint
    assert (
        first_box.xmin,
        first_box.ymin,
        first_box.zmin,
        first_box.xmax,
        first_box.ymax,
        first_box.zmax,
    ) == pytest.approx(
        (
            second_box.xmin,
            second_box.ymin,
            second_box.zmin,
            second_box.xmax,
            second_box.ymax,
            second_box.zmax,
        )
    )
