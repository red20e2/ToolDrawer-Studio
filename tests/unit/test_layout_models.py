from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.persistence.project_archive import ProjectBundle, load_project, save_project


def _layout_types():
    module = importlib.import_module("tooldrawer_studio.layout.models")
    return module.LayoutState, module.ToolPlacement


def test_gridfinity_dimensions_are_derived_from_rows_columns_and_pitch():
    LayoutState, _ = _layout_types()

    state = LayoutState(mode="gridfinity", grid_columns=6, grid_rows=5, grid_pitch_mm=42.0)

    assert state.width_mm == pytest.approx(252.0)
    assert state.height_mm == pytest.approx(210.0)


def test_tool_placement_normalizes_rotation_and_rejects_invalid_policy():
    _, ToolPlacement = _layout_types()

    placement = ToolPlacement(tool_id="tool-1", x_mm=10.0, y_mm=20.0, rotation_deg=450.0)
    assert placement.rotation_deg == pytest.approx(90.0)

    with pytest.raises(ValueError, match="rotation policy"):
        ToolPlacement(tool_id="tool-2", rotation_policy="diagonal-only")


def test_layout_rejects_duplicate_tool_placements():
    LayoutState, ToolPlacement = _layout_types()

    with pytest.raises(ValueError, match="Duplicate tool placement"):
        LayoutState(
            mode="foam",
            foam_width_mm=300.0,
            foam_height_mm=200.0,
            placements=[ToolPlacement(tool_id="tool-1"), ToolPlacement(tool_id="tool-1")],
        )


def test_v3_round_trip_preserves_nondefault_arrange_state(tmp_path: Path):
    LayoutState, ToolPlacement = _layout_types()
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=6,
        grid_rows=5,
        grid_pitch_mm=41.5,
        spacing_mm=3.5,
        border_mm=5.0,
        grab_clearance_mm=14.0,
        snap_enabled=True,
        snap_increment_mm=0.5,
        placements=[
            ToolPlacement(
                tool_id="tool-1",
                x_mm=35.25,
                y_mm=44.75,
                rotation_deg=30.0,
                locked=True,
                rotation_policy="free",
                grab_side="right",
                grab_clearance_override_mm=16.0,
                is_placed=True,
            ),
            ToolPlacement(
                tool_id="tool-2",
                x_mm=0.0,
                y_mm=0.0,
                rotation_deg=90.0,
                rotation_policy="orthogonal",
                grab_side="none",
                is_placed=False,
            ),
        ],
        unplaced_tool_ids=["tool-2"],
        review_required=True,
    )
    project = Project(
        id="project-layout",
        name="Layout round trip",
        default_layout_spacing_mm=2.5,
        default_layout_border_mm=6.0,
        default_grab_clearance_mm=15.0,
        default_snap_increment_mm=0.25,
        gridfinity_pitch_mm=41.5,
        layout=layout,
    )
    path = tmp_path / "layout.tds"

    save_project(ProjectBundle(project=project, image_bytes={}), path)
    reopened = load_project(path).project

    assert reopened.default_layout_spacing_mm == pytest.approx(2.5)
    assert reopened.default_layout_border_mm == pytest.approx(6.0)
    assert reopened.default_grab_clearance_mm == pytest.approx(15.0)
    assert reopened.default_snap_increment_mm == pytest.approx(0.25)
    assert reopened.gridfinity_pitch_mm == pytest.approx(41.5)
    assert reopened.layout is not None
    assert reopened.layout.mode == "gridfinity"
    assert reopened.layout.width_mm == pytest.approx(249.0)
    assert reopened.layout.height_mm == pytest.approx(207.5)
    assert reopened.layout.spacing_mm == pytest.approx(3.5)
    assert reopened.layout.snap_enabled is True
    assert reopened.layout.unplaced_tool_ids == ["tool-2"]
    assert reopened.layout.review_required is True
    assert reopened.layout.placements[0].tool_id == "tool-1"
    assert reopened.layout.placements[0].locked is True
    assert reopened.layout.placements[0].rotation_deg == pytest.approx(30.0)
    assert reopened.layout.placements[0].grab_side == "right"
    assert reopened.layout.placements[0].grab_clearance_override_mm == pytest.approx(16.0)
    assert reopened.layout.placements[1].rotation_policy == "orthogonal"
    assert reopened.layout.placements[1].is_placed is False
