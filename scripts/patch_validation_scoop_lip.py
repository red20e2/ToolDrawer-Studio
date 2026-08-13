from pathlib import Path

path = Path("src/tooldrawer_studio/generation/validation.py")
text = path.read_text(encoding="utf-8")
marker = '''                if scoop is not None and scoop.shrunk:
                    issues.append(
                        _warning(
                            "scoop_shrunk",
                            f"{tool.name} scoop was reduced to {scoop.width_mm:.3f} mm wide x {scoop.depth_mm:.3f} mm deep to preserve manufacturing limits",
                            tool_id,
                        )
                    )
'''
addition = marker + '''                if (
                    scoop is not None
                    and layout.mode == "gridfinity"
                    and settings.stacking_lip_enabled
                ):
                    scoop_bounds = scoop.cutter.val().BoundingBox()
                    scoop_xy = box(
                        scoop_bounds.xmin,
                        scoop_bounds.ymin,
                        scoop_bounds.xmax,
                        scoop_bounds.ymax,
                    )
                    if (
                        scoop_xy.intersection(stacking_lip_xy_zone(layout)).area
                        > _INTERSECTION_AREA_TOLERANCE
                    ):
                        already_reported = any(
                            issue.code == "stacking_lip_omitted"
                            and issue.tool_ids == (tool_id,)
                            for issue in issues
                        )
                        if not already_reported:
                            issues.append(
                                _warning(
                                    "stacking_lip_omitted",
                                    f"{tool.name} scoop overlaps the stacking-lip region; the conflicting lip segment will be omitted",
                                    tool_id,
                                )
                            )
'''
if addition in text:
    print("validation-scoop-lip-already-patched")
elif marker in text:
    path.write_text(text.replace(marker, addition, 1), encoding="utf-8")
    print("validation-scoop-lip-patched")
else:
    raise RuntimeError("Expected scoop warning block not found")
