from __future__ import annotations

import pytest

from tooldrawer_studio.domain.models import Project


def _state_api():
    try:
        from tooldrawer_studio.project_state import ProjectEditTracker, editable_project_digest
    except ModuleNotFoundError:
        pytest.fail("project state tracking is not implemented")
    return ProjectEditTracker, editable_project_digest


def test_editable_digest_ignores_derived_generation_state():
    _tracker, digest = _state_api()
    project = Project(id="project-1", name="Drawer")
    original = digest(project)
    project.generation_state.review_required = False
    project.generation_state.last_generated_fingerprint = "generated-result"
    assert digest(project) == original
    project.generation_settings.minimum_floor_mm = 2.5
    assert digest(project) != original


def test_tracker_resets_saved_baseline():
    ProjectEditTracker, _digest = _state_api()
    project = Project(id="project-1", name="Drawer")
    tracker = ProjectEditTracker(project)
    assert tracker.has_unsaved_changes() is False
    project.name = "Drawer revised"
    assert tracker.has_unsaved_changes() is True
    tracker.mark_saved()
    assert tracker.has_unsaved_changes() is False
