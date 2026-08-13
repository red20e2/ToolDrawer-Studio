from pathlib import Path
import tomllib


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_pyinstaller_is_declared_for_release_builds():
    data = tomllib.loads((_root() / "pyproject.toml").read_text(encoding="utf-8"))
    dev = data["project"]["optional-dependencies"]["dev"]
    assert any(item.lower().startswith("pyinstaller") for item in dev)


def test_pyinstaller_spec_builds_windowed_onedir_app():
    spec = _root() / "packaging" / "ToolDrawerStudio.spec"
    assert spec.is_file()
    text = spec.read_text(encoding="utf-8")
    normalized = text.replace("'", '"').replace("\\", "/")
    assert "src/tooldrawer_studio/__main__.py" in normalized
    assert 'name="ToolDrawer Studio"' in normalized
    assert "console=False" in text
    assert "exclude_binaries=True" in text
    assert "COLLECT(" in text


def test_release_build_scripts_run_frozen_verification():
    build_script = _root() / "packaging" / "build_app.ps1"
    verify_script = _root() / "packaging" / "verify_frozen.ps1"
    assert build_script.is_file()
    assert verify_script.is_file()
    build_text = build_script.read_text(encoding="utf-8")
    verify_text = verify_script.read_text(encoding="utf-8")
    assert "ToolDrawerStudio.spec" in build_text
    assert "ToolDrawer Studio.exe" in build_text
    assert "ToolDrawer Studio.exe" in verify_text
    assert ("--self-" + "test") in verify_text
    assert "--output-dir" in verify_text
