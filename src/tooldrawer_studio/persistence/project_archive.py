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
from tooldrawer_studio.generation.models import GenerationSettings, GenerationState
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
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


def _placement_to_dict(placement: ToolPlacement) -> dict:
    return {
        "tool_id": placement.tool_id,
        "x_mm": placement.x_mm,
        "y_mm": placement.y_mm,
        "rotation_deg": placement.rotation_deg,
        "locked": placement.locked,
        "rotation_policy": placement.rotation_policy,
        "grab_side": placement.grab_side,
        "grab_clearance_override_mm": placement.grab_clearance_override_mm,
        "is_placed": placement.is_placed,
    }


def _placement_from_dict(data: dict) -> ToolPlacement:
    return ToolPlacement(
        tool_id=str(data["tool_id"]),
        x_mm=float(data.get("x_mm", 0.0)),
        y_mm=float(data.get("y_mm", 0.0)),
        rotation_deg=float(data.get("rotation_deg", 0.0)),
        locked=bool(data.get("locked", False)),
        rotation_policy=str(data.get("rotation_policy", "free")),
        grab_side=str(data.get("grab_side", "none")),
        grab_clearance_override_mm=_optional_float(
            data.get("grab_clearance_override_mm")
        ),
        is_placed=bool(data.get("is_placed", False)),
    )


def _layout_to_dict(layout: LayoutState | None) -> dict | None:
    if layout is None:
        return None
    return {
        "mode": layout.mode,
        "foam_width_mm": layout.foam_width_mm,
        "foam_height_mm": layout.foam_height_mm,
        "grid_columns": layout.grid_columns,
        "grid_rows": layout.grid_rows,
        "grid_pitch_mm": layout.grid_pitch_mm,
        "spacing_mm": layout.spacing_mm,
        "border_mm": layout.border_mm,
        "grab_clearance_mm": layout.grab_clearance_mm,
        "snap_enabled": layout.snap_enabled,
        "snap_increment_mm": layout.snap_increment_mm,
        "placements": [_placement_to_dict(item) for item in layout.placements],
        "unplaced_tool_ids": list(layout.unplaced_tool_ids),
        "review_required": layout.review_required,
    }


def _layout_from_dict(data: dict | None) -> LayoutState | None:
    if data is None:
        return None
    return LayoutState(
        mode=str(data["mode"]),
        foam_width_mm=_optional_float(data.get("foam_width_mm")),
        foam_height_mm=_optional_float(data.get("foam_height_mm")),
        grid_columns=(
            None if data.get("grid_columns") is None else int(data["grid_columns"])
        ),
        grid_rows=None if data.get("grid_rows") is None else int(data["grid_rows"]),
        grid_pitch_mm=float(data.get("grid_pitch_mm", 42.0)),
        spacing_mm=float(data.get("spacing_mm", 3.0)),
        border_mm=float(data.get("border_mm", 4.0)),
        grab_clearance_mm=float(data.get("grab_clearance_mm", 12.0)),
        snap_enabled=bool(data.get("snap_enabled", False)),
        snap_increment_mm=float(data.get("snap_increment_mm", 1.0)),
        placements=[
            _placement_from_dict(item) for item in data.get("placements", [])
        ],
        unplaced_tool_ids=[str(item) for item in data.get("unplaced_tool_ids", [])],
        review_required=bool(data.get("review_required", False)),
    )


def _generation_settings_to_dict(settings: GenerationSettings) -> dict:
    return {
        "height_mode": settings.height_mode,
        "manual_height_mm": settings.manual_height_mm,
        "minimum_floor_mm": settings.minimum_floor_mm,
        "minimum_wall_mm": settings.minimum_wall_mm,
        "scoops_enabled": settings.scoops_enabled,
        "tool_scoop_modes": dict(settings.tool_scoop_modes),
        "magnets_enabled": settings.magnets_enabled,
        "magnet_diameter_mm": settings.magnet_diameter_mm,
        "magnet_depth_mm": settings.magnet_depth_mm,
        "screw_holes_enabled": settings.screw_holes_enabled,
        "screw_diameter_mm": settings.screw_diameter_mm,
        "stacking_lip_enabled": settings.stacking_lip_enabled,
        "gridfinity_height_snap": settings.gridfinity_height_snap,
    }


def _generation_settings_from_dict(data: dict | None) -> GenerationSettings:
    payload = data or {}
    return GenerationSettings(
        height_mode=str(payload.get("height_mode", "auto")),
        manual_height_mm=_optional_float(payload.get("manual_height_mm")),
        minimum_floor_mm=float(payload.get("minimum_floor_mm", 2.0)),
        minimum_wall_mm=float(payload.get("minimum_wall_mm", 2.0)),
        scoops_enabled=bool(payload.get("scoops_enabled", True)),
        tool_scoop_modes={
            str(tool_id): str(mode)
            for tool_id, mode in dict(payload.get("tool_scoop_modes", {})).items()
        },
        magnets_enabled=bool(payload.get("magnets_enabled", True)),
        magnet_diameter_mm=float(payload.get("magnet_diameter_mm", 6.0)),
        magnet_depth_mm=float(payload.get("magnet_depth_mm", 2.0)),
        screw_holes_enabled=bool(payload.get("screw_holes_enabled", False)),
        screw_diameter_mm=float(payload.get("screw_diameter_mm", 3.2)),
        stacking_lip_enabled=bool(payload.get("stacking_lip_enabled", True)),
        gridfinity_height_snap=bool(payload.get("gridfinity_height_snap", True)),
    )


def _generation_state_to_dict(state: GenerationState) -> dict:
    return {
        "last_generated_fingerprint": state.last_generated_fingerprint,
        "last_generated_height_mm": state.last_generated_height_mm,
        "review_required": state.review_required,
    }


def _generation_state_from_dict(data: dict | None) -> GenerationState:
    payload = data or {}
    fingerprint = payload.get("last_generated_fingerprint")
    return GenerationState(
        last_generated_fingerprint=(None if fingerprint is None else str(fingerprint)),
        last_generated_height_mm=_optional_float(payload.get("last_generated_height_mm")),
        review_required=bool(payload.get("review_required", True)),
    )


def _project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "schema_version": project.schema_version,
        "default_exposed_height_mm": project.default_exposed_height_mm,
        "default_bottom_clearance_mm": project.default_bottom_clearance_mm,
        "default_layout_spacing_mm": project.default_layout_spacing_mm,
        "default_layout_border_mm": project.default_layout_border_mm,
        "default_grab_clearance_mm": project.default_grab_clearance_mm,
        "default_snap_increment_mm": project.default_snap_increment_mm,
        "gridfinity_pitch_mm": project.gridfinity_pitch_mm,
        "layout": _layout_to_dict(project.layout),
        "generation_settings": _generation_settings_to_dict(project.generation_settings),
        "generation_state": _generation_state_to_dict(project.generation_state),
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
                pocket_depth_override_mm=_optional_float(
                    item.get("pocket_depth_override_mm")
                ),
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
        default_layout_spacing_mm=float(data.get("default_layout_spacing_mm", 3.0)),
        default_layout_border_mm=float(data.get("default_layout_border_mm", 4.0)),
        default_grab_clearance_mm=float(data.get("default_grab_clearance_mm", 12.0)),
        default_snap_increment_mm=float(data.get("default_snap_increment_mm", 1.0)),
        gridfinity_pitch_mm=float(data.get("gridfinity_pitch_mm", 42.0)),
        layout=_layout_from_dict(data.get("layout")),
        generation_settings=_generation_settings_from_dict(
            data.get("generation_settings")
        ),
        generation_state=_generation_state_from_dict(data.get("generation_state")),
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
