from __future__ import annotations

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.persistence.migrations import CURRENT_SCHEMA_VERSION, migrate_project_dict


def _minimal_v2_project() -> dict:
    return {
        "id": "project-v2",
        "name": "Existing measured project",
        "schema_version": 2,
        "default_exposed_height_mm": 4.5,
        "default_bottom_clearance_mm": 0.9,
        "captures": [],
        "calibrations": [],
        "tools": [
            {
                "id": "tool-1",
                "name": "Ratchet",
                "source_capture_id": "capture-1",
                "base_contour_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 20.0, "y_mm": 0.0},
                    {"x_mm": 20.0, "y_mm": 10.0},
                ],
                "contour_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 20.0, "y_mm": 0.0},
                    {"x_mm": 20.0, "y_mm": 10.0},
                ],
                "clearance_mm": 0.7,
                "trace_confidence": 0.92,
                "side_view_capture_id": None,
                "automatic_thickness_mm": 20.0,
                "automatic_thickness_confidence": 0.91,
                "automatic_thickness_endpoint_a_px": None,
                "automatic_thickness_endpoint_b_px": None,
                "corrected_thickness_endpoint_a_px": None,
                "corrected_thickness_endpoint_b_px": None,
                "side_view_silhouette_px": [],
                "accepted_thickness_mm": 19.0,
                "thickness_measurement_mode": "manual",
                "thickness_accepted": True,
                "exposed_height_override_mm": 3.0,
                "bottom_clearance_override_mm": 1.0,
                "pocket_depth_override_mm": 17.0,
                "thickness_review_required": True,
            }
        ],
    }


def test_current_schema_version_is_four_for_generate_state():
    assert CURRENT_SCHEMA_VERSION == 4


def test_new_project_has_arrange_and_generate_defaults_without_inventing_a_layout():
    project = Project(id="p", name="P")

    assert project.schema_version == 4
    assert project.default_layout_spacing_mm == 3.0
    assert project.default_layout_border_mm == 4.0
    assert project.default_grab_clearance_mm == 12.0
    assert project.default_snap_increment_mm == 1.0
    assert project.gridfinity_pitch_mm == 42.0
    assert project.layout is None
    assert project.generation_settings.minimum_floor_mm == 2.0
    assert project.generation_settings.minimum_wall_mm == 2.0
    assert project.generation_state.last_generated_fingerprint is None
    assert project.generation_state.review_required is True


def test_v2_migration_preserves_measure_state_and_adds_arrange_and_generate_defaults():
    original = _minimal_v2_project()
    original_tool = dict(original["tools"][0])

    migrated = migrate_project_dict(original, 2)

    assert migrated["schema_version"] == 4
    assert migrated["default_exposed_height_mm"] == 4.5
    assert migrated["default_bottom_clearance_mm"] == 0.9
    assert migrated["default_layout_spacing_mm"] == 3.0
    assert migrated["default_layout_border_mm"] == 4.0
    assert migrated["default_grab_clearance_mm"] == 12.0
    assert migrated["default_snap_increment_mm"] == 1.0
    assert migrated["gridfinity_pitch_mm"] == 42.0
    assert migrated["layout"] is None
    assert migrated["generation_settings"]["minimum_floor_mm"] == 2.0
    assert migrated["generation_settings"]["minimum_wall_mm"] == 2.0
    assert migrated["generation_state"]["last_generated_fingerprint"] is None
    assert migrated["generation_state"]["review_required"] is True
    assert migrated["tools"][0] == original_tool
