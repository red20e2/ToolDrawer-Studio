import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.ui.generate_panel import GeneratePanel
from tooldrawer_studio.ui.main_window import MainWindow
from tooldrawer_studio.ui.model_preview import ModelPreview


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _ready_project() -> Project:
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
        clearance_mm=0.0,
        pocket_depth_override_mm=6.0,
    )
    layout = LayoutState(
        mode="foam",
        foam_width_mm=80.0,
        foam_height_mm=50.0,
        border_mm=4.0,
        placements=[
            ToolPlacement(tool_id=tool.id, x_mm=40.0, y_mm=25.0, is_placed=True)
        ],
        review_required=False,
    )
    return Project(id="project-1", name="Drawer", tools=[tool], layout=layout)


def test_main_window_replaces_pocket_settings_with_generate_stage():
    app = _app()
    window = MainWindow()
    assert window.tabs.count() == 6
    assert window.tabs.tabText(4) == "5. Generate"
    assert window.tabs.tabText(5) == "6. Save & Export"
    assert isinstance(window.generate_panel, GeneratePanel)
    assert isinstance(window.model_preview, ModelPreview)
    window.close()
    assert app is not None


def test_save_export_stage_has_individual_and_all_manufacturing_actions():
    window = MainWindow()
    assert window.export_step_button.text() == "Export STEP"
    assert window.export_stl_button.text() == "Export STL"
    assert window.export_dxf_button.text() == "Export DXF"
    assert window.export_all_button.text() == "Export All"
    window.close()


def test_export_buttons_are_disabled_until_generation_is_current():
    window = MainWindow()
    buttons = (
        window.export_step_button,
        window.export_stl_button,
        window.export_dxf_button,
        window.export_all_button,
    )
    assert all(not button.isEnabled() for button in buttons)

    window.controller.bundle.project = _ready_project()
    window.controller.select_tool("tool-1")
    window._refresh_generate_state()
    assert all(not button.isEnabled() for button in buttons)

    window.controller.generate_organizer()
    window._refresh_generate_state()
    assert all(button.isEnabled() for button in buttons)
    window.close()
