from __future__ import annotations

import importlib

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _packer():
    return importlib.import_module("tooldrawer_studio.layout.packer")


def _tool(tool_id: str, width: float, height: float, *, clearance: float = 0.0) -> ToolObject:
    contour = [
        Point2D(0.0, 0.0),
        Point2D(width, 0.0),
        Point2D(width, height),
        Point2D(0.0, height),
    ]
    return ToolObject(
        id=tool_id,
        name=tool_id,
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=clearance,
    )


def test_rotation_candidates_follow_policy_exactly():
    packer = _packer()

    free = ToolPlacement(tool_id="free", rotation_policy="free")
    orthogonal = ToolPlacement(tool_id="ortho", rotation_policy="orthogonal")
    fixed = ToolPlacement(tool_id="fixed", rotation_policy="fixed", rotation_deg=37.5)

    assert packer.rotation_candidates(free) == tuple(float(value) for value in range(0, 360, 15))
    assert packer.rotation_candidates(orthogonal) == (0.0, 90.0, 180.0, 270.0)
    assert packer.rotation_candidates(fixed) == (37.5,)


def test_same_input_produces_identical_packing_result():
    packer = _packer()
    project = Project(
        id="p",
        name="P",
        tools=[_tool("large", 35.0, 20.0), _tool("small", 20.0, 10.0)],
        layout=LayoutState(
            mode="foam",
            foam_width_mm=100.0,
            foam_height_mm=70.0,
            border_mm=4.0,
            spacing_mm=3.0,
            placements=[
                ToolPlacement(tool_id="large", is_placed=False),
                ToolPlacement(tool_id="small", is_placed=False),
            ],
        ),
    )

    first = packer.pack_layout(project, project.layout)
    second = packer.pack_layout(project, project.layout)

    assert first == second
    assert first.validation.valid is True
    assert first.unplaced_tool_ids == ()


def test_locked_placement_is_preserved_exactly_when_repacking_unlocked():
    packer = _packer()
    locked = ToolPlacement(
        tool_id="locked",
        x_mm=25.25,
        y_mm=30.75,
        rotation_deg=30.0,
        locked=True,
        is_placed=True,
    )
    project = Project(
        id="p",
        name="P",
        tools=[_tool("locked", 20.0, 10.0), _tool("other", 20.0, 10.0)],
        layout=LayoutState(
            mode="foam",
            foam_width_mm=100.0,
            foam_height_mm=70.0,
            border_mm=4.0,
            spacing_mm=3.0,
            placements=[locked, ToolPlacement(tool_id="other", is_placed=False)],
        ),
    )

    result = packer.pack_layout(project, project.layout, repack_unlocked_only=True)
    saved = next(item for item in result.placements if item.tool_id == "locked")

    assert saved.x_mm == 25.25
    assert saved.y_mm == 30.75
    assert saved.rotation_deg == 30.0
    assert saved.locked is True
    assert saved.is_placed is True


def test_tool_can_span_nominal_gridfinity_cell_lines():
    packer = _packer()
    project = Project(
        id="p",
        name="P",
        tools=[_tool("ratchet", 70.0, 18.0)],
        layout=LayoutState(
            mode="gridfinity",
            grid_columns=3,
            grid_rows=1,
            grid_pitch_mm=42.0,
            border_mm=3.0,
            spacing_mm=3.0,
            placements=[ToolPlacement(tool_id="ratchet", rotation_policy="fixed", is_placed=False)],
        ),
    )

    result = packer.pack_layout(project, project.layout)
    ratchet = result.placements[0]

    assert ratchet.is_placed is True
    assert result.unplaced_tool_ids == ()
    assert result.validation.valid is True


def test_partial_fit_keeps_valid_placements_and_lists_unplaced_tools():
    packer = _packer()
    project = Project(
        id="p",
        name="P",
        tools=[_tool("fits", 20.0, 10.0), _tool("too-large", 200.0, 100.0)],
        layout=LayoutState(
            mode="foam",
            foam_width_mm=80.0,
            foam_height_mm=60.0,
            border_mm=4.0,
            spacing_mm=3.0,
            placements=[
                ToolPlacement(tool_id="fits", is_placed=False),
                ToolPlacement(tool_id="too-large", is_placed=False),
            ],
        ),
    )

    result = packer.pack_layout(project, project.layout)
    by_id = {item.tool_id: item for item in result.placements}

    assert by_id["fits"].is_placed is True
    assert by_id["too-large"].is_placed is False
    assert result.unplaced_tool_ids == ("too-large",)
    assert result.validation.valid is True


def test_restricted_large_tool_is_packed_before_flexible_small_tool():
    packer = _packer()
    restricted = ToolPlacement(tool_id="restricted", rotation_policy="fixed", is_placed=False)
    flexible = ToolPlacement(tool_id="flexible", rotation_policy="free", is_placed=False)
    project = Project(
        id="p",
        name="P",
        tools=[_tool("flexible", 10.0, 10.0), _tool("restricted", 45.0, 18.0)],
        layout=LayoutState(
            mode="foam",
            foam_width_mm=80.0,
            foam_height_mm=50.0,
            border_mm=3.0,
            spacing_mm=3.0,
            placements=[flexible, restricted],
        ),
    )

    ordered = packer.pack_order(project, project.layout)

    assert ordered[0].id == "restricted"
    assert ordered[1].id == "flexible"
