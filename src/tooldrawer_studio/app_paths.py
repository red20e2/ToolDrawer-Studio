from __future__ import annotations

import os
import sys
from pathlib import Path


_APP_DIRECTORY_NAME = "ToolDrawer Studio"


def app_data_dir() -> Path:
    """Return the per-user writable application-data directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not available")
    return Path(local_app_data).expanduser().resolve() / _APP_DIRECTORY_NAME


def preferences_path() -> Path:
    return app_data_dir() / "preferences.json"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def resource_root() -> Path:
    """Return the read-only application resource root in source or frozen mode."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(str(bundled_root)).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)
