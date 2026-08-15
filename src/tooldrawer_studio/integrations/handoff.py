from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
from typing import Iterable

from tooldrawer_studio.preferences import Preferences

HANDOFF_APPS = ("orca_slicer", "freecad", "custom")
PREFERRED_FORMATS = {
    "orca_slicer": "stl",
    "freecad": "step",
}


@dataclass(frozen=True, slots=True)
class HandoffTarget:
    key: str
    label: str
    preferred_format: str
    executable: Path | None


def _existing_file(path: Path | None) -> Path | None:
    if path is None:
        return None
    candidate = path.expanduser()
    if candidate.is_file():
        return candidate.resolve()
    return None


def _first_existing(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        found = _existing_file(candidate)
        if found is not None:
            return found
    return None


def _which(names: Iterable[str]) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _program_files_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Programs")
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def detect_orca_slicer(preferences: Preferences | None = None) -> Path | None:
    if preferences is not None:
        found = _existing_file(
            Path(preferences.orca_slicer_path) if preferences.orca_slicer_path else None
        )
        if found is not None:
            return found
    names = ("orca-slicer.exe", "OrcaSlicer.exe", "orca-slicer")
    guessed: list[Path] = []
    for root in _program_files_roots():
        guessed.extend(
            [
                root / "OrcaSlicer" / "orca-slicer.exe",
                root / "OrcaSlicer" / "OrcaSlicer.exe",
                root / "SoftFever" / "OrcaSlicer" / "orca-slicer.exe",
            ]
        )
    return _first_existing(guessed) or _which(names)


def detect_freecad(preferences: Preferences | None = None) -> Path | None:
    if preferences is not None:
        found = _existing_file(
            Path(preferences.freecad_path) if preferences.freecad_path else None
        )
        if found is not None:
            return found
    guessed: list[Path] = []
    for root in _program_files_roots():
        guessed.extend(root.glob("FreeCAD*/bin/FreeCAD.exe"))
        guessed.append(root / "FreeCAD" / "bin" / "FreeCAD.exe")
    return _first_existing(guessed) or _which(("FreeCAD.exe", "freecad", "FreeCAD"))


def detect_custom(preferences: Preferences | None = None) -> Path | None:
    if preferences is None or not preferences.custom_handoff_executable:
        return None
    return _existing_file(Path(preferences.custom_handoff_executable))


def resolve_handoff_target(key: str, preferences: Preferences | None = None) -> HandoffTarget:
    prefs = preferences or Preferences()
    if key == "orca_slicer":
        return HandoffTarget("orca_slicer", "OrcaSlicer", "stl", detect_orca_slicer(prefs))
    if key == "freecad":
        return HandoffTarget("freecad", "FreeCAD", "step", detect_freecad(prefs))
    if key == "custom":
        fmt = prefs.custom_handoff_format or "dxf"
        if fmt not in {"step", "stl", "dxf", "svg", "pdf"}:
            fmt = "dxf"
        label = prefs.custom_handoff_name or "CNC / laser"
        return HandoffTarget("custom", label, fmt, detect_custom(prefs))
    raise ValueError(f"Unknown handoff target: {key}")


def launch_document(executable: Path, document: Path) -> None:
    exe = _existing_file(executable)
    if exe is None:
        raise ValueError(f"Application not found: {executable}")
    if not document.is_file():
        raise ValueError(f"File not found: {document}")
    subprocess.Popen(
        [str(exe), str(document)],
        cwd=str(document.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
