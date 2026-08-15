import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.main_window import MainWindow
from tooldrawer_studio.ui.theme import ACCENT


def test_theme_uses_fusion_and_marks_primary_actions():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert ACCENT in (app.styleSheet() or "")
        assert window.phone_qr_label.objectName() == "phoneQr"
        assert window.calibrate_button.property("role") == "primary"
        assert window.capture_tray.promote_button.property("role") == "primary"
        assert window.capture_tray.delete_button.property("role") == "danger"
        assert window.generate_panel.generate_button.property("role") == "primary"
        assert window.export_all_button.property("role") == "primary"
        assert window.measure_panel.measure_button.property("role") == "primary"
        assert [window.tabs.tabText(index) for index in range(6)] == [
            "1. Import & Calibrate",
            "2. Detect & Edit",
            "3. Measure",
            "4. Arrange",
            "5. Generate",
            "6. Save & Export",
        ]
        assert window.statusBar().currentMessage()
    finally:
        window.close()
    assert app is not None
