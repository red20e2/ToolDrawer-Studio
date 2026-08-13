from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QProgressBar

from tooldrawer_studio.__main__ import build_main_window


def _busy_api():
    try:
        from tooldrawer_studio.ui.busy_scope import busy_ui
    except ModuleNotFoundError:
        pytest.fail("release busy-state helper is not implemented")
    return busy_ui


def test_busy_scope_disables_conflicting_actions_and_uses_indeterminate_progress(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    try:
        try:
            progress = window.operation_progress
        except AttributeError:
            pytest.fail("release operation progress indicator is not implemented")
        busy_ui = _busy_api()
        window.generate_panel.generate_button.setEnabled(True)
        window.export_step_button.setEnabled(True)
        with busy_ui(window, "Generating organizer"):
            assert window.generate_panel.generate_button.isEnabled() is False
            assert window.export_step_button.isEnabled() is False
            assert progress.isVisible() is True
            assert isinstance(progress, QProgressBar)
            assert progress.minimum() == 0
            assert progress.maximum() == 0
        assert window.generate_panel.generate_button.isEnabled() is True
        assert window.export_step_button.isEnabled() is True
        assert progress.isVisible() is False
    finally:
        window.close()
    assert app is not None


def test_busy_scope_restores_controls_after_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    busy_ui = _busy_api()
    window.generate_panel.generate_button.setEnabled(True)
    try:
        with pytest.raises(RuntimeError):
            with busy_ui(window, "Exporting organizer"):
                raise RuntimeError("fixture failure")
        assert window.generate_panel.generate_button.isEnabled() is True
        assert window.operation_progress.isVisible() is False
    finally:
        window.close()
    assert app is not None
