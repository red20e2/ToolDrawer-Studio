from __future__ import annotations

import importlib

import pytest

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _geometry():
    return importlib.import_module("tooldrawer_studio.layout.geometry")


def _rectangle_tool(*, width: float = 20.0, height: float = 10.0, clearance: float = 1.0) -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(width, 0.0),
        Point2D(width, height),
        Point2D(0.0, height),
    ]
    return ToolObject(
        id="tool-1",
        name="Rectangle",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=clearance,
    )


def test_cavity_footprint_includes_manufacturing_clearance():
    geometry = _geometry()
    polygon = geometry.tool_cavity_polygon(_rectangle_tool(clearance=1.0))

    minx, miny, maxx, maxy = polygon.bounds
    assert maxx - minx == pytest.approx(22.0)
    assert maxy - miny == pytest.approx(12.0)


def test_oriented_cavity_rotates_about_stable_local_anchor():
    geometry = _geometry()
    tool = _rectangle_tool(clearance=1.0)
    placement = ToolPlacement(
        tool_id=tool.id,
        x_mm=50.0,
        y_mm=60.0,
        rotation_deg=90.0,
        is_placed=True,
    )

    polygon = geometry.oriented_cavity_polygon(tool, placement)
    minx, miny, maxx, maxy = polygon.bounds

    assert maxx - minx == pytest.approx(12.0)
    assert maxy - miny == pytest.approx(22.0)
    assert polygon.centroid.x == pytest.approx(50.0)
    assert polygon.centroid.y == pytest.approx(60.0)


def test_structural_spacing_is_separate_and_applied_after_cavity_clearance():
    geometry = _geometry()
    tool = _rectangle_tool(clearance=1.0)
    placement = ToolPlacement(tool_id=tool.id, x_mm=50.0, y_mm=50.0, is_placed=True)

    cavity = geometry.oriented_cavity_polygon(tool, placement)
    exclusion = geometry.spacing_exclusion_polygon(tool, placement, spacing_mm=4.0)

    cavity_width = cavity.bounds[2] - cavity.bounds[0]
    exclusion_width = exclusion.bounds[2] - exclusion.bounds[0]
    assert cavity_width == pytest.approx(22.0)
    assert exclusion_width == pytest.approx(26.0)


def test_right_grab_zone_extends_only_requested_side_beyond_normal_spacing():
    geometry = _geometry()
    tool = _rectangle_tool(clearance=0.5)
    placement = ToolPlacement(
        tool_id=tool.id,
        x_mm=50.0,
        y_mm=50.0,
        grab_side="right",
        grab_clearance_override_mm=12.0,
        is_placed=True,
    )
    normal = geometry.spacing_exclusion_polygon(tool, placement, spacing_mm=3.0)
    with_grab = geometry.candidate_exclusion_geometry(
        tool,
        placement,
        spacing_mm=3.0,
        default_grab_clearance_mm=8.0,
    )

    assert with_grab.bounds[0] == pytest.approx(normal.bounds[0])
    assert with_grab.bounds[1] == pytest.approx(normal.bounds[1])
    assert with_grab.bounds[3] == pytest.approx(normal.bounds[3])
    assert with_grab.bounds[2] == pytest.approx(normal.bounds[2] + 12.0)


def test_usable_boundary_applies_border_margin_in_real_millimetres():
    geometry = _geometry()
    layout = LayoutState(
        mode="foam",
        foam_width_mm=300.0,
        foam_height_mm=200.0,
        border_mm=4.0,
    )

    boundary = geometry.usable_boundary_polygon(layout)
    assert boundary.bounds == pytest.approx((4.0, 4.0, 296.0, 196.0))


def test_invalid_tool_contour_is_rejected_instead_of_inventing_geometry():
    geometry = _geometry()
    tool = ToolObject(
        id="tool-bad",
        name="Bad",
        source_capture_id="capture-1",
        base_contour_mm=[Point2D(0, 0), Point2D(1, 0)],
        contour_mm=[Point2D(0, 0), Point2D(1, 0)],
    )

    with pytest.raises(ValueError, match="valid polygon"):
        geometry.tool_cavity_polygon(tool)
