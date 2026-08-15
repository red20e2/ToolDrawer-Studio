from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tooldrawer_studio.app_paths import preferences_path

MAX_RECENT_PROJECTS = 10


def _absolute_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return None
    return str(candidate.resolve())


@dataclass(slots=True)
class Preferences:
    recent_projects: list[str] = field(default_factory=list)
    project_directory: str | None = None
    export_directory: str | None = None
    photo_import_directory: str | None = None
    orca_slicer_path: str | None = None
    freecad_path: str | None = None
    custom_handoff_name: str | None = None
    custom_handoff_executable: str | None = None
    custom_handoff_format: str = "dxf"

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

        format_value = payload.get("custom_handoff_format", "dxf")
        custom_format = (
            str(format_value)
            if format_value in {"step", "stl", "dxf", "svg", "pdf"}
            else "dxf"
        )
        name = payload.get("custom_handoff_name")
        return cls(
            recent_projects=recent,
            project_directory=_absolute_path(payload.get("project_directory")),
            export_directory=_absolute_path(payload.get("export_directory")),
            photo_import_directory=_absolute_path(payload.get("photo_import_directory")),
            orca_slicer_path=_absolute_path(payload.get("orca_slicer_path")),
            freecad_path=_absolute_path(payload.get("freecad_path")),
            custom_handoff_name=str(name) if isinstance(name, str) and name.strip() else None,
            custom_handoff_executable=_absolute_path(payload.get("custom_handoff_executable")),
            custom_handoff_format=custom_format,
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
