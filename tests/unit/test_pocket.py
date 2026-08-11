import pytest

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.geometry.pocket import PocketSpec, build_pocket_insert


def _tool() -> ToolObject:
    contour = [Point2D(10, 10), Point2D(30, 10), Point2D(30, 20), Point2D(10, 20)]
    return ToolObject(id="tool-1", name="Block", source_capture_id="capture-1", base_contour_mm=list(contour), contour_mm=list(contour), clearance_mm=0.5, depth_mm=4.0)


def test_build_pocket_insert_has_expected_outer_dimensions():
    model = build_pocket_insert(_tool(), PocketSpec(60.0, 40.0, 8.0, 4.0))
    box = model.val().BoundingBox()
    assert abs(box.xlen - 60.0) < 1e-6
    assert abs(box.ylen - 40.0) < 1e-6
    assert abs(box.zlen - 8.0) < 1e-6


def test_rejects_pocket_through_bottom():
    with pytest.raises(ValueError, match="shallower than base thickness"):
        build_pocket_insert(_tool(), PocketSpec(60.0, 40.0, 8.0, 8.0))


def test_rejects_cavity_that_exceeds_base_boundary():
    tool = _tool()
    tool.contour_mm = [Point2D(0.2, 10), Point2D(30, 10), Point2D(30, 20), Point2D(0.2, 20)]
    with pytest.raises(ValueError, match="Tool cavity exceeds base boundary"):
        build_pocket_insert(tool, PocketSpec(60.0, 40.0, 8.0, 4.0))
