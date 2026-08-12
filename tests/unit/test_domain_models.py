from tooldrawer_studio.domain.models import Point2D, Project, ToolObject


def test_project_starts_with_schema_version_one_and_preserves_base_trace():
    raw = [Point2D(0.0, 0.0), Point2D(50.0, 0.0), Point2D(50.0, 20.0)]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id="capture-1",
        base_contour_mm=list(raw),
        contour_mm=list(raw),
        clearance_mm=0.6,
        depth_mm=8.0,
        trace_confidence=0.9,
    )
    tool.contour_mm[1] = Point2D(52.0, 0.0)
    project = Project(id="project-1", name="Drawer A", tools=[tool])

    assert project.schema_version == 1
    assert project.tools[0].name == "Ratchet"
    assert project.tools[0].base_contour_mm[1].x_mm == 50.0
    assert project.tools[0].contour_mm[1].x_mm == 52.0
