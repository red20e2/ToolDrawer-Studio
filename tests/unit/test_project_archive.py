import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from tooldrawer_studio.domain.models import CaptureAsset, Point2D, Project, ToolObject
from tooldrawer_studio.persistence.project_archive import ProjectBundle, load_project, save_project


def test_tds_round_trip_preserves_base_and_edited_contours(tmp_path: Path):
    capture = CaptureAsset("capture-1", "tool.png", 100, 80, "images/capture-1.png")
    raw = [Point2D(0, 0), Point2D(20, 0), Point2D(20, 10), Point2D(0, 10)]
    edited = [Point2D(0, 0), Point2D(22, 0), Point2D(22, 10), Point2D(0, 10)]
    tool = ToolObject(id="tool-1", name="Pliers", source_capture_id="capture-1", base_contour_mm=raw, contour_mm=edited, clearance_mm=0.7, depth_mm=9.0, trace_confidence=0.88)
    bundle = ProjectBundle(project=Project(id="project-1", name="Test", captures=[capture], tools=[tool]), image_bytes={"capture-1": b"fake-png-bytes"})
    path = tmp_path / "test.tds"
    save_project(bundle, path)
    reopened = load_project(path)
    assert reopened.project.schema_version == 1
    assert reopened.project.tools[0].base_contour_mm[1] == Point2D(20, 0)
    assert reopened.project.tools[0].contour_mm[1] == Point2D(22, 0)
    assert reopened.image_bytes["capture-1"] == b"fake-png-bytes"


def test_tds_rejects_unsafe_archive_member(tmp_path: Path):
    path = tmp_path / "unsafe.tds"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"format": "tooldrawer-studio", "schema_version": 1}))
        archive.writestr("project.json", json.dumps({"id": "p", "name": "P", "schema_version": 1, "captures": [], "calibrations": [], "tools": []}))
        archive.writestr("../escape.txt", b"nope")
    with pytest.raises(ValueError, match="Unsafe archive path"):
        load_project(path)


def test_tds_rejects_unsupported_schema(tmp_path: Path):
    path = tmp_path / "future.tds"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"format": "tooldrawer-studio", "schema_version": 2}))
        archive.writestr("project.json", "{}")
    with pytest.raises(ValueError, match="Unsupported project schema version: 2"):
        load_project(path)
