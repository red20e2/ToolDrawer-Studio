import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cadquery as cq
import numpy as np
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.ui.model_preview import ModelPreview


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_preview_tessellates_cadquery_solid_to_triangle_arrays():
    app = _app()
    preview = ModelPreview()
    preview.set_model(cq.Workplane("XY").box(20.0, 10.0, 5.0))
    assert preview.vertices.ndim == 2
    assert preview.vertices.shape[1] == 3
    assert preview.triangles.ndim == 2
    assert preview.triangles.shape[1] == 3
    assert preview.vertices.shape[0] >= 8
    assert preview.triangles.shape[0] >= 12
    preview.close()
    assert app is not None


def test_preview_centers_model_and_reset_view_is_deterministic():
    preview = ModelPreview()
    preview.set_model(cq.Workplane("XY").box(20.0, 10.0, 5.0, centered=False))
    center = (preview.vertices.min(axis=0) + preview.vertices.max(axis=0)) / 2.0
    assert np.allclose(center, np.zeros(3), atol=1e-6)
    first = (preview.yaw_deg, preview.pitch_deg, preview.zoom, tuple(preview.pan))
    preview.yaw_deg = 0.0
    preview.pitch_deg = 0.0
    preview.zoom = 3.0
    preview.pan[:] = 5.0
    preview.reset_view()
    second = (preview.yaw_deg, preview.pitch_deg, preview.zoom, tuple(preview.pan))
    assert first == second
    preview.close()


def test_clear_model_removes_geometry():
    preview = ModelPreview()
    preview.set_model(cq.Workplane("XY").box(5.0, 5.0, 5.0))
    preview.clear_model()
    assert preview.vertices.size == 0
    assert preview.triangles.size == 0
    preview.close()
