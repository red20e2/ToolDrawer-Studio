from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_DLL_DIRECTORY_HANDLES: list[Any] = []


def prepare_frozen_runtime() -> None:
    """Prepare native-library search paths before importing CAD dependencies."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root or not sys.platform.startswith("win"):
        return

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return

    casadi_dir = Path(str(bundle_root)).resolve() / "casadi"
    if not casadi_dir.is_dir():
        return

    handle = add_dll_directory(str(casadi_dir))
    _DLL_DIRECTORY_HANDLES.append(handle)
