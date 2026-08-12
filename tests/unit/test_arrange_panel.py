import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.ui.arrange_panel import ArrangePanel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_panel_owns_arrange_controls_and_distinguishes_spacing_from_pocket_clearance():
    app = _app()
    panel = ArrangePanel()

    assert panel.mode_combo is not None
    assert panel.foam_width is not None
    assert panel.foam_height is not None
    assert panel.grid_columns is not None
    assert panel.grid_rows is not None
    assert panel.grid_pitch is not None
    assert panel.auto_button.text() == "Auto Arrange"
    assert panel.repack_button.text() == "Re-pack Unlocked"
    assert panel.rotation_policy is not None
    assert panel.grab_side is not None
    assert panel.locked is not None
    assert "pocket clearance" in panel.spacing_note.text().lower()
    panel.close()
    assert app is not None


def test_gridfinity_live_dimensions_show_columns_rows_times_pitch():
    panel = ArrangePanel()
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("gridfinity"))
    panel.grid_columns.setValue(6)
    panel.grid_rows.setValue(5)
    panel.grid_pitch.setValue(42.0)

    assert "252.000" in panel.grid_dimensions.text()
    assert "210.000" in panel.grid_dimensions.text()
    assert panel.grid_columns.isVisibleTo(panel) is True
    panel.close()


def test_set_state_renders_layout_defaults_selection_and_validation_status():
    panel = ArrangePanel()
    project = Project(id="p", name="P")
    placement = ToolPlacement(
        tool_id="tool-1",
        x_mm=30.0,
        y_mm=40.0,
        rotation_deg=30.0,
        locked=True,
        rotation_policy="free",
        grab_side="right",
        is_placed=True,
    )
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=6,
        grid_rows=5,
        spacing_mm=3.5,
        border_mm=5.0,
        grab_clearance_mm=14.0,
        snap_enabled=True,
        snap_increment_mm=0.5,
        placements=[placement],
        unplaced_tool_ids=["tool-2"],
        review_required=True,
    )

    panel.set_state(
        project,
        layout,
        placement,
        placed_count=1,
        total_count=2,
        validation_messages=["Tool exceeds boundary"],
    )

    assert panel.spacing.value() == 3.5
    assert panel.border.value() == 5.0
    assert panel.default_grab.value() == 14.0
    assert panel.snap_enabled.isChecked() is True
    assert panel.snap_increment.value() == 0.5
    assert panel.locked.isChecked() is True
    assert panel.rotation_policy.currentData() == "free"
    assert panel.grab_side.currentData() == "right"
    assert "1 / 2" in panel.status_label.text()
    assert "unplaced" in panel.status_label.text().lower()
    assert "review" in panel.status_label.text().lower()
    assert "boundary" in panel.validation_label.text().lower()
    panel.close()


def test_unplaced_tools_are_listed_by_name_for_actionable_partial_fit():
    panel = ArrangePanel()
    contour = [Point2D(0, 0), Point2D(20, 0), Point2D(20, 10), Point2D(0, 10)]
    placed_tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )
    unplaced_tool = ToolObject(
        id="tool-2",
        name="Long Breaker Bar",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )
    project = Project(id="p", name="P", tools=[placed_tool, unplaced_tool])
    placement = ToolPlacement(tool_id="tool-1", x_mm=30.0, y_mm=30.0, is_placed=True)
    layout = LayoutState(
        mode="foam",
        foam_width_mm=100.0,
        foam_height_mm=80.0,
        placements=[placement, ToolPlacement(tool_id="tool-2")],
        unplaced_tool_ids=["tool-2"],
    )

    panel.set_state(
        project,
        layout,
        placement,
        placed_count=1,
        total_count=2,
    )

    assert panel.unplaced_list.count() == 1
    assert panel.unplaced_list.item(0).text() == "Long Breaker Bar"
    panel.close()


def test_core_actions_emit_presentation_neutral_values():
    panel = ArrangePanel()
    captured: dict[str, object] = {}
    panel.layoutRequested.connect(lambda payload: captured.__setitem__("layout", payload))
    panel.defaultsChanged.connect(lambda payload: captured.__setitem__("defaults", payload))
    panel.autoArrangeRequested.connect(lambda: captured.__setitem__("auto", True))
    panel.repackRequested.connect(lambda: captured.__setitem__("repack", True))

    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("foam"))
    panel.foam_width.setValue(300.0)
    panel.foam_height.setValue(200.0)
    panel.apply_layout_button.click()
    panel.spacing.setValue(4.0)
    panel.auto_button.click()
    panel.repack_button.click()

    assert captured["layout"] == ("foam", 300.0, 200.0)
    assert captured["defaults"][0] == "spacing_mm"
    assert captured["defaults"][1] == 4.0
    assert captured["auto"] is True
    assert captured["repack"] is True
    panel.close()
