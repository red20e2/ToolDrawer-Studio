from __future__ import annotations

import json

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.persistence.project_archive import _project_to_dict


def editable_project_digest(project: Project) -> str:
    payload = _project_to_dict(project)
    payload.pop("generation_state", None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class ProjectEditTracker:
    def __init__(self, project: Project) -> None:
        self.project = project
        self._saved_digest = editable_project_digest(project)

    def mark_saved(self) -> None:
        self._saved_digest = editable_project_digest(self.project)

    def has_unsaved_changes(self) -> bool:
        return editable_project_digest(self.project) != self._saved_digest

    def replace_project(self, project: Project, *, mark_saved: bool = True) -> None:
        self.project = project
        if mark_saved:
            self.mark_saved()
