from __future__ import annotations

from copy import deepcopy

CURRENT_SCHEMA_VERSION = 2


def _migrate_v1_to_v2(data: dict) -> dict:
    migrated = deepcopy(data)
    migrated["schema_version"] = 2
    migrated.setdefault("default_exposed_height_mm", 4.0)
    migrated.setdefault("default_bottom_clearance_mm", 0.8)
    for tool in migrated.get("tools", []):
        old_depth = float(tool.pop("depth_mm", 5.0))
        tool.setdefault("side_view_capture_id", None)
        tool.setdefault("automatic_thickness_mm", None)
        tool.setdefault("automatic_thickness_confidence", None)
        tool.setdefault("automatic_thickness_endpoint_a_px", None)
        tool.setdefault("automatic_thickness_endpoint_b_px", None)
        tool.setdefault("corrected_thickness_endpoint_a_px", None)
        tool.setdefault("corrected_thickness_endpoint_b_px", None)
        tool.setdefault("side_view_silhouette_px", [])
        tool.setdefault("accepted_thickness_mm", None)
        tool.setdefault("thickness_measurement_mode", "none")
        tool.setdefault("thickness_accepted", False)
        tool.setdefault("exposed_height_override_mm", None)
        tool.setdefault("bottom_clearance_override_mm", None)
        tool.setdefault("pocket_depth_override_mm", old_depth)
        tool.setdefault("thickness_review_required", False)
    return migrated


def migrate_project_dict(data: dict, from_version: int) -> dict:
    version = int(from_version)
    if version < 1 or version > CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {version}")
    payload_version = int(data.get("schema_version", 0))
    if payload_version != version:
        raise ValueError("Project schema version does not match manifest")
    migrated = deepcopy(data)
    if version == 1:
        migrated = _migrate_v1_to_v2(migrated)
        version = 2
    if version != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported project schema version: {version}")
    return migrated
