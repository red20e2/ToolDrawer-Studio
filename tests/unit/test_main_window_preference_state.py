from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.__main__ import build_main_window
from tooldrawer_studio.preferences import Preferences


def test_launched_window_loads_persisted_dialog_directories(monkeypatch, tmp_path: Path):
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
    window = build_main_window()
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


def test_release_window_restores_saved_normal_geometry(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    prefs = Preferences()
    prefs.set_window_geometry(90, 70, 1320, 820, maximized=False)
    prefs.save()

    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    window.show()
    app.processEvents()
    try:
        geometry = window.geometry()
        assert geometry.width() == 1320
        assert geometry.height() == 820
        assert window.isMaximized() is False
    finally:
        window.close()


def test_release_window_recenters_saved_geometry_that_is_offscreen(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    prefs = Preferences()
    prefs.set_window_geometry(50000, 50000, 1320, 820, maximized=False)
    prefs.save()

    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    window.show()
    app.processEvents()
    try:
        geometry = window.geometry()
        assert any(
            geometry.intersects(screen.availableGeometry())
            for screen in QApplication.screens()
        )
        assert geometry.width() == 1320
        assert geometry.height() == 820
    finally:
        window.close()


def test_release_window_saves_last_normal_geometry_on_close(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    window.setGeometry(110, 85, 1450, 880)
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()

    saved = Preferences.load()
    assert saved.window_x is not None
    assert saved.window_y is not None
    assert saved.window_width == 1450
    assert saved.window_height == 880
    assert saved.window_maximized is False


def test_release_window_cleans_up_when_window_state_save_fails(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    app = QApplication.instance() or QApplication([])
    window = build_main_window()

    class PhoneServer:
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    class WebcamService:
        closed = False

        def close(self) -> None:
            self.closed = True

    phone_server = PhoneServer()
    webcam_service = WebcamService()
    window.phone_server = phone_server
    window.webcam_service = webcam_service
    window.webcam_panel = None
    window.show()
    app.processEvents()
    event = QCloseEvent()
    monkeypatch.setattr(window, "_confirm_discard_unsaved", lambda: True)

    def fail_save(_preferences) -> None:
        raise OSError("preferences directory is read-only")

    monkeypatch.setattr(Preferences, "save", fail_save)
    try:
        window.closeEvent(event)

        assert event.isAccepted()
        assert phone_server.stopped is True
        assert webcam_service.closed is True
    finally:
        monkeypatch.setattr(Preferences, "save", lambda _preferences: None)
        window.close()
