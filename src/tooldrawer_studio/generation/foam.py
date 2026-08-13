from __future__ import annotations

import math

import cadquery as cq

from tooldrawer_studio.layout.models import LayoutState


def build_foam_body(layout: LayoutState, body_height_mm: float) -> cq.Workplane:
    if layout.mode != "foam":
        raise ValueError("Foam body requires foam layout mode")
    height = float(body_height_mm)
    if not math.isfinite(height) or height <= 0.0:
        raise ValueError("body_height_mm must be finite and positive")
    return cq.Workplane("XY").box(
        layout.width_mm,
        layout.height_mm,
        height,
        centered=(False, False, False),
    )
