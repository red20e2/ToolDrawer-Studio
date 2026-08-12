import pytest

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.measurement.depth import (
    effective_bottom_clearance_mm,
    effective_exposed_height_mm,
    final_pocket_depth_mm,
    suggested_pocket_depth_mm,
)


def _fixture() -> tuple[Project, ToolObject]:
    contour = [
        Point2D(0, 0),
        Point2D(10, 0),
        Point2D(10, 5),
        Point2D(0, 5),
    ]
    tool = ToolObject("tool", "Tool", "capture", contour, list(contour))
    project = Project("project", "P", tools=[tool])
    return project, tool


def test_project_defaults_produce_approved_depth_formula():
    project, tool = _fixture()
    tool.accepted_thickness_mm = 18.0
    tool.thickness_accepted = True

    assert suggested_pocket_depth_mm(project, tool) == pytest.approx(14.8)


def test_tool_overrides_replace_project_defaults_independently():
    project, tool = _fixture()
    tool.accepted_thickness_mm = 18.0
    tool.thickness_accepted = True
    tool.exposed_height_override_mm = 3.0
    tool.bottom_clearance_override_mm = 1.2

    assert effective_exposed_height_mm(project, tool) == 3.0
    assert effective_bottom_clearance_mm(project, tool) == 1.2
    assert suggested_pocket_depth_mm(project, tool) == pytest.approx(16.2)


def test_unaccepted_thickness_cannot_drive_pocket_suggestion():
    project, tool = _fixture()
    tool.accepted_thickness_mm = 18.0
    tool.thickness_accepted = False

    assert suggested_pocket_depth_mm(project, tool) is None


def test_explicit_final_pocket_override_has_precedence():
    project, tool = _fixture()
    tool.accepted_thickness_mm = 18.0
    tool.thickness_accepted = True
    tool.pocket_depth_override_mm = 9.25

    assert suggested_pocket_depth_mm(project, tool) == pytest.approx(14.8)
    assert final_pocket_depth_mm(project, tool) == pytest.approx(9.25)


def test_invalid_formula_never_returns_negative_depth():
    project, tool = _fixture()
    tool.accepted_thickness_mm = 3.0
    tool.thickness_accepted = True

    with pytest.raises(ValueError, match="positive pocket depth"):
        suggested_pocket_depth_mm(project, tool)
