from pathlib import Path

import pytest

from tooldrawer_studio.export.service import export_organizer_package
from tooldrawer_studio.generation.builder import generate_organizer, placed_tool_depths
from tooldrawer_studio.release_fixture import build_release_fixture


def _assert_exports_exist(paths) -> None:
    for path in (paths.step, paths.stl, paths.dxf):
        assert path is not None
        assert Path(path).is_file()
        assert Path(path).stat().st_size > 0


def test_release_fixture_foam_covers_multi_depth_rotation_clearance_and_scoop(tmp_path):
    bundle = build_release_fixture("foam")
    project = bundle.project
    assert project.layout is not None
    assert project.layout.mode == "foam"
    assert project.layout.review_required is False
    assert len(project.tools) == 2
    assert sorted(depth for _tool, _placement, depth in placed_tool_depths(project)) == [6.0, 10.0]
    assert any(tool.clearance_mm > 0.0 for tool in project.tools)
    assert any(placement.rotation_deg != 0.0 for placement in project.layout.placements)
    assert any(placement.grab_side != "none" for placement in project.layout.placements)

    result = generate_organizer(project)
    assert result.body_height_mm == pytest.approx(12.0)
    assert len(result.model.solids().vals()) == 1
    assert result.model.val().isValid()
    _assert_exports_exist(export_organizer_package(result, project, tmp_path / "foam"))


def test_release_fixture_gridfinity_covers_full_release_features(tmp_path):
    bundle = build_release_fixture("gridfinity")
    project = bundle.project
    assert project.layout is not None
    assert project.layout.mode == "gridfinity"
    assert project.layout.grid_columns == 2
    assert project.layout.grid_rows == 2
    assert project.generation_settings.magnets_enabled is True
    assert project.generation_settings.screw_holes_enabled is True
    assert project.generation_settings.stacking_lip_enabled is True
    assert project.generation_settings.gridfinity_height_snap is True

    result = generate_organizer(project)
    assert result.body_height_mm == pytest.approx(14.0)
    assert len(result.model.solids().vals()) == 1
    assert result.model.val().isValid()
    _assert_exports_exist(export_organizer_package(result, project, tmp_path / "gridfinity"))
