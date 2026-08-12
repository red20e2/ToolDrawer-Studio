from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from tooldrawer_studio.domain.models import (
    CalibrationRecord,
    CaptureAsset,
    Point2D,
    Project,
    ToolObject,
)
from tooldrawer_studio.measurement.models import ImagePoint
from tooldrawer_studio.persistence.migrations import (
    CURRENT_SCHEMA_VERSION,
    migrate_project_dict,
)

_FORMAT = "tooldrawer-studio"


@dataclass(slots=True)
class ProjectBundle:
    project: Project
    image_bytes: dict[str, bytes]


def _point_to_dict(point: Point2D) -> dict[str, float]:
    return {"x_mm": point.x_mm, "y_mm": point.y_mm}


def _point_from_dict(data: dict) -> Point2D:
    return Point2D(float(data["x_mm"]), float(data["y_mm"]))


def _image_point_to_dict(point: ImagePoint) -> dict[str, float]:
    return {"x_px": point.x_px, "y_px": point.y_px}


def _image_point_from_dict(data: dict) -> ImagePoint:
    return ImagePoint(float(data["x_px"]), float(data["y_px"]))


def _optional_image_point_to_dict(point: ImagePoint | None) -> dict[str, float] | None:
    return None if point is None else _image_point_to_dict(point)


def _optional_image_point_from_dict(data: dict | None) -> ImagePoint | None:
    return None if data is None else _image_point_from_dict(data)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "schema_version": project.schema_version,
        "default_exposed_height_mm": project.default_exposed_height_mm,
        "default_bottom_clearance_mm": project.default_bottom_clearance_mm,
        "captures": [
            {
                "id": capture.id,
                "filename": capture.filename,
                "width_px": capture.width_px,
                "height_px": capture.height_px,
                "archive_path": capture.archive_path,
            }
            for capture in project.captures
        ],
        "calibrations": [
            {
                "id": calibration.id,
                "capture_id": calibration.capture_id,
                "method": calibration.method,
                "matrix_3x3": [list(row) for row in calibration.matrix_3x3],
                "residual_mm": calibration.residual_mm,
                "confidence": calibration.confidence,
            }
            for calibration in project.calibrations
        ],
        "tools": [
            {
                "id": tool.id,
                "name": tool.name,
                "source_capture_id": tool.source_capture_id,
                "base_contour_mm": [_point_to_dict(point) for point in tool.base_contour_mm],
                "contour_mm": [_point_to_dict(point) for point in tool.contour_mm],
                "clearance_mm": tool.clearance_mm,
                "trace_confidence": tool.trace_confidence,
                "side_view_capture_id": tool.side_view_capture_id,
                "automatic_thickness_mm": tool.automatic_thickness_mm,
                "automatic_thickness_confidence": tool.automatic_thickness_confidence,
                "automatic_thickness_endpoint_a_px": _optional_image_point_to_dict(
                    tool.automatic_thickness_endpoint_a_px
                ),
                "automatic_thickness_endpoint_b_px": _optional_image_point_to_dict(
                    tool.automatic_thickness_endpoint_b_px
                ),
                "corrected_thickness_endpoint_a_px": _optional_image_point_to_dict(
                    tool.corrected_thickness_endpoint_a_px
                ),
                "corrected_thickness_endpoint_b_px": _optional_image_point_to_dict(
                    tool.corrected_thickness_endpoint_b_px
                ),
                "side_view_silhouette_px": [
                    _image_point_to_dict(point) for point in tool.side_view_silhouette_px
                ],
                "accepted_thickness_mm": tool.accepted_thickness_mm,
                "thickness_measurement_mode": tool.thickness_measurement_mode,
                "thickness_accepted": tool.thickness_accepted,
                "exposed_height_override_mm": tool.exposed_height_override_mm,
                "bottom_clearance_override_mm": tool.bottom_clearance_override_mm,
                "pocket_depth_override_mm": tool.pocket_depth_override_mm,
                "thickness_review_required": tool.thickness_review_required,
            }
            for tool in project.tools
        ],
    }


def _project_from_dict(data: dict) -> Project:
    schema_version = int(data.get("schema_version", 0))
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {schema_version}")

    captures = [
        CaptureAsset(
            id=str(item["id"]),
            filename=str(item["filename"]),
            width_px=int(item["width_px"]),
            height_px=int(item["height_px"]),
            archive_path=str(item["archive_path"]),
        )
        for item in data.get("captures", [])
    ]
    calibrations = [
        CalibrationRecord(
            id=str(item["id"]),
            capture_id=str(item["capture_id"]),
            method=str(item["method"]),
            matrix_3x3=tuple(
                tuple(float(value) for value in row) for row in item["matrix_3x3"]
            ),
            residual_mm=float(item["residual_mm"]),
            confidence=float(item["confidence"]),
        )
        for item in data.get("calibrations", [])
    ]

    tools: list[ToolObject] = []
    for item in data.get("tools", []):
        pocket_override = _optional_float(item.get("pocket_depth_override_mm"))
        tools.append(
            ToolObject(
                id=str(item["id"]),
                name=str(item["name"]),
                source_capture_id=str(item["source_capture_id"]),
                base_contour_mm=[
                    _point_from_dict(point) for point in item["base_contour_mm"]
                ],
                contour_mm=[_point_from_dict(point) for point in item["contour_mm"]],
                clearance_mm=float(item.get("clearance_mm", 0.6)),
                trace_confidence=float(item.get("trace_confidence", 0.0)),
                side_view_capture_id=(
                    None
                    if item.get("side_view_capture_id") is None
                    else str(item["side_view_capture_id"])
                ),
                automatic_thickness_mm=_optional_float(
                    item.get("automatic_thickness_mm")
                ),
                automatic_thickness_confidence=_optional_float(
                    item.get("automatic_thickness_confidence")
                ),
                automatic_thickness_endpoint_a_px=_optional_image_point_from_dict(
                    item.get("automatic_thickness_endpoint_a_px")
                ),
                automatic_thickness_endpoint_b_px=_optional_image_point_from_dict(
                    item.get("automatic_thickness_endpoint_b_px")
                ),
                corrected_thickness_endpoint_a_px=_optional_image_point_from_dict(
                    item.get("corrected_thickness_endpoint_a_px")
                ),
                corrected_thickness_endpoint_b_px=_optional_image_point_from_dict(
                    item.get("corrected_thickness_endpoint_b_px")
                ),
                side_view_silhouette_px=[
                    _image_point_from_dict(point)
                    for point in item.get("side_view_silhouette_px", [])
                ],
                accepted_thickness_mm=_optional_float(
                    item.get("accepted_thickness_mm")
                ),
                thickness_measurement_mode=str(
                    item.get("thickness_measurement_mode", "none")
                ),
                thickness_accepted=bool(item.get("thickness_accepted", False)),
                exposed_height_override_mm=_optional_float(
                    item.get("exposed_height_override_mm")
                ),
                bottom_clearance_override_mm=_optional_float(
                    item.get("bottom_clearance_override_mm")
                ),
                pocket_depth_override_mm=pocket_override,
                thickness_review_required=bool(
                    item.get("thickness_review_required", False)
                ),
            )
        )

    return Project(
        id=str(data["id"]),
        name=str(data["name"]),
        schema_version=schema_version,
        captures=captures,
        calibrations=calibrations,
        tools=tools,
        default_exposed_height_mm=float(data.get("default_exposed_height_mm", 4.0)),
        default_bottom_clearance_mm=float(
            data.get("default_bottom_clearance_mm", 0.8)
        ),
    )


def _validate_archive_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe archive path: {name}")


def save_project(bundle: ProjectBundle, path: Path) -> None:
    if bundle.project.schema_version != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version: {bundle.project.schema_version}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {"format": _FORMAT, "schema_version": CURRENT_SCHEMA_VERSION},
                    separators=(",", ":"),
                ),
            )
            archive.writestr(
                "project.json",
                json.dumps(_project_to_dict(bundle.project), separators=(",", ":")),
            )
            for capture in bundle.project.captures:
                _validate_archive_path(capture.archive_path)
                try:
                    raw = bundle.image_bytes[capture.id]
                except KeyError as exc:
                    raise ValueError(
                        f"Missing source image bytes for capture: {capture.id}"
                    ) from exc
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
            if schema_version < 1 or schema_version > CURRENT_SCHEMA_VERSION:
                raise ValueError(f"Unsupported project schema version: {schema_version}")

            raw_project = json.loads(archive.read("project.json"))
            migrated = migrate_project_dict(raw_project, schema_version)
            project = _project_from_dict(migrated)

            image_bytes: dict[str, bytes] = {}
            for capture in project.captures:
                _validate_archive_path(capture.archive_path)
                if capture.archive_path not in names:
                    raise ValueError(
                        f"Missing source image in project: {capture.archive_path}"
                    )
                image_bytes[capture.id] = archive.read(capture.archive_path)
            return ProjectBundle(project=project, image_bytes=image_bytes)
    except BadZipFile as exc:
        raise ValueError("Invalid ToolDrawer Studio project archive") from exc