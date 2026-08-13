from __future__ import annotations

import os
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
