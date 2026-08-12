import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from tooldrawer_studio.domain.models import CaptureAsset, Point2D, Project, ToolObject
from tooldrawer_studio.measurement.models import ImagePoint
from tooldrawer_studio.persistence.project_archive import ProjectBundle, load_project, save_project


def _write_v1_archive(path: Path, depth_mm: float) -> None:
    payload = {
        "id": "legacy-project",
        "name": "Legacy",
        "schema_version": 1,
        "captures": [],
        "calibrations": [],
        "tools": [
            {
                "id": "legacy-tool",
                "name": "Legacy Tool",
                "source_capture_id": "legacy-capture",
                "base_contour_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 5.0},
                ],
                "contour_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 5.0},
                ],
                "clearance_mm": 0.6,
                "depth_mm": depth_mm,
                "trace_confidence": 0.8,
            }
        ],
    }
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "tooldrawer-studio", "schema_version": 1}),
        )
        archive.writestr("project.json", json.dumps(payload))


def test_tds_v1_migrates_depth_exactly_to_v2_override(tmp_path: Path):
    path = tmp_path / "legacy.tds"
    _write_v1_archive(path, 9.375)

    reopened = load_project(path)
    tool = reopened.project.tools[0]

    assert reopened.project.schema_version == 2
    assert reopened.project.default_exposed_height_mm == 4.0
    assert reopened.project.default_bottom_clearance_mm == 0.8
    assert tool.pocket_depth_override_mm == pytest.approx(9.375)
    assert tool.side_view_capture_id is None
    assert tool.accepted_thickness_mm is None
    assert tool.thickness_measurement_mode == "none"


def test_tds_round_trip_preserves_base_and_edited_contours(tmp_path: Path):
    capture = CaptureAsset("capture-1", "tool.png", 100, 80, "images/capture-1.png")
    raw = [Point2D(0, 0), Point2D(20, 0), Point2D(20, 10), Point2D(0, 10)]
    edited = [Point2D(0, 0), Point2D(22, 0), Point2D(22, 10), Point2D(0, 10)]
    tool = ToolObject(
        id="tool-1",
        name="Pliers",
        source_capture_id="capture-1",
        base_contour_mm=raw,
        contour_mm=edited,
        clearance_mm=0.7,
        trace_confidence=0.88,
        pocket_depth_override_mm=9.0,
    )
    bundle = ProjectBundle(
        project=Project(id="project-1", name="Test", captures=[capture], tools=[tool]),
        image_bytes={"capture-1": b"fake-png-bytes"},
    )
    path = tmp_path / "test.tds"

    save_project(bundle, path)
    reopened = load_project(path)

    assert reopened.project.schema_version == 2
    assert reopened.project.tools[0].base_contour_mm[1] == Point2D(20, 0)
    assert reopened.project.tools[0].contour_mm[1] == Point2D(22, 0)
    assert reopened.project.tools[0].pocket_depth_override_mm == pytest.approx(9.0)
    assert reopened.image_bytes["capture-1"] == b"fake-png-bytes"


def test_tds_v2_round_trip_preserves_measurement_state(tmp_path: Path):
    top = CaptureAsset("capture-1", "top.png", 100, 80, "images/capture-1.png")
    side = CaptureAsset("capture-2", "side.png", 120, 90, "images/capture-2.png")
    contour = [Point2D(0, 0), Point2D(20, 0), Point2D(20, 10), Point2D(0, 10)]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        trace_confidence=0.92,
        side_view_capture_id="capture-2",
        automatic_thickness_mm=20.0,
        automatic_thickness_confidence=0.91,
        automatic_thickness_endpoint_a_px=ImagePoint(10.0, 20.0),
        automatic_thickness_endpoint_b_px=ImagePoint(10.0, 60.0),
        corrected_thickness_endpoint_a_px=ImagePoint(12.0, 21.0),
        corrected_thickness_endpoint_b_px=ImagePoint(12.0, 59.0),
        side_view_silhouette_px=[
            ImagePoint(5.0, 5.0),
            ImagePoint(20.0, 5.0),
            ImagePoint(20.0, 70.0),
            ImagePoint(5.0, 70.0),
        ],
        accepted_thickness_mm=19.0,
        thickness_measurement_mode="endpoints",
        thickness_accepted=True,
        exposed_height_override_mm=3.0,
        bottom_clearance_override_mm=1.0,
        pocket_depth_override_mm=17.0,
        thickness_review_required=True,
    )
    project = Project(
        id="project-1",
        name="Measured",
        captures=[top, side],
        tools=[tool],
        default_exposed_height_mm=4.5,
        default_bottom_clearance_mm=0.9,
    )
    bundle = ProjectBundle(
        project=project,
        image_bytes={"capture-1": b"top-bytes", "capture-2": b"side-bytes"},
    )
    path = tmp_path / "measured.tds"

    save_project(bundle, path)
    reopened = load_project(path)
    saved = reopened.project.tools[0]

    assert reopened.project.default_exposed_height_mm == pytest.approx(4.5)
    assert reopened.project.default_bottom_clearance_mm == pytest.approx(0.9)
    assert saved.side_view_capture_id == "capture-2"
    assert saved.automatic_thickness_mm == pytest.approx(20.0)
    assert saved.automatic_thickness_confidence == pytest.approx(0.91)
    assert saved.automatic_thickness_endpoint_a_px == ImagePoint(10.0, 20.0)
    assert saved.automatic_thickness_endpoint_b_px == ImagePoint(10.0, 60.0)
    assert saved.corrected_thickness_endpoint_a_px == ImagePoint(12.0, 21.0)
    assert saved.corrected_thickness_endpoint_b_px == ImagePoint(12.0, 59.0)
    assert saved.side_view_silhouette_px == tool.side_view_silhouette_px
    assert saved.accepted_thickness_mm == pytest.approx(19.0)
    assert saved.thickness_measurement_mode == "endpoints"
    assert saved.thickness_accepted is True
    assert saved.exposed_height_override_mm == pytest.approx(3.0)
    assert saved.bottom_clearance_override_mm == pytest.approx(1.0)
    assert saved.pocket_depth_override_mm == pytest.approx(17.0)
    assert saved.thickness_review_required is True
    assert reopened.image_bytes == bundle.image_bytes


def test_tds_rejects_unsafe_archive_member(tmp_path: Path):
    path = tmp_path / "unsafe.tds"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "tooldrawer-studio", "schema_version": 1}),
        )
        archive.writestr(
            "project.json",
            json.dumps(
                {
                    "id": "p",
                    "name": "P",
                    "schema_version": 1,
                    "captures": [],
                    "calibrations": [],
                    "tools": [],
                }
            ),
        )
        archive.writestr("../escape.txt", b"nope")

    with pytest.raises(ValueError, match="Unsafe archive path"):
        load_project(path)


def test_tds_rejects_future_schema(tmp_path: Path):
    path = tmp_path / "future.tds"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "tooldrawer-studio", "schema_version": 3}),
        )
        archive.writestr("project.json", "{}")

    with pytest.raises(ValueError, match="Unsupported project schema version: 3"):
        load_project(path)
