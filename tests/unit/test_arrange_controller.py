from __future__ import annotations

from pathlib import Path

import pytest

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _tool(tool_id: str, width: float = 20.0, height: float = 10.0) -> ToolObject:
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
        clearance_mm=0.5,
    )


def _controller() -> WorkflowController:
    controller = WorkflowController()
    controller.project.tools = [_tool("tool-a", 30.0, 15.0), _tool("tool-b", 20.0, 10.0)]
    return controller


def test_configure_gridfinity_layout_uses_project_defaults_and_creates_unplaced_entries():
    controller = _controller()

    layout = controller.configure_gridfinity_layout(6, 5)

    assert layout.mode == "gridfinity"
    assert layout.width_mm == pytest.approx(252.0)
    assert layout.height_mm == pytest.approx(210.0)
    assert layout.spacing_mm == pytest.approx(3.0)
    assert layout.border_mm == pytest.approx(4.0)
    assert [item.tool_id for item in layout.placements] == ["tool-a", "tool-b"]
    assert all(item.is_placed is False for item in layout.placements)


def test_auto_arrange_applies_valid_result_to_project_layout():
    controller = _controller()
    controller.configure_foam_layout(120.0, 80.0)

    result = controller.auto_arrange()

    assert result.validation.valid is True
    assert controller.project.layout is not None
    assert controller.project.layout.review_required is False
    assert all(item.is_placed for item in controller.project.layout.placements)
    assert controller.project.layout.unplaced_tool_ids == []


def test_repack_unlocked_preserves_locked_tool_exactly():
    controller = _controller()
    controller.configure_foam_layout(120.0, 80.0)
    controller.move_tool("tool-a", 30.25, 35.75)
    controller.rotate_tool("tool-a", 30.0)
    controller.set_tool_locked("tool-a", True)

    result = controller.repack_unlocked()
    saved = next(item for item in result.placements if item.tool_id == "tool-a")

    assert saved.x_mm == pytest.approx(30.25)
    assert saved.y_mm == pytest.approx(35.75)
    assert saved.rotation_deg == pytest.approx(30.0)
    assert saved.locked is True


def test_rotation_policy_is_enforced_by_controller():
    controller = _controller()
    controller.configure_foam_layout(120.0, 80.0)
    controller.set_tool_layout_options("tool-a", rotation_policy="orthogonal")

    rotated = controller.rotate_tool("tool-a", 47.0)
    assert rotated.rotation_deg == pytest.approx(90.0)

    controller.set_tool_layout_options("tool-a", rotation_policy="fixed")
    with pytest.raises(ValueError, match="fixed"):
        controller.rotate_tool("tool-a", 180.0)


def test_layout_setting_and_tool_geometry_changes_mark_review_without_moving_tools():
    controller = _controller()
    controller.configure_foam_layout(120.0, 80.0)
    controller.move_tool("tool-a", 31.0, 32.0)
    controller.auto_arrange()
    placement = controller.project.layout.placement_for("tool-a")
    before = (placement.x_mm, placement.y_mm, placement.rotation_deg)

    controller.set_layout_defaults(spacing_mm=5.0)
    placement = controller.project.layout.placement_for("tool-a")
    assert controller.project.layout.review_required is True
    assert (placement.x_mm, placement.y_mm, placement.rotation_deg) == before

    controller.project.layout.review_required = False
    controller.update_tool_settings("tool-a", clearance_mm=0.8)
    assert controller.project.layout.review_required is True
    placement = controller.project.layout.placement_for("tool-a")
    assert (placement.x_mm, placement.y_mm, placement.rotation_deg) == before


def test_save_reopen_restores_arrangement_without_repacking(tmp_path: Path):
    controller = _controller()
    controller.configure_foam_layout(120.0, 80.0)
    controller.move_tool("tool-a", 33.25, 28.75)
    controller.rotate_tool("tool-a", 15.0)
    controller.set_tool_locked("tool-a", True)
    controller.project.layout.review_required = True
    path = tmp_path / "arranged.tds"

    controller.save(path)
    reopened = WorkflowController.open(path)
    layout = reopened.project.layout
    saved = layout.placement_for("tool-a")

    assert saved.x_mm == pytest.approx(33.25)
    assert saved.y_mm == pytest.approx(28.75)
    assert saved.rotation_deg == pytest.approx(15.0)
    assert saved.locked is True
    assert layout.review_required is True


def test_align_and_distribute_operate_on_real_placed_tools():
    controller = WorkflowController()
    controller.project.tools = [_tool("a"), _tool("b"), _tool("c")]
    controller.configure_foam_layout(200.0, 100.0)
    controller.move_tool("a", 30.0, 30.0)
    controller.move_tool("b", 80.0, 40.0)
    controller.move_tool("c", 150.0, 50.0)

    controller.align_tools(["a", "b", "c"], "center_y")
    ys = [controller.project.layout.placement_for(tool_id).y_mm for tool_id in ("a", "b", "c")]
    assert ys[0] == pytest.approx(ys[1]) == pytest.approx(ys[2])

    controller.move_tool("a", 30.0, ys[0])
    controller.move_tool("b", 60.0, ys[0])
    controller.move_tool("c", 150.0, ys[0])
    controller.distribute_tools(["a", "b", "c"], "horizontal")
    xs = [controller.project.layout.placement_for(tool_id).x_mm for tool_id in ("a", "b", "c")]
    assert xs[1] - xs[0] == pytest.approx(xs[2] - xs[1])
