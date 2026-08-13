import pytest

from tooldrawer_studio.generation.foam import build_foam_body
from tooldrawer_studio.layout.models import LayoutState


def test_foam_body_matches_exact_arrange_dimensions():
    layout = LayoutState(mode="foam", foam_width_mm=123.4, foam_height_mm=87.6)
    body = build_foam_body(layout, body_height_mm=18.25)
    box = body.val().BoundingBox()
    assert box.xmin == pytest.approx(0.0)
    assert box.ymin == pytest.approx(0.0)
    assert box.zmin == pytest.approx(0.0)
    assert box.xlen == pytest.approx(123.4)
    assert box.ylen == pytest.approx(87.6)
    assert box.zlen == pytest.approx(18.25)


def test_foam_body_rejects_gridfinity_layout():
    layout = LayoutState(mode="gridfinity", grid_columns=2, grid_rows=2)
    with pytest.raises(ValueError, match="foam layout mode"):
        build_foam_body(layout, 14.0)


def test_foam_body_rejects_nonpositive_height():
    layout = LayoutState(mode="foam", foam_width_mm=100.0, foam_height_mm=80.0)
    with pytest.raises(ValueError, match="body_height_mm"):
        build_foam_body(layout, 0.0)
