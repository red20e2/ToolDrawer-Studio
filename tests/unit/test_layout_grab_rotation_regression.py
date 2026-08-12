from __future__ import annotations

import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.geometry import (
    candidate_exclusion_geometry,
    spacing_exclusion_polygon,
)
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.layout.validation import validate_layout


def _rectangle_tool(tool_id: str = "tool-1") -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(20.0, 0.0),
        Point2D(20.0, 10.0),
        Point2D(0.0, 10.0),
    ]
    return ToolObject(
        id=tool_id,
        name=tool_id,
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.0,
    )


def test_local_right_grab_zone_rotates_to_world_top_at_90_degrees():
    tool = _rectangle_tool()
    placement = ToolPlacement(
        tool_id=tool.id,
        x_mm=50.0,
        y_mm=50.0,
        rotation_deg=90.0,
        grab_side="right",
        grab_clearance_override_mm=10.0,
        is_placed=True,
    )

    normal = spacing_exclusion_polygon(tool, placement, spacing_mm=0.0)
    with_grab = candidate_exclusion_geometry(
        tool,
        placement,
        spacing_mm=0.0,
        default_grab_clearance_mm=12.0,
    )

    assert with_grab.bounds[0] == pytest.approx(normal.bounds[0])
    assert with_grab.bounds[2] == pytest.approx(normal.bounds[2])
    assert with_grab.bounds[1] == pytest.approx(normal.bounds[1])
    assert with_grab.bounds[3] == pytest.approx(normal.bounds[3] + 10.0)


def test_structural_spacing_does_not_inflate_outer_border_margin():
    tool = _rectangle_tool()
    placement = ToolPlacement(
        tool_id=tool.id,
        x_mm=14.0,
        y_mm=15.0,
        is_placed=True,
    )
    layout = LayoutState(
        mode="foam",
        foam_width_mm=40.0,
        foam_height_mm=30.0,
        border_mm=4.0,
        spacing_mm=4.0,
        placements=[placement],
    )
    project = Project(id="p", name="P", tools=[tool], layout=layout)

    result = validate_layout(project, layout)

    assert result.valid is True
    assert not any(issue.code == "boundary" for issue in result.issues)


def test_overlapping_grab_strips_are_allowed_when_neither_cavity_obstructs_access():
    left_tool = _rectangle_tool("left")
    right_tool = _rectangle_tool("right")
    left = ToolPlacement(
        tool_id="left",
        x_mm=20.0,
        y_mm=20.0,
        grab_side="right",
        grab_clearance_override_mm=10.0,
        is_placed=True,
    )
    right = ToolPlacement(
        tool_id="right",
        x_mm=50.0,
        y_mm=20.0,
        grab_side="left",
        grab_clearance_override_mm=10.0,
        is_placed=True,
    )
    layout = LayoutState(
        mode="foam",
        foam_width_mm=80.0,
        foam_height_mm=50.0,
        border_mm=4.0,
        spacing_mm=0.0,
        placements=[left, right],
    )
    project = Project(
        id="p",
        name="P",
        tools=[left_tool, right_tool],
        layout=layout,
    )

    result = validate_layout(project, layout)

    assert result.valid is True
    assert not any(issue.code == "overlap" for issue in result.issues)
