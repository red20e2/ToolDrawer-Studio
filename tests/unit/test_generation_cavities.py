import pytest

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.generation.cavities import build_cavity_cutter
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import ToolPlacement


def _rectangle_tool(clearance_mm: float = 1.0) -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(20.0, 0.0),
        Point2D(20.0, 10.0),
        Point2D(0.0, 10.0),
    ]
    return ToolObject(
        id="tool-1",
        name="Socket",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=clearance_mm,
        pocket_depth_override_mm=5.0,
    )


def _bounds_xy(cutter) -> tuple[float, float, float, float]:
    box = cutter.val().BoundingBox()
    return box.xmin, box.ymin, box.xmax, box.ymax


def test_cavity_uses_arrange_transform():
    tool = _rectangle_tool()
    placement = ToolPlacement(tool_id=tool.id, x_mm=30.0, y_mm=40.0, is_placed=True)
    cutter = build_cavity_cutter(tool, placement, depth_mm=5.0, body_height_mm=12.0)
    expected = oriented_cavity_polygon(tool, placement).bounds
    box = cutter.val().BoundingBox()

    assert _bounds_xy(cutter) == pytest.approx(expected, abs=1e-3)
    assert box.zmin == pytest.approx(7.0)
    assert box.zmax == pytest.approx(12.0)


def test_rotated_cavity_uses_same_oriented_polygon_as_arrange():
    tool = _rectangle_tool()
    placement = ToolPlacement(
        tool_id=tool.id,
        x_mm=30.0,
        y_mm=40.0,
        rotation_deg=90.0,
        is_placed=True,
    )
    cutter = build_cavity_cutter(tool, placement, 4.0, 10.0)
    assert _bounds_xy(cutter) == pytest.approx(
        oriented_cavity_polygon(tool, placement).bounds,
        abs=1e-3,
    )


def test_two_tools_can_have_distinct_cavity_depths():
    tool = _rectangle_tool()
    placement = ToolPlacement(tool_id=tool.id, x_mm=30.0, y_mm=40.0, is_placed=True)
    shallow = build_cavity_cutter(tool, placement, 3.0, 12.0).val().BoundingBox()
    deep = build_cavity_cutter(tool, placement, 7.0, 12.0).val().BoundingBox()
    assert shallow.zmin == pytest.approx(9.0)
    assert deep.zmin == pytest.approx(5.0)
    assert shallow.zmax == pytest.approx(deep.zmax)


def test_manufacturing_clearance_is_present_once_not_twice():
    tool = _rectangle_tool(clearance_mm=1.0)
    placement = ToolPlacement(tool_id=tool.id, x_mm=30.0, y_mm=40.0, is_placed=True)
    box = build_cavity_cutter(tool, placement, 5.0, 12.0).val().BoundingBox()
    assert box.xlen == pytest.approx(22.0, abs=1e-2)
    assert box.ylen == pytest.approx(12.0, abs=1e-2)


def test_cavity_rejects_nonpositive_depth():
    tool = _rectangle_tool()
    placement = ToolPlacement(tool_id=tool.id, is_placed=True)
    with pytest.raises(ValueError, match="depth_mm"):
        build_cavity_cutter(tool, placement, 0.0, 12.0)
