import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.layout.validation import LayoutValidationResult
from tooldrawer_studio.ui.arrangement_view import ArrangementView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _tool(tool_id: str, width: float = 20.0, height: float = 10.0) -> ToolObject:
    contour = [Point2D(0, 0), Point2D(width, 0), Point2D(width, height), Point2D(0, height)]
    return ToolObject(
        id=tool_id,
        name=tool_id,
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.5,
    )


def _fixture(*, snap: bool = False) -> tuple[Project, LayoutState]:
    layout = LayoutState(
        mode="gridfinity",
        grid_columns=4,
        grid_rows=3,
        grid_pitch_mm=42.0,
        border_mm=4.0,
        spacing_mm=3.0,
        snap_enabled=snap,
        snap_increment_mm=1.0,
        placements=[
            ToolPlacement(tool_id="a", x_mm=30.0, y_mm=30.0, is_placed=True),
            ToolPlacement(tool_id="b", x_mm=70.0, y_mm=40.0, is_placed=True),
        ],
    )
    return Project(id="p", name="P", tools=[_tool("a"), _tool("b")], layout=layout), layout


def test_model_scene_coordinate_conversion_keeps_lower_left_model_origin():
    app = _app()
    view = ArrangementView()
    project, layout = _fixture()
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))

    scene_point = view.model_to_scene(10.0, 20.0)
    model_point = view.scene_to_model(scene_point.x(), scene_point.y())

    assert scene_point.x() == 10.0
    assert scene_point.y() == layout.height_mm - 20.0
    assert model_point == (10.0, 20.0)
    view.close()
    assert app is not None


def test_gridfinity_lines_are_guides_and_do_not_force_unsnapped_move():
    view = ArrangementView()
    project, layout = _fixture(snap=False)
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))

    view.commit_translation(["a"], 7.3, 2.7)
    placement = view.placement("a")

    assert placement.x_mm == 37.3
    assert placement.y_mm == 32.7
    view.close()


def test_snap_enabled_applies_configured_increment():
    view = ArrangementView()
    project, layout = _fixture(snap=True)
    layout.snap_increment_mm = 1.0
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))

    view.commit_translation(["a"], 7.34, 2.66)
    placement = view.placement("a")

    assert placement.x_mm == 37.0
    assert placement.y_mm == 33.0
    view.close()


def test_locked_tool_cannot_be_transformed():
    view = ArrangementView()
    project, layout = _fixture()
    layout.placement_for("a").locked = True
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))

    try:
        view.commit_translation(["a"], 5.0, 0.0)
    except ValueError as exc:
        assert "locked" in str(exc).lower()
    else:
        raise AssertionError("locked translation should fail")
    view.close()


def test_orthogonal_rotation_snaps_and_fixed_rotation_rejects():
    view = ArrangementView()
    project, layout = _fixture()
    layout.placement_for("a").rotation_policy = "orthogonal"
    layout.placement_for("b").rotation_policy = "fixed"
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))

    view.commit_rotation(["a"], 47.0)
    assert view.placement("a").rotation_deg == 90.0

    try:
        view.commit_rotation(["b"], 30.0)
    except ValueError as exc:
        assert "fixed" in str(exc).lower()
    else:
        raise AssertionError("fixed rotation should fail")
    view.close()


def test_multi_translation_preserves_relative_offsets_and_one_undo_command():
    view = ArrangementView()
    project, layout = _fixture()
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))
    before_dx = view.placement("b").x_mm - view.placement("a").x_mm
    before_dy = view.placement("b").y_mm - view.placement("a").y_mm

    view.commit_translation(["a", "b"], 10.0, 5.0)

    assert view.placement("b").x_mm - view.placement("a").x_mm == before_dx
    assert view.placement("b").y_mm - view.placement("a").y_mm == before_dy
    assert view.undo_stack.count() == 1

    view.undo_stack.undo()
    assert view.placement("a").x_mm == 30.0
    assert view.placement("a").y_mm == 30.0
    assert view.placement("b").x_mm == 70.0
    assert view.placement("b").y_mm == 40.0
    view.close()


def test_committed_transform_emits_final_placement_values():
    view = ArrangementView()
    project, layout = _fixture()
    view.set_project_layout(project, layout, LayoutValidationResult(True, ()))
    emitted: list[object] = []
    view.placementsCommitted.connect(emitted.append)

    view.commit_translation(["a"], 5.0, 6.0)

    assert len(emitted) == 1
    payload = emitted[0]
    assert payload == [("a", 35.0, 36.0, 0.0)]
    view.close()
