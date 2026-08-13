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


def test_release_build_scripts_exist():
    build_script = _root() / "packaging" / "build_app.ps1"
    verify_script = _root() / "packaging" / "verify_frozen.ps1"
    verify_cmd = _root() / "packaging" / "verify_frozen.cmd"
    assert build_script.is_file()
    assert verify_script.is_file()
    assert verify_cmd.is_file()
    assert "ToolDrawerStudio.spec" in build_script.read_text(encoding="utf-8")
    assert "verify_frozen.cmd" in verify_script.read_text(encoding="utf-8")
    assert "ToolDrawer Studio.exe" in verify_cmd.read_text(encoding="utf-8")
