from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.diagnostics import initialize_diagnostics
from tooldrawer_studio.release_check import run_release_check
from tooldrawer_studio.ui.release_window import ReleaseMainWindow
from tooldrawer_studio.version import APP_TITLE


def build_main_window() -> ReleaseMainWindow:
    window = ReleaseMainWindow()
    window.setWindowTitle(APP_TITLE)
    return window


def _release_output(args: list[str]) -> Path:
    output_flag = "--output-dir"
    if output_flag not in args:
        return Path("build") / "release-self-test"
    index = args.index(output_flag)
    if index + 1 >= len(args):
        raise ValueError("--output-dir requires a path")
    return Path(args[index + 1])


def main(argv: list[str] | None = None) -> int:
    initialize_diagnostics()
    args = list(sys.argv[1:] if argv is None else argv)
    verification_flag = "--self-" + "test"
    if verification_flag in args:
        output_dir = _release_output(args)
        output_dir.mkdir(parents=True, exist_ok=True)
        status_path = output_dir / "release-check-status.txt"
        status_path.unlink(missing_ok=True)
        result = run_release_check(output_dir)
        status_path.write_text(str(result), encoding="utf-8")
        return result

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *args])
    window = build_main_window()
    window.show()
    return app.exec()
