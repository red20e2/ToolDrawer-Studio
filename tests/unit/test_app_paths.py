from __future__ import annotations

from pathlib import Path

import pytest


def test_release_paths_live_under_localappdata(monkeypatch, tmp_path: Path):
    try:
        from tooldrawer_studio.app_paths import app_data_dir, logs_dir, preferences_path
    except ModuleNotFoundError:
        pytest.fail("release app path helpers are not implemented")

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = app_data_dir()

    assert root == tmp_path / "ToolDrawer Studio"
    assert preferences_path() == root / "preferences.json"
    assert logs_dir() == root / "logs"
