from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.generation.cavities import build_cavity_cutter
from tooldrawer_studio.generation.fingerprint import (
    generation_fingerprint,
    resolve_body_height_mm,
)
from tooldrawer_studio.generation.foam import build_foam_body
from tooldrawer_studio.generation.gridfinity import (
    apply_stacking_lip_omissions,
    build_gridfinity_body,
    gridfinity_feature_cutters,
)
from tooldrawer_studio.generation.models import GenerationIssue
from tooldrawer_studio.generation.scoops import build_scoop_cutter
from tooldrawer_studio.generation.validation import validate_generation
from tooldrawer_studio.layout.models import ToolPlacement
from tooldrawer_studio.measurement.depth import final_pocket_depth_mm


@dataclass(frozen=True, slots=True)
class GenerationResult:
    model: cq.Workplane
    fingerprint: str
    body_height_mm: float
    warnings: tuple[GenerationIssue, ...] = ()


class GenerationBlockedError(ValueError):
    def __init__(self, issues: tuple[GenerationIssue, ...]) -> None:
        self.issues = issues
        messages = [issue.message for issue in issues if issue.severity == "error"]
        super().__init__(messages[0] if messages else "Organizer generation is blocked")


class GenerationBuildError(RuntimeError):
    pass


def placed_tool_depths(
    project: Project,
) -> tuple[tuple[ToolObject, ToolPlacement, float], ...]:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout first")
    tools = {tool.id: tool for tool in project.tools}
    result: list[tuple[ToolObject, ToolPlacement, float]] = []
    for placement in sorted(layout.placements, key=lambda item: item.tool_id):
        if not placement.is_placed:
            continue
        tool = tools.get(placement.tool_id)
        if tool is None:
            raise ValueError(f"Placement references missing tool: {placement.tool_id}")
        depth = final_pocket_depth_mm(project, tool)
        if depth is None:
            raise ValueError(f"{tool.name} has no resolved pocket depth")
        result.append((tool, placement, float(depth)))
    return tuple(result)


def _dedupe_warnings(issues: list[GenerationIssue]) -> tuple[GenerationIssue, ...]:
    by_key: dict[tuple[str, tuple[str, ...]], GenerationIssue] = {}
    for issue in issues:
        key = (issue.code, issue.tool_ids)
        by_key[key] = issue
    return tuple(
        sorted(
            by_key.values(),
            key=lambda issue: (issue.code, issue.tool_ids, issue.message),
        )
    )


def _assert_valid_single_solid(model: cq.Workplane) -> None:
    solids = model.solids().vals()
    if len(solids) != 1:
        raise ValueError(f"Generated organizer must be one solid; found {len(solids)}")
    if not solids[0].isValid():
        raise ValueError("Generated organizer is not a valid CAD solid")


def generate_organizer(project: Project) -> GenerationResult:
    layout = project.layout
    if layout is None:
        raise GenerationBlockedError(
            (GenerationIssue("layout_missing", "Configure an Arrange layout before generating", "error"),)
        )

    height = resolve_body_height_mm(project)
    validation = validate_generation(project, height)
    if not validation.valid:
        raise GenerationBlockedError(validation.issues)

    warnings = [issue for issue in validation.issues if issue.severity == "warning"]
    try:
        if layout.mode == "foam":
            body = build_foam_body(layout, height)
        elif layout.mode == "gridfinity":
            body = build_gridfinity_body(layout, height, project.generation_settings)
            features = gridfinity_feature_cutters(
                layout,
                project.generation_settings,
                height,
            )
            for cutter in features.magnet_cutters:
                body = body.cut(cutter)
            for cutter in features.screw_cutters:
                body = body.cut(cutter)
            lip, lip_warnings = apply_stacking_lip_omissions(
                features.stacking_lip,
                project,
                height,
            )
            warnings.extend(features.warnings)
            warnings.extend(lip_warnings)
            if lip is not None:
                body = body.union(lip)
        else:
            raise ValueError(f"Unsupported layout mode: {layout.mode}")

        for tool, placement, depth in placed_tool_depths(project):
            body = body.cut(build_cavity_cutter(tool, placement, depth, height))
            scoop = build_scoop_cutter(
                tool,
                placement,
                layout,
                project.generation_settings,
                height,
                depth,
            )
            if scoop is not None:
                body = body.cut(scoop.cutter)

        body = body.clean()
        _assert_valid_single_solid(body)
    except GenerationBlockedError:
        raise
    except Exception as exc:
        raise GenerationBuildError(
            f"Could not build organizer CAD: {exc}"
        ) from exc

    return GenerationResult(
        model=body,
        fingerprint=generation_fingerprint(project),
        body_height_mm=height,
        warnings=_dedupe_warnings(warnings),
    )
