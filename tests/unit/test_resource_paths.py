from pathlib import Path
import sys

import tooldrawer_studio.app_paths as app_paths


def test_resource_root_uses_source_tree(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    expected = Path(app_paths.__file__).resolve().parents[2]
    assert app_paths.resource_root() == expected
    assert app_paths.resource_path("packaging", "example.txt") == expected / "packaging" / "example.txt"


def test_resource_root_uses_frozen_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert app_paths.resource_root() == bundle.resolve()
    assert app_paths.resource_path("assets", "icon.ico") == bundle.resolve() / "assets" / "icon.ico"
