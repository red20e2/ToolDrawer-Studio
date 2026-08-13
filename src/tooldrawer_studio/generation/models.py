from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal

HeightMode = Literal["auto", "manual"]
ScoopMode = Literal["auto", "off"]
GenerationSeverity = Literal["error", "warning"]


def _finite_nonnegative(value: float, name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return numeric


def _finite_positive(value: float, name: str) -> float:
    numeric = float(value)
    if not isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return numeric


@dataclass(slots=True)
class GenerationSettings:
    height_mode: HeightMode = "auto"
    manual_height_mm: float | None = None
    minimum_floor_mm: float = 2.0
    minimum_wall_mm: float = 2.0
    scoops_enabled: bool = True
    tool_scoop_modes: dict[str, ScoopMode] = field(default_factory=dict)
    magnets_enabled: bool = True
    magnet_diameter_mm: float = 6.0
    magnet_depth_mm: float = 2.0
    screw_holes_enabled: bool = False
    screw_diameter_mm: float = 3.2
    stacking_lip_enabled: bool = True
    gridfinity_height_snap: bool = True

    def __post_init__(self) -> None:
        if self.height_mode not in {"auto", "manual"}:
            raise ValueError("height_mode must be 'auto' or 'manual'")
        if self.manual_height_mm is not None:
            self.manual_height_mm = _finite_positive(
                self.manual_height_mm, "manual_height_mm"
            )
        self.minimum_floor_mm = _finite_nonnegative(
            self.minimum_floor_mm, "minimum_floor_mm"
        )
        self.minimum_wall_mm = _finite_nonnegative(
            self.minimum_wall_mm, "minimum_wall_mm"
        )
        normalized_modes: dict[str, ScoopMode] = {}
        for tool_id, mode in self.tool_scoop_modes.items():
            normalized_tool_id = str(tool_id)
            if not normalized_tool_id:
                raise ValueError("tool_scoop_modes keys must be non-empty tool ids")
            if mode not in {"auto", "off"}:
                raise ValueError("tool_scoop_modes values must be 'auto' or 'off'")
            normalized_modes[normalized_tool_id] = mode
        self.tool_scoop_modes = normalized_modes
        self.magnet_diameter_mm = _finite_positive(
            self.magnet_diameter_mm, "magnet_diameter_mm"
        )
        self.magnet_depth_mm = _finite_positive(
            self.magnet_depth_mm, "magnet_depth_mm"
        )
        self.screw_diameter_mm = _finite_positive(
            self.screw_diameter_mm, "screw_diameter_mm"
        )


@dataclass(slots=True)
class GenerationState:
    last_generated_fingerprint: str | None = None
    last_generated_height_mm: float | None = None
    review_required: bool = True

    def __post_init__(self) -> None:
        if self.last_generated_fingerprint is not None:
            self.last_generated_fingerprint = str(self.last_generated_fingerprint)
            if not self.last_generated_fingerprint:
                raise ValueError("last_generated_fingerprint must be non-empty")
        if self.last_generated_height_mm is not None:
            self.last_generated_height_mm = _finite_positive(
                self.last_generated_height_mm, "last_generated_height_mm"
            )
        self.review_required = bool(self.review_required)


@dataclass(frozen=True, slots=True)
class GenerationIssue:
    code: str
    message: str
    severity: GenerationSeverity
    tool_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning"}:
            raise ValueError("severity must be 'error' or 'warning'")


@dataclass(frozen=True, slots=True)
class GenerationValidationResult:
    valid: bool
    issues: tuple[GenerationIssue, ...]


def generation_settings_defaults_dict() -> dict[str, object]:
    return {
        "height_mode": "auto",
        "manual_height_mm": None,
        "minimum_floor_mm": 2.0,
        "minimum_wall_mm": 2.0,
        "scoops_enabled": True,
        "tool_scoop_modes": {},
        "magnets_enabled": True,
        "magnet_diameter_mm": 6.0,
        "magnet_depth_mm": 2.0,
        "screw_holes_enabled": False,
        "screw_diameter_mm": 3.2,
        "stacking_lip_enabled": True,
        "gridfinity_height_snap": True,
    }


def generation_state_defaults_dict() -> dict[str, object]:
    return {
        "last_generated_fingerprint": None,
        "last_generated_height_mm": None,
        "review_required": True,
    }
