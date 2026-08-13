from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from tooldrawer_studio.__main__ import build_main_window


def test_release_window_tracks_editable_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    try:
        try:
            tracker = window.project_edit_tracker
        except AttributeError:
            pytest.fail("release window edit tracking is not implemented")
        assert tracker.has_unsaved_changes() is False
        window.controller.project.name = "Edited project"
        assert tracker.has_unsaved_changes() is True
    finally:
        window.close()
    assert app is not None


def test_unsaved_guard_honors_cancel_discard_and_successful_save(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    window.controller.project.name = "Edited project"
    try:
        try:
            confirm = window._confirm_discard_unsaved
        except AttributeError:
            pytest.fail("unsaved project confirmation is not implemented")

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )
        assert confirm() is False

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
        )
        assert confirm() is True

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Save,
        )
        monkeypatch.setattr(window, "_save_project", lambda: True)
        assert confirm() is True

        monkeypatch.setattr(window, "_save_project", lambda: False)
        assert confirm() is False
    finally:
        window.controller.project.name = "Untitled Project"
        window.close()
    assert app is not None
