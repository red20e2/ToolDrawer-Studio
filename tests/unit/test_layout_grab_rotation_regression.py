from __future__ import annotations

import pytest

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.layout.geometry import (
    candidate_exclusion_geometry,
    spacing_exclusion_polygon,
)
from tooldrawer_studio.layout.models import ToolPlacement


def _rectangle_tool() -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(20.0, 0.0),
        Point2D(20.0, 10.0),
        Point2D(0.0, 10.0),
    ]
    return ToolObject(
        id="tool-1",
        name="Rectangle",
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
