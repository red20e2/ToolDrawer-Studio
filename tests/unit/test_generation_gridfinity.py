import pytest

from tooldrawer_studio.generation.gridfinity import (
    PROFILE,
    build_gridfinity_body,
    gridfinity_cell_centers,
    gridfinity_feature_cutters,
    magnet_centers,
    snap_gridfinity_height,
)
from tooldrawer_studio.generation.models import GenerationSettings
from tooldrawer_studio.layout.models import LayoutState


def _layout(columns: int = 2, rows: int = 3) -> LayoutState:
    return LayoutState(
        mode="gridfinity",
        grid_columns=columns,
        grid_rows=rows,
        grid_pitch_mm=42.0,
    )


def test_gridfinity_profile_constants_are_pinned():
    assert PROFILE.pitch_mm == 42.0
    assert PROFILE.top_footprint_mm == 41.5
    assert PROFILE.base_height_mm == 7.0
    assert PROFILE.base_profile_height_mm == 4.75
    assert PROFILE.base_profile == (
        (0.0, 0.0),
        (0.8, 0.8),
        (0.8, 2.6),
        (2.95, 4.75),
    )
    assert PROFILE.top_corner_radius_mm == 3.75
    assert PROFILE.bottom_corner_radius_mm == 0.8
    assert PROFILE.stacking_lip_profile == (
        (0.0, 0.0),
        (0.7, 0.7),
        (0.7, 2.5),
        (2.6, 4.4),
    )


def test_two_by_three_grid_has_exact_pitch_extent():
    layout = _layout(2, 3)
    assert layout.width_mm == pytest.approx(84.0)
    assert layout.height_mm == pytest.approx(126.0)
    assert gridfinity_cell_centers(layout) == (
        (21.0, 21.0),
        (63.0, 21.0),
        (21.0, 63.0),
        (63.0, 63.0),
        (21.0, 105.0),
        (63.0, 105.0),
    )


def test_each_cell_top_footprint_is_41_5():
    body = build_gridfinity_body(_layout(1, 1), 14.0, GenerationSettings())
    box = body.val().BoundingBox()
    assert box.xlen == pytest.approx(41.5, abs=1e-3)
    assert box.ylen == pytest.approx(41.5, abs=1e-3)


def test_multi_cell_body_is_one_valid_solid():
    body = build_gridfinity_body(_layout(2, 3), 21.0, GenerationSettings())
    assert len(body.solids().vals()) == 1
    assert body.val().isValid()
    box = body.val().BoundingBox()
    assert box.xlen == pytest.approx(83.5, abs=1e-3)
    assert box.ylen == pytest.approx(125.5, abs=1e-3)
    assert box.zlen == pytest.approx(21.0, abs=1e-3)


def test_base_engagement_profile_height_is_4_75():
    assert PROFILE.base_profile[-1][1] == pytest.approx(4.75)


def test_height_snap_never_rounds_down():
    assert snap_gridfinity_height(17.4) == pytest.approx(21.0)
    assert snap_gridfinity_height(21.0) == pytest.approx(21.0)
    assert snap_gridfinity_height(21.0001) == pytest.approx(28.0)


def test_gridfinity_body_rejects_wrong_pitch():
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=1,
        grid_rows=1,
        grid_pitch_mm=40.0,
    )
    with pytest.raises(ValueError, match="42.0 mm pitch"):
        build_gridfinity_body(layout, 14.0, GenerationSettings())


def test_gridfinity_body_requires_at_least_one_base_unit_height():
    with pytest.raises(ValueError, match="at least 7.000 mm"):
        build_gridfinity_body(_layout(1, 1), 6.9, GenerationSettings())


def test_default_magnet_holes_are_6_by_2_mm():
    features = gridfinity_feature_cutters(_layout(1, 1), GenerationSettings(), 21.0)
    first = features.magnet_cutters[0].val().BoundingBox()
    assert first.xlen == pytest.approx(6.0, abs=1e-3)
    assert first.ylen == pytest.approx(6.0, abs=1e-3)
    assert first.zlen == pytest.approx(2.0, abs=1e-3)


def test_shared_multi_cell_hole_coordinates_are_deduplicated():
    centers = magnet_centers(_layout(3, 2))
    assert len(centers) == len(set(centers))
    assert len(centers) == 24


def test_screw_holes_are_independent_of_magnets():
    settings = GenerationSettings(magnets_enabled=False, screw_holes_enabled=True)
    features = gridfinity_feature_cutters(_layout(1, 1), settings, 21.0)
    assert not features.magnet_cutters
    assert features.screw_cutters
    screw = features.screw_cutters[0].val().BoundingBox()
    assert screw.xlen == pytest.approx(3.2, abs=1e-3)


def test_stacking_lip_is_present_by_default():
    features = gridfinity_feature_cutters(_layout(2, 1), GenerationSettings(), 21.0)
    assert features.stacking_lip is not None
    box = features.stacking_lip.val().BoundingBox()
    assert box.zmin == pytest.approx(21.0, abs=1e-3)
    assert box.zmax == pytest.approx(25.4, abs=1e-3)


def test_disabled_stacking_lip_returns_none():
    settings = GenerationSettings(stacking_lip_enabled=False)
    features = gridfinity_feature_cutters(_layout(1, 1), settings, 21.0)
    assert features.stacking_lip is None
