from __future__ import annotations

import json
from pathlib import Path

import pytest


def _preferences_type():
    try:
        from tooldrawer_studio.preferences import Preferences
    except ModuleNotFoundError:
        pytest.fail("release preferences are not implemented")
    return Preferences


def test_missing_and_corrupt_preferences_fall_back_to_defaults(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    Preferences = _preferences_type()

    missing = Preferences.load()
    assert missing.recent_projects == []
    assert missing.project_directory is None
    assert missing.export_directory is None
    assert missing.photo_import_directory is None
    assert missing.window_x is None
    assert missing.window_y is None
    assert missing.window_width is None
    assert missing.window_height is None
    assert missing.window_maximized is False

    path = tmp_path / "ToolDrawer Studio" / "preferences.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    corrupt = Preferences.load()
    assert corrupt.recent_projects == []
    assert corrupt.window_width is None


def test_recent_projects_are_absolute_deduped_existing_and_capped_at_ten(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    Preferences = _preferences_type()
    projects = tmp_path / "projects"
    projects.mkdir()
    paths = []
    for index in range(12):
        path = projects / f"project-{index}.tds"
        path.write_text(str(index), encoding="utf-8")
        paths.append(path.resolve())

    prefs = Preferences()
    for path in paths:
        prefs.add_recent_project(path)
    prefs.add_recent_project(paths[5])

    assert len(prefs.recent_projects) == 10
    assert prefs.recent_projects[0] == str(paths[5])
    assert len(set(prefs.recent_projects)) == 10
    assert all(Path(item).is_absolute() for item in prefs.recent_projects)

    paths[4].unlink()
    prefs.save()
    loaded = Preferences.load()
    assert str(paths[4]) not in loaded.recent_projects


def test_preferences_save_atomically_and_persist_last_directories(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    Preferences = _preferences_type()
    project_dir = (tmp_path / "projects").resolve()
    export_dir = (tmp_path / "exports").resolve()
    photo_dir = (tmp_path / "photos").resolve()
    for directory in (project_dir, export_dir, photo_dir):
        directory.mkdir(parents=True)

    prefs = Preferences(
        project_directory=str(project_dir),
        export_directory=str(export_dir),
        photo_import_directory=str(photo_dir),
    )
    prefs.save()

    path = tmp_path / "local" / "ToolDrawer Studio" / "preferences.json"
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["project_directory"] == str(project_dir)
    assert payload["export_directory"] == str(export_dir)
    assert payload["photo_import_directory"] == str(photo_dir)


def test_window_geometry_and_maximized_state_roundtrip(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    Preferences = _preferences_type()

    prefs = Preferences()
    prefs.set_window_geometry(120, 80, 1500, 940, maximized=True)
    prefs.save()
    loaded = Preferences.load()

    assert loaded.window_x == 120
    assert loaded.window_y == 80
    assert loaded.window_width == 1500
    assert loaded.window_height == 940
    assert loaded.window_maximized is True


def test_invalid_saved_window_geometry_is_ignored(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    Preferences = _preferences_type()
    path = tmp_path / "local" / "ToolDrawer Studio" / "preferences.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "window_x": "bad",
                "window_y": 20,
                "window_width": 300,
                "window_height": -5,
                "window_maximized": "yes",
            }
        ),
        encoding="utf-8",
    )

    loaded = Preferences.load()

    assert loaded.window_x is None
    assert loaded.window_y is None
    assert loaded.window_width is None
    assert loaded.window_height is None
    assert loaded.window_maximized is False
