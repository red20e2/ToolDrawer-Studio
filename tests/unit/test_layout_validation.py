from __future__ import annotations

import importlib

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _validation():
    return importlib.import_module("tooldrawer_studio.layout.validation")


def _tool(tool_id: str, *, width: float = 20.0, height: float = 10.0, clearance: float = 0.0) -> ToolObject:
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


def _project_with_layout(*placements: ToolPlacement, tools: list[ToolObject] | None = None) -> Project:
    actual_tools = tools or [_tool(item.tool_id) for item in placements if item.tool_id.startswith("tool-")]
    return Project(
        id="project-1",
        name="P",
        tools=actual_tools,
        layout=LayoutState(
            mode="foam",
            foam_width_mm=100.0,
            foam_height_mm=80.0,
            border_mm=4.0,
            spacing_mm=4.0,
            placements=list(placements),
        ),
    )


def test_valid_separated_tools_have_no_issues():
    validation = _validation()
    project = _project_with_layout(
        ToolPlacement(tool_id="tool-a", x_mm=25.0, y_mm=30.0, is_placed=True),
        ToolPlacement(tool_id="tool-b", x_mm=65.0, y_mm=30.0, is_placed=True),
    )

    result = validation.validate_layout(project, project.layout)

    assert result.valid is True
    assert result.issues == ()


def test_boundary_violation_is_reported():
    validation = _validation()
    placement = ToolPlacement(tool_id="tool-a", x_mm=5.0, y_mm=5.0, is_placed=True)
    project = _project_with_layout(placement)

    result = validation.validate_layout(project, project.layout)

    assert result.valid is False
    assert any(issue.code == "boundary" and issue.tool_ids == ("tool-a",) for issue in result.issues)


def test_structural_spacing_overlap_is_reported():
    validation = _validation()
    project = _project_with_layout(
        ToolPlacement(tool_id="tool-a", x_mm=30.0, y_mm=30.0, is_placed=True),
        ToolPlacement(tool_id="tool-b", x_mm=50.0, y_mm=30.0, is_placed=True),
    )

    result = validation.validate_layout(project, project.layout)

    assert result.valid is False
    assert any(issue.code == "overlap" and issue.tool_ids == ("tool-a", "tool-b") for issue in result.issues)


def test_exact_minimum_spacing_touch_is_valid_not_overlap():
    validation = _validation()
    project = _project_with_layout(
        ToolPlacement(tool_id="tool-a", x_mm=30.0, y_mm=30.0, is_placed=True),
        ToolPlacement(tool_id="tool-b", x_mm=54.0, y_mm=30.0, is_placed=True),
    )

    result = validation.validate_layout(project, project.layout)

    assert not any(issue.code == "overlap" for issue in result.issues)


def test_grab_zone_conflict_is_reported_as_overlap():
    validation = _validation()
    project = _project_with_layout(
        ToolPlacement(
            tool_id="tool-a",
            x_mm=30.0,
            y_mm=30.0,
            is_placed=True,
            grab_side="right",
            grab_clearance_override_mm=15.0,
        ),
        ToolPlacement(tool_id="tool-b", x_mm=62.0, y_mm=30.0, is_placed=True),
    )

    result = validation.validate_layout(project, project.layout)

    assert any(issue.code == "overlap" and issue.tool_ids == ("tool-a", "tool-b") for issue in result.issues)


def test_locked_invalid_placement_is_reported_without_being_moved():
    validation = _validation()
    placement = ToolPlacement(
        tool_id="tool-a",
        x_mm=-50.0,
        y_mm=20.0,
        rotation_deg=30.0,
        locked=True,
        is_placed=True,
    )
    project = _project_with_layout(placement)

    result = validation.validate_layout(project, project.layout)

    assert result.valid is False
    assert any(issue.code == "boundary" for issue in result.issues)
    assert placement.x_mm == -50.0
    assert placement.y_mm == 20.0
    assert placement.rotation_deg == 30.0


def test_unplaced_tools_are_not_checked_for_collision():
    validation = _validation()
    project = _project_with_layout(
        ToolPlacement(tool_id="tool-a", x_mm=30.0, y_mm=30.0, is_placed=True),
        ToolPlacement(tool_id="tool-b", x_mm=30.0, y_mm=30.0, is_placed=False),
    )

    result = validation.validate_layout(project, project.layout)

    assert not any(issue.code == "overlap" for issue in result.issues)


def test_unknown_placement_tool_id_is_reported_deterministically():
    validation = _validation()
    project = _project_with_layout(
        ToolPlacement(tool_id="missing", x_mm=20.0, y_mm=20.0, is_placed=True),
        tools=[_tool("tool-a")],
    )

    result = validation.validate_layout(project, project.layout)

    assert result.valid is False
    assert result.issues[0].code == "missing_tool"
    assert result.issues[0].tool_ids == ("missing",)
