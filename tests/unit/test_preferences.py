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

    path = tmp_path / "ToolDrawer Studio" / "preferences.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    corrupt = Preferences.load()
    assert corrupt.recent_projects == []


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
