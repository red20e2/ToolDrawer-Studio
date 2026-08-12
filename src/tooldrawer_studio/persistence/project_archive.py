from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from tooldrawer_studio.domain.models import CalibrationRecord, CaptureAsset, Point2D, Project, ToolObject

_FORMAT = "tooldrawer-studio"
_SCHEMA_VERSION = 1


@dataclass(slots=True)
class ProjectBundle:
    project: Project
    image_bytes: dict[str, bytes]


def _point_to_dict(point: Point2D) -> dict[str, float]:
    return {"x_mm": point.x_mm, "y_mm": point.y_mm}


def _point_from_dict(data: dict) -> Point2D:
    return Point2D(float(data["x_mm"]), float(data["y_mm"]))


def _project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "schema_version": project.schema_version,
        "captures": [{"id": c.id, "filename": c.filename, "width_px": c.width_px, "height_px": c.height_px, "archive_path": c.archive_path} for c in project.captures],
        "calibrations": [{"id": c.id, "capture_id": c.capture_id, "method": c.method, "matrix_3x3": [list(row) for row in c.matrix_3x3], "residual_mm": c.residual_mm, "confidence": c.confidence} for c in project.calibrations],
        "tools": [{"id": t.id, "name": t.name, "source_capture_id": t.source_capture_id, "base_contour_mm": [_point_to_dict(p) for p in t.base_contour_mm], "contour_mm": [_point_to_dict(p) for p in t.contour_mm], "clearance_mm": t.clearance_mm, "depth_mm": t.depth_mm, "trace_confidence": t.trace_confidence} for t in project.tools],
    }


def _project_from_dict(data: dict) -> Project:
    schema_version = int(data.get("schema_version", 0))
    if schema_version != _SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {schema_version}")
    captures = [CaptureAsset(id=str(i["id"]), filename=str(i["filename"]), width_px=int(i["width_px"]), height_px=int(i["height_px"]), archive_path=str(i["archive_path"])) for i in data.get("captures", [])]
    calibrations = [CalibrationRecord(id=str(i["id"]), capture_id=str(i["capture_id"]), method=str(i["method"]), matrix_3x3=tuple(tuple(float(v) for v in row) for row in i["matrix_3x3"]), residual_mm=float(i["residual_mm"]), confidence=float(i["confidence"])) for i in data.get("calibrations", [])]
    tools = [ToolObject(id=str(i["id"]), name=str(i["name"]), source_capture_id=str(i["source_capture_id"]), base_contour_mm=[_point_from_dict(p) for p in i["base_contour_mm"]], contour_mm=[_point_from_dict(p) for p in i["contour_mm"]], clearance_mm=float(i.get("clearance_mm", 0.6)), depth_mm=float(i.get("depth_mm", 5.0)), trace_confidence=float(i.get("trace_confidence", 0.0))) for i in data.get("tools", [])]
    return Project(id=str(data["id"]), name=str(data["name"]), schema_version=schema_version, captures=captures, calibrations=calibrations, tools=tools)


def _validate_archive_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe archive path: {name}")


def save_project(bundle: ProjectBundle, path: Path) -> None:
    if bundle.project.schema_version != _SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {bundle.project.schema_version}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps({"format": _FORMAT, "schema_version": _SCHEMA_VERSION}, separators=(",", ":")))
            archive.writestr("project.json", json.dumps(_project_to_dict(bundle.project), separators=(",", ":")))
            for capture in bundle.project.captures:
                _validate_archive_path(capture.archive_path)
                try:
                    raw = bundle.image_bytes[capture.id]
                except KeyError as exc:
                    raise ValueError(f"Missing source image bytes for capture: {capture.id}") from exc
                archive.writestr(capture.archive_path, raw)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_project(path: Path) -> ProjectBundle:
    try:
        with ZipFile(path, "r") as archive:
            names = archive.namelist()
            for name in names:
                _validate_archive_path(name)
            if "manifest.json" not in names or "project.json" not in names:
                raise ValueError("Invalid ToolDrawer Studio project archive")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != _FORMAT:
                raise ValueError("Invalid ToolDrawer Studio project archive")
            schema_version = int(manifest.get("schema_version", 0))
            if schema_version != _SCHEMA_VERSION:
                raise ValueError(f"Unsupported project schema version: {schema_version}")
            project = _project_from_dict(json.loads(archive.read("project.json")))
            image_bytes: dict[str, bytes] = {}
            for capture in project.captures:
                _validate_archive_path(capture.archive_path)
                if capture.archive_path not in names:
                    raise ValueError(f"Missing source image in project: {capture.archive_path}")
                image_bytes[capture.id] = archive.read(capture.archive_path)
            return ProjectBundle(project=project, image_bytes=image_bytes)
    except BadZipFile as exc:
        raise ValueError("Invalid ToolDrawer Studio project archive") from exc
