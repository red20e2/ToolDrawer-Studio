from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.preferences import Preferences
from tooldrawer_studio.ui.main_window import MainWindow


def test_main_window_loads_persisted_dialog_directories(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    project_dir = (tmp_path / "projects").resolve()
    export_dir = (tmp_path / "exports").resolve()
    photo_dir = (tmp_path / "photos").resolve()
    for directory in (project_dir, export_dir, photo_dir):
        directory.mkdir(parents=True)
    Preferences(
        project_directory=str(project_dir),
        export_directory=str(export_dir),
        photo_import_directory=str(photo_dir),
    ).save()

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.preferences.project_directory == str(project_dir)
        assert window.preferences.export_directory == str(export_dir)
        assert window.preferences.photo_import_directory == str(photo_dir)
        assert window._dialog_directory("project") == str(project_dir)
        assert window._dialog_directory("export") == str(export_dir)
        assert window._dialog_directory("photo") == str(photo_dir)
    finally:
        window.close()
    assert app is not None
