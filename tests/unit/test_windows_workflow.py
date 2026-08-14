from pathlib import Path


def test_windows_pr_workflow_has_release_packaging_steps():
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github" / "workflows" / "windows-tests.yml").read_text(encoding="utf-8")

    assert "python -m compileall -q src tests" in text
    assert "python -m pytest -q" in text
    assert "arrange-imports-ok" in text
    assert "generation-imports-ok" in text
    assert "generation-build-ok" in text
    assert "Build frozen Windows app" in text
    assert "Verify frozen Windows app" in text
    assert "Toolchain versions" in text
    assert "Build release artifacts" in text
    assert "build_artifacts.ps1" in text
    assert "Upload Windows release artifacts" in text
    assert "artifacts/" in text
