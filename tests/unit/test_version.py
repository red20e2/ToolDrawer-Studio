from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio import __version__
from tooldrawer_studio.__main__ import build_main_window


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "packaging" / "check_version.py"


def test_runtime_version_and_window_title_use_0_1_1():
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    try:
        assert __version__ == "0.1.1"
        assert window.windowTitle() == "ToolDrawer Studio 0.1.1"
    finally:
        window.close()
    assert app is not None


def test_release_tag_checker_accepts_only_matching_tag():
    matching = subprocess.run(
        [sys.executable, str(CHECKER), "v0.1.1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    mismatch = subprocess.run(
        [sys.executable, str(CHECKER), "v0.1.0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert matching.returncode == 0, matching.stderr
    assert "version-ok: 0.1.1" in matching.stdout
    assert mismatch.returncode != 0
    assert "Tag v0.1.0 does not match application version 0.1.1" in mismatch.stderr
