from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tooldrawer_studio.app_paths import preferences_path

MAX_RECENT_PROJECTS = 10
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 700


def _absolute_directory(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return None
    return str(candidate.resolve())


def _plain_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


@dataclass(slots=True)
class Preferences:
    recent_projects: list[str] = field(default_factory=list)
    project_directory: str | None = None
    export_directory: str | None = None
    photo_import_directory: str | None = None
    window_x: int | None = None
    window_y: int | None = None
    window_width: int | None = None
    window_height: int | None = None
    window_maximized: bool = False

    @classmethod
    def load(cls) -> "Preferences":
        path = preferences_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return cls()
        if not isinstance(payload, dict):
            return cls()

        recent: list[str] = []
        raw_recent = payload.get("recent_projects", [])
        if isinstance(raw_recent, list):
            for item in raw_recent:
                if not isinstance(item, str) or not item:
                    continue
                candidate = Path(item).expanduser()
                if not candidate.is_absolute():
                    continue
                resolved = candidate.resolve()
                text = str(resolved)
                if resolved.is_file() and text not in recent:
                    recent.append(text)
                if len(recent) >= MAX_RECENT_PROJECTS:
                    break

        window_x = _plain_int(payload.get("window_x"))
        window_y = _plain_int(payload.get("window_y"))
        window_width = _plain_int(payload.get("window_width"))
        window_height = _plain_int(payload.get("window_height"))
        geometry_valid = (
            window_x is not None
            and window_y is not None
            and window_width is not None
            and window_height is not None
            and window_width >= MIN_WINDOW_WIDTH
            and window_height >= MIN_WINDOW_HEIGHT
        )
        if not geometry_valid:
            window_x = None
            window_y = None
            window_width = None
            window_height = None

        raw_maximized = payload.get("window_maximized", False)
        window_maximized = raw_maximized if isinstance(raw_maximized, bool) else False

        return cls(
            recent_projects=recent,
            project_directory=_absolute_directory(payload.get("project_directory")),
            export_directory=_absolute_directory(payload.get("export_directory")),
            photo_import_directory=_absolute_directory(payload.get("photo_import_directory")),
            window_x=window_x,
            window_y=window_y,
            window_width=window_width,
            window_height=window_height,
            window_maximized=window_maximized,
        )

    def add_recent_project(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        text = str(resolved)
        self.recent_projects = [item for item in self.recent_projects if item != text]
        if resolved.is_file():
            self.recent_projects.insert(0, text)
        self.recent_projects = self.recent_projects[:MAX_RECENT_PROJECTS]

    def set_project_directory(self, path: Path) -> None:
        self.project_directory = str(path.expanduser().resolve())

    def set_export_directory(self, path: Path) -> None:
        self.export_directory = str(path.expanduser().resolve())

    def set_photo_import_directory(self, path: Path) -> None:
        self.photo_import_directory = str(path.expanduser().resolve())

    def set_window_geometry(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        maximized: bool,
    ) -> None:
        if isinstance(x, bool) or isinstance(y, bool):
            raise ValueError("Window position must use integer coordinates")
        if isinstance(width, bool) or isinstance(height, bool):
            raise ValueError("Window size must use integer dimensions")
        if width < MIN_WINDOW_WIDTH or height < MIN_WINDOW_HEIGHT:
            raise ValueError(
                f"Window size must be at least {MIN_WINDOW_WIDTH} x {MIN_WINDOW_HEIGHT}"
            )
        self.window_x = int(x)
        self.window_y = int(y)
        self.window_width = int(width)
        self.window_height = int(height)
        self.window_maximized = bool(maximized)

    def save(self) -> None:
        destination = preferences_path()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.recent_projects = [
            item for item in self.recent_projects
            if Path(item).is_absolute() and Path(item).is_file()
        ][:MAX_RECENT_PROJECTS]
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(asdict(self), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
