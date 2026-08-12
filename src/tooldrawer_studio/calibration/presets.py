from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaperPreset:
    key: str
    label: str
    width_mm: float
    height_mm: float


A4 = PaperPreset("a4", "A4", 210.0, 297.0)
LETTER = PaperPreset("letter", "US Letter", 215.9, 279.4)
PAPER_PRESETS = {preset.key: preset for preset in (A4, LETTER)}
