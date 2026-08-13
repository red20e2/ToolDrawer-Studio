import math

import pytest

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.generation.models import GenerationSettings, GenerationState
from tooldrawer_studio.persistence.migrations import migrate_project_dict


def _minimal_project_dict(version: int) -> dict:
    return {
        "id": "project-1",
        "name": "Drawer",
        "schema_version": version,
        "captures": [],
        "calibrations": [],
        "tools": [],
    }


def test_generation_defaults_are_manufacturing_safe():
    settings = GenerationSettings()
    state = GenerationState()

    assert settings.height_mode == "auto"
    assert settings.manual_height_mm is None
    assert settings.minimum_floor_mm == 2.0
    assert settings.minimum_wall_mm == 2.0
    assert settings.scoops_enabled is True
    assert settings.tool_scoop_modes == {}
    assert settings.magnets_enabled is True
    assert settings.magnet_diameter_mm == 6.0
    assert settings.magnet_depth_mm == 2.0
    assert settings.screw_holes_enabled is False
    assert settings.screw_diameter_mm == 3.2
    assert settings.stacking_lip_enabled is True
    assert settings.gridfinity_height_snap is True
    assert state.last_generated_fingerprint is None
    assert state.last_generated_height_mm is None
    assert state.review_required is True


def test_generation_settings_reject_negative_floor():
    with pytest.raises(ValueError, match="minimum_floor_mm"):
        GenerationSettings(minimum_floor_mm=-0.001)


def test_generation_settings_reject_nonpositive_magnet_diameter():
    with pytest.raises(ValueError, match="magnet_diameter_mm"):
        GenerationSettings(magnet_diameter_mm=0.0)


def test_generation_settings_reject_nonfinite_values():
    with pytest.raises(ValueError, match="minimum_wall_mm"):
        GenerationSettings(minimum_wall_mm=math.inf)


def test_generation_settings_reject_unknown_modes():
    with pytest.raises(ValueError, match="height_mode"):
        GenerationSettings(height_mode="guess")
    with pytest.raises(ValueError, match="tool_scoop_modes"):
        GenerationSettings(tool_scoop_modes={"tool-1": "maybe"})


def test_v3_migrates_to_v4_without_inventing_generated_model():
    original = _minimal_project_dict(3)
    original.update(
        {
            "default_exposed_height_mm": 4.0,
            "default_bottom_clearance_mm": 0.8,
            "default_layout_spacing_mm": 3.0,
            "default_layout_border_mm": 4.0,
            "default_grab_clearance_mm": 12.0,
            "default_snap_increment_mm": 1.0,
            "gridfinity_pitch_mm": 42.0,
            "layout": None,
        }
    )

    migrated = migrate_project_dict(original, 3)

    assert migrated["schema_version"] == 4
    assert migrated["generation_settings"]["minimum_floor_mm"] == 2.0
    assert migrated["generation_settings"]["minimum_wall_mm"] == 2.0
    assert migrated["generation_state"]["last_generated_fingerprint"] is None
    assert migrated["generation_state"]["last_generated_height_mm"] is None
    assert migrated["generation_state"]["review_required"] is True
    assert migrated["layout"] is None
    assert migrated["tools"] == original["tools"]


def test_v1_migrates_through_v4():
    migrated = migrate_project_dict(_minimal_project_dict(1), 1)
    assert migrated["schema_version"] == 4
    assert migrated["layout"] is None
    assert migrated["generation_state"]["review_required"] is True


def test_project_defaults_to_schema_v4_generation_state():
    project = Project(id="project-1", name="Drawer")
    assert project.schema_version == 4
    assert project.generation_settings.minimum_floor_mm == 2.0
    assert project.generation_state.review_required is True


def test_future_schema_remains_rejected():
    with pytest.raises(ValueError, match="Unsupported project schema version: 5"):
        migrate_project_dict(_minimal_project_dict(5), 5)
