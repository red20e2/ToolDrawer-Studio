from __future__ import annotations

import os
import sys
from pathlib import Path


def _probe_dependencies() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import cadquery  # noqa: F401
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    import qrcode  # noqa: F401
    import shapely  # noqa: F401
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    if app is None:
        raise RuntimeError("Qt application could not initialize")


def run_release_check(output_dir: Path) -> int:
    try:
        _probe_dependencies()
        from tooldrawer_studio.export.service import export_organizer_package
        from tooldrawer_studio.generation.builder import generate_organizer
        from tooldrawer_studio.release_fixture import build_release_fixture

        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        for mode in ("foam", "gridfinity"):
            bundle = build_release_fixture(mode)
            result = generate_organizer(bundle.project)
            paths = export_organizer_package(result, bundle.project, root / mode)
            for path in (paths.step, paths.stl, paths.dxf):
                if path is None or not path.is_file() or path.stat().st_size <= 0:
                    raise RuntimeError(f"{mode} export missing")
        print("self-test-ok")
        return 0
    except Exception as exc:
        print(f"self-test-failed: {exc}", file=sys.stderr)
        return 1
