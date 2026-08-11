import pytest

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.geometry.contour import (
    polygon_area_mm2,
    replace_tool_contour,
    reset_tool_contour,
    validate_contour,
)


def _tool() -> ToolObject:
    raw = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 5), Point2D(0, 5)]
    return ToolObject(
        id="tool-1",
        name="Wrench",
        source_capture_id="capture-1",
        base_contour_mm=list(raw),
        contour_mm=list(raw),
    )


def test_replace_tool_contour_preserves_base_trace_and_metadata():
    tool = _tool()
    edited = [Point2D(0, 0), Point2D(12, 0), Point2D(12, 5), Point2D(0, 5)]
    result = replace_tool_contour(tool, edited)
    assert result.name == "Wrench"
    assert result.contour_mm[1].x_mm == 12
    assert result.base_contour_mm[1].x_mm == 10
    assert tool.contour_mm[1].x_mm == 10


def test_reset_tool_contour_restores_independent_base_copy():
    edited = replace_tool_contour(
        _tool(), [Point2D(0, 0), Point2D(12, 0), Point2D(12, 5), Point2D(0, 5)]
    )
    reset = reset_tool_contour(edited)
    assert reset.contour_mm == reset.base_contour_mm
    assert reset.contour_mm is not reset.base_contour_mm


def test_validate_contour_rejects_self_intersection():
    bow_tie = [Point2D(0, 0), Point2D(10, 10), Point2D(0, 10), Point2D(10, 0)]
    with pytest.raises(ValueError, match="self-intersect"):
        validate_contour(bow_tie)


def test_validate_contour_rejects_too_few_unique_points_and_zero_area():
    with pytest.raises(ValueError, match="three unique"):
        validate_contour([Point2D(0, 0), Point2D(1, 0), Point2D(1, 0)])
    with pytest.raises(ValueError, match="area"):
        validate_contour([Point2D(0, 0), Point2D(1, 0), Point2D(2, 0)])


def test_polygon_area_returns_absolute_square_millimetres():
    points = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 5), Point2D(0, 5)]
    assert polygon_area_mm2(points) == 50.0
    assert polygon_area_mm2(list(reversed(points))) == 50.0
