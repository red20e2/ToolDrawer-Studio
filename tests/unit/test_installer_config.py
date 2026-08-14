from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_inno_installer_is_per_user_x64_and_versioned_from_build():
    installer = _root() / "packaging" / "ToolDrawerStudio.iss"
    assert installer.is_file()
    text = installer.read_text(encoding="utf-8")
    normalized = text.replace(" ", "").lower()

    assert "privilegesrequired=lowest" in normalized
    assert "architecturesallowed=x64compatible" in normalized
    assert "architecturesinstallin64bitmode=x64compatible" in normalized
    assert "{localappdata}" in text.lower()
    assert "#ifndef AppVersion" in text
    assert '#define AppVersion "0.1.0"' not in text
    assert "{#AppVersion}" in text
    assert "ToolDrawer-Studio-{#AppVersion}-Setup" in text


def test_inno_installer_packages_app_and_shortcuts():
    text = (_root() / "packaging" / "ToolDrawerStudio.iss").read_text(encoding="utf-8")
    lower = text.lower()

    assert 'Source: "..\\dist\\ToolDrawer Studio\\*"' in text
    assert "ToolDrawer Studio.exe" in text
    assert "[icons]" in lower
    assert "{group}" in lower
    assert "{userdesktop}" in lower
    assert "desktopicon" in lower
    assert "[tasks]" in lower
    assert "uninstallable=no" not in lower
