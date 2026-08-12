from tooldrawer_studio.domain.models import Point2D, Project, ToolObject


def _measurement_tool() -> ToolObject:
    raw = [
        Point2D(0.0, 0.0),
        Point2D(50.0, 0.0),
        Point2D(50.0, 20.0),
    ]
    return ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="capture-1",
        base_contour_mm=list(raw),
        contour_mm=list(raw),
        clearance_mm=0.6,
        trace_confidence=0.9,
    )


def test_project_starts_with_schema_version_three_and_measurement_layout_defaults():
    project = Project(id="project-1", name="Drawer A")

    assert project.schema_version == 3
    assert project.default_exposed_height_mm == 4.0
    assert project.default_bottom_clearance_mm == 0.8
    assert project.default_layout_spacing_mm == 3.0
    assert project.default_layout_border_mm == 4.0
    assert project.default_grab_clearance_mm == 12.0
    assert project.default_snap_increment_mm == 1.0
    assert project.gridfinity_pitch_mm == 42.0
    assert project.layout is None


def test_new_tool_has_no_measurement_or_pocket_override():
    tool = _measurement_tool()

    assert tool.side_view_capture_id is None
    assert tool.accepted_thickness_mm is None
    assert tool.thickness_measurement_mode == "none"
    assert tool.pocket_depth_override_mm is None


def test_editing_contour_preserves_independent_base_trace():
    tool = _measurement_tool()
    tool.contour_mm[1] = Point2D(52.0, 0.0)
    project = Project(id="project-1", name="Drawer A", tools=[tool])

    assert project.tools[0].name == "Ratchet"
    assert project.tools[0].base_contour_mm[1].x_mm == 50.0
    assert project.tools[0].contour_mm[1].x_mm == 52.0
