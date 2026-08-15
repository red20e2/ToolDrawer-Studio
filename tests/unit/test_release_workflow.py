from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_tagged_release_workflow_contract():
    root = _root()
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "v*.*.*" in workflow
    assert "contents: write" in workflow
    assert "packaging/check_version.py" in workflow
    assert "python -m pytest -q" in workflow
    assert "packaging/build_app.ps1" in workflow
    assert "packaging/verify_frozen.ps1" in workflow
    assert "packaging/build_artifacts.ps1" in workflow
    assert "gh release create" in workflow
    assert "--prerelease" in workflow
    assert '$appVersion = "${{ github.ref_name }}".TrimStart("v")' in workflow
    assert "ToolDrawer-Studio-$appVersion-Setup.exe" in workflow
    assert "ToolDrawer-Studio-$appVersion-Portable.zip" in workflow
    assert "docs/V0.1.1_RELEASE_NOTES.md" in workflow
    assert "SHA256SUMS.txt" in workflow


def test_release_docs_cover_manufacturing_gate_and_windows_distribution():
    root = _root()
    validation = (root / "docs" / "V0.1_MANUFACTURING_VALIDATION.md").read_text(encoding="utf-8")
    notes = (root / "docs" / "V0.1_RELEASE_NOTES.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    for phrase in (
        "Calibration reference",
        "Known CAD dimensions",
        "STEP",
        "slicer",
        "Material",
        "Process",
        "Fit observations",
        "Corrections",
        "Date",
        "Pass/Fail",
    ):
        assert phrase in validation

    assert "0.1.0" in notes
    assert "pre-release" in notes.lower()
    assert "physical validation" in notes.lower()

    assert "Windows x64" in readme
    assert "Portable" in readme
    assert "unsigned" in readme.lower()
    assert "offline" in readme.lower()
    assert "%LOCALAPPDATA%" in readme
    assert ".tds" in readme
    assert "V4" in readme
    assert "physical validation" in readme.lower()
