from pathlib import Path

from tooldrawer_studio.version import __version__


def test_release_workflow_does_not_hardcode_previous_version():
    text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "0.1.0" not in text
    assert "packaging/check_version.py" in text
    assert "build_artifacts.ps1" in text


def test_windows_validation_workflow_does_not_hardcode_previous_version():
    text = Path(".github/workflows/windows-tests.yml").read_text(encoding="utf-8")
    assert "0.1.0" not in text
    assert "build_artifacts.ps1" in text
    assert "SHA256SUMS.txt" in text


def test_canonical_version_is_v011():
    assert __version__ == "0.1.1"
