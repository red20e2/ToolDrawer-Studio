import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.ui.arrange_panel import ArrangePanel
from tooldrawer_studio.ui.arrangement_view import ArrangementView
from tooldrawer_studio.ui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _add_tool(window: MainWindow, tool_id: str = "tool-1") -> ToolObject:
    contour = [Point2D(0, 0), Point2D(25, 0), Point2D(25, 12), Point2D(0, 12)]
    tool = ToolObject(
        id=tool_id,
        name=tool_id,
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.6,
    )
    window.controller.project.tools.append(tool)
    window.controller.select_tool(tool.id)
    window._populate_tools()
    return tool


def test_main_window_has_arrange_stage_between_measure_and_pocket_settings():
    app = _app()
    window = MainWindow()

    assert window.tabs.count() == 6
    assert [window.tabs.tabText(index) for index in range(6)] == [
        "1. Import & Calibrate",
        "2. Detect & Edit",
        "3. Measure",
        "4. Arrange",
        "5. Pocket Settings",
        "6. Save & Export",
    ]
    assert isinstance(window.arrange_panel, ArrangePanel)
    assert isinstance(window.arrangement_view, ArrangementView)
    window.close()
    assert app is not None


def test_layout_request_auto_arrange_and_panel_status_are_wired_to_controller():
    window = MainWindow()
    _add_tool(window)

    window._arrange_layout_requested(("gridfinity", 3, 2, 42.0))
    window._arrange_auto()

    layout = window.controller.project.layout
    assert layout is not None
    assert layout.mode == "gridfinity"
    assert layout.width_mm == 126.0
    assert layout.height_mm == 84.0
    assert layout.placement_for("tool-1").is_placed is True
    assert "1 / 1" in window.arrange_panel.status_label.text()
    assert window.tabs.isTabEnabled(3) is True
    window.close()


def test_canvas_committed_placement_updates_controller_without_resetting_undo_stack():
    window = MainWindow()
    _add_tool(window)
    window._arrange_layout_requested(("foam", 150.0, 100.0))
    window._arrange_auto()
    before = window.controller.project.layout.placement_for("tool-1")
    before_x = before.x_mm
    before_y = before.y_mm

    window.arrangement_view.commit_translation(["tool-1"], 5.0, 7.0)

    saved = window.controller.project.layout.placement_for("tool-1")
    assert saved.x_mm == before_x + 5.0
    assert saved.y_mm == before_y + 7.0
    assert window.arrangement_view.undo_stack.count() == 1

    window.arrangement_view.undo_stack.undo()
    restored = window.controller.project.layout.placement_for("tool-1")
    assert restored.x_mm == before_x
    assert restored.y_mm == before_y
    window.close()


def test_selected_tool_layout_options_are_wired_from_panel():
    window = MainWindow()
    _add_tool(window)
    window._arrange_layout_requested(("foam", 150.0, 100.0))
    window._arrange_auto()

    window._arrange_rotation_policy("orthogonal")
    window._arrange_grab_side("right")
    window._arrange_lock(True)

    placement = window.controller.project.layout.placement_for("tool-1")
    assert placement.rotation_policy == "orthogonal"
    assert placement.grab_side == "right"
    assert placement.locked is True
    window.close()


def test_single_canvas_selection_becomes_active_tool_for_arrange_controls():
    window = MainWindow()
    first = _add_tool(window, "tool-1")
    second = _add_tool(window, "tool-2")
    window.controller.select_tool(first.id)
    window._arrange_layout_requested(("foam", 180.0, 120.0))
    window._arrange_auto()

    window.arrangement_view.set_selected_tool_ids({second.id})

    assert window.controller.selected_tool().id == second.id
    assert window.arrange_panel.rotation_value.value() == window.controller.project.layout.placement_for(second.id).rotation_deg
    window.close()
