import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.generation.models import GenerationIssue, GenerationValidationResult
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.ui.generate_panel import GeneratePanel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _project(mode: str = "foam") -> Project:
    contour = [
        Point2D(-10.0, -5.0),
        Point2D(10.0, -5.0),
        Point2D(10.0, 5.0),
        Point2D(-10.0, 5.0),
    ]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        pocket_depth_override_mm=6.0,
    )
    if mode == "gridfinity":
        layout = LayoutState(
            mode="gridfinity",
            grid_columns=2,
            grid_rows=2,
            placements=[ToolPlacement(tool_id=tool.id, x_mm=42.0, y_mm=42.0, is_placed=True)],
            review_required=False,
        )
    else:
        layout = LayoutState(
            mode="foam",
            foam_width_mm=100.0,
            foam_height_mm=80.0,
            placements=[ToolPlacement(tool_id=tool.id, x_mm=50.0, y_mm=40.0, is_placed=True)],
            review_required=False,
        )
    return Project(id="p", name="Drawer", tools=[tool], layout=layout)


def test_panel_exposes_manufacturing_controls_and_generate_action():
    app = _app()
    panel = GeneratePanel()
    assert panel.height_mode.currentData() == "auto"
    assert panel.minimum_floor.value() == 2.0
    assert panel.minimum_wall.value() == 2.0
    assert panel.scoops_enabled.isChecked()
    assert panel.generate_button.text() == "Generate Organizer"
    panel.close()
    assert app is not None


def test_gridfinity_controls_only_show_for_gridfinity_project():
    panel = GeneratePanel()
    foam = _project("foam")
    panel.set_project(foam)
    assert panel.magnets_enabled.isVisibleTo(panel) is False

    grid = _project("gridfinity")
    panel.set_project(grid)
    assert panel.magnets_enabled.isVisibleTo(panel) is True
    assert panel.magnet_diameter.value() == 6.0
    assert panel.magnet_depth.value() == 2.0
    assert panel.stacking_lip.isChecked() is True
    panel.close()


def test_set_project_does_not_emit_settings_changed_during_nested_widget_refresh():
    panel = GeneratePanel()
    captured: list[dict[str, object]] = []
    panel.settingsChanged.connect(lambda payload: captured.append(payload))

    panel.set_project(_project())

    assert captured == []
    panel.close()


def test_settings_emit_presentation_neutral_dict():
    panel = GeneratePanel()
    panel.set_project(_project())
    captured: list[dict[str, object]] = []
    panel.settingsChanged.connect(lambda payload: captured.append(payload))
    panel.minimum_floor.setValue(2.5)
    assert captured
    assert captured[-1] == {"minimum_floor_mm": 2.5}
    panel.close()


def test_per_tool_scoop_mode_emits_tool_id_and_mode():
    panel = GeneratePanel()
    panel.set_project(_project())
    captured: list[tuple[str, str]] = []
    panel.toolScoopModeChanged.connect(lambda tool_id, mode: captured.append((tool_id, mode)))
    panel.tool_scoop_mode.setCurrentIndex(panel.tool_scoop_mode.findData("off"))
    assert captured[-1] == ("tool-1", "off")
    panel.close()


def test_validation_and_currentness_are_actionable():
    panel = GeneratePanel()
    project = _project()
    project.generation_state.last_generated_fingerprint = "old-fingerprint"
    project.generation_state.review_required = True
    panel.set_project(project)
    panel.set_validation(
        GenerationValidationResult(
            False,
            (
                GenerationIssue(
                    "minimum_floor",
                    "Ratchet needs 2.0 mm more floor",
                    "error",
                    ("tool-1",),
                ),
            ),
        )
    )
    panel.set_currentness(False)
    assert "ratchet" in panel.validation_label.text().lower()
    assert "stale" in panel.currentness_label.text().lower()
    panel.close()
