import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.generate_panel import GeneratePanel
from tooldrawer_studio.ui.main_window import MainWindow
from tooldrawer_studio.ui.model_preview import ModelPreview


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


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


def test_generate_panel_signals_are_connected_to_window_handlers():
    window = MainWindow()
    receivers = window.generate_panel.generateRequested.receivers()
    assert receivers >= 1
    window.close()
