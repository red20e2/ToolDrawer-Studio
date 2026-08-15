from pathlib import Path

import pytest

from tooldrawer_studio.integrations.handoff import (
    launch_document,
    resolve_handoff_target,
)
from tooldrawer_studio.preferences import Preferences


def test_resolve_uses_preference_path_when_present(tmp_path: Path):
    orca = tmp_path / "orca-slicer.exe"
    orca.write_bytes(b"fake")
    prefs = Preferences(orca_slicer_path=str(orca))
    target = resolve_handoff_target("orca_slicer", prefs)
    assert target.preferred_format == "stl"
    assert target.executable == orca.resolve()


def test_resolve_custom_target_uses_configured_format(tmp_path: Path):
    exe = tmp_path / "laser.exe"
    exe.write_bytes(b"fake")
    prefs = Preferences(
        custom_handoff_name="Glowforge",
        custom_handoff_executable=str(exe),
        custom_handoff_format="svg",
    )
    target = resolve_handoff_target("custom", prefs)
    assert target.label == "Glowforge"
    assert target.preferred_format == "svg"
    assert target.executable == exe.resolve()


def test_missing_app_is_none_without_crashing():
    target = resolve_handoff_target("freecad", Preferences())
    assert target.preferred_format == "step"
    assert target.executable is None or target.executable.is_file()


def test_launch_rejects_missing_files(tmp_path: Path):
    with pytest.raises(ValueError, match="not found"):
        launch_document(tmp_path / "missing.exe", tmp_path / "part.stl")
