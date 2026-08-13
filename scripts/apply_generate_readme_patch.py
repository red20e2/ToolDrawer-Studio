from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = README.read_text(encoding="utf-8")
    if "## Generate / manufacturing workflow" in text:
        print("readme-already-patched")
        return

    text = replace_once(
        text,
        "The current V0.1 foundation includes the dimensional core: import or capture source photos, calibrate pixels to millimetres, trace one or more tool silhouettes, refine contours without destroying the base trace, measure physical tool thickness from an independently calibrated side view, arrange calibrated tool cavities inside foam/drawer or Gridfinity boundaries, derive a pocket-depth suggestion, save/reopen editable `.tds` projects, generate a parametric pocket, and export STEP/STL/DXF manufacturing geometry.",
        "The current V0.1 foundation now covers the complete manufacturing path: import or capture source photos, calibrate pixels to millimetres, trace and refine tool silhouettes, measure physical tool thickness from an independently calibrated side view, arrange real cleared cavity contours inside foam/drawer or Gridfinity boundaries, generate a validated multi-tool organizer solid with per-tool pocket depths and removal access, preview it in 3D, save/reopen editable `.tds` projects, and export the complete organizer as STEP, STL, and DXF.",
        "V0.1 summary",
    )

    text = replace_once(
        text,
        "Measure state was introduced in `.tds` schema V2 and remains preserved in the current V3 format. Existing V1 projects migrate non-destructively through V2 to V3: the old `depth_mm` value is preserved exactly as the explicit pocket-depth override. Reopening a project restores saved Measure state without automatically rerunning image analysis.",
        "Measure state was introduced in `.tds` schema V2 and remains preserved in the current V4 format. Existing V1 projects migrate non-destructively through V2, V3, and V4: the old `depth_mm` value is preserved exactly as the explicit pocket-depth override. Reopening a project restores saved Measure state without automatically rerunning image analysis or organizer generation.",
        "Measure schema text",
    )

    text = replace_once(
        text,
        "Grab side may be none, left, right, top, or bottom. The selected side rotates with the tool. Grab clearance is a layout exclusion rule; it does not create finger-scoop CAD or mutate the source contour.",
        "Grab side may be none, left, right, top, or bottom. The selected side rotates with the tool. Arrange reserves that access region without mutating the source contour; the Generate stage later converts the saved grab-side intent into optional rounded finger-scoop CAD.",
        "Arrange grab text",
    )

    text = replace_once(
        text,
        "`.tds` schema V3 persists Arrange defaults, boundary settings, every tool placement, rotation policy, lock state, grab-side settings, explicit unplaced tools, and review-required state. V2 projects migrate to V3 non-destructively with no invented layout. Opening a saved project restores the exact saved placement state and never automatically repacks it.\n\nArrange validates 2D layout geometry only. Final foam/Gridfinity solid generation remains responsible for confirming that the requested wall, base, and manufacturing geometry can actually be produced.",
        "`.tds` schema V4 preserves all V3 Arrange state: defaults, boundary settings, every tool placement, rotation policy, lock state, grab-side settings, explicit unplaced tools, and review-required state. V2 projects migrate through V3 to V4 non-destructively with no invented layout. Opening a saved project restores the exact saved placement state and never automatically repacks it.\n\nArrange validates 2D layout geometry only. The Generate stage consumes that exact state and performs the separate 3D manufacturing checks described below.",
        "Arrange schema/final text",
    )

    generate_section = r'''## Generate / manufacturing workflow

The **Generate** stage is the manufacturing authority for the complete organizer. It never moves tools, changes Arrange rotation, reduces layout spacing, changes a resolved Measure pocket depth, or silently weakens a wall/floor requirement to make a model succeed.

Generation is explicit. Editing an upstream contour, tool clearance, resolved depth, placement, rotation, grab side, organizer boundary, or generation setting marks the previous result stale. The saved project keeps the recipe and currentness metadata, not a serialized BREP/STL as project authority. Reopening a `.tds` project therefore never silently regenerates CAD; press **Generate Organizer** when the project is ready.

### Common manufacturing settings

Defaults are:

- height mode: **Automatic**;
- minimum floor: **2.0 mm**;
- minimum wall: **2.0 mm**;
- finger scoops: **enabled**;
- per-tool scoop mode: **Auto** or **Off**.

For foam/drawer mode, automatic body height is the deepest resolved pocket plus the required minimum floor. Manual height is exact and is rejected when it cannot satisfy the current cavities/features. Every placed tool is cut from the organizer top by its own resolved Measure depth, so one organizer may contain many different pocket depths.

Finger scoops use the saved Arrange grab side. Their direction rotates with the tool. Automatic scoops may shrink deterministically to preserve the boundary, minimum wall, and minimum floor, but the application never relaxes those manufacturing limits to preserve a scoop.

### Full-featured Gridfinity generation

Gridfinity generation is parametric CadQuery geometry, not an imported STL. V0.1 pins its compatibility profile to the approved Gridfinity baseline used by the design spec:

- grid pitch: **42.0 mm**;
- nominal top footprint per 1U cell: **41.5 mm**;
- vertical unit: **7.0 mm**;
- base profile height: **4.75 mm**;
- magnets: **6.0 mm diameter x 2.0 mm deep**, enabled by default;
- M3 screw passages: optional, default clearance diameter **3.2 mm**;
- stacking lip: enabled by default;
- automatic height snapping: upward to the next **7 mm** unit by default.

The organizer remains one continuous body across all selected cells, so a ratchet, wrench, or other tool cavity may cross nominal cell boundaries. Multi-cell magnet/screw locations are deduplicated deterministically.

Tool fit and removal access take precedence over the top stacking lip. If a cavity conflicts only with the stacking-lip region, Generate can omit that local lip segment and report a warning. Magnet/screw/base-profile conflicts that would violate required material are hard errors.

### Manufacturing validation

Hard errors block generation/export. Checks include:

- Arrange layout missing, stale, invalid, or containing unplaced tools;
- unresolved or review-required pocket depths;
- invalid/non-finite contours or depths;
- insufficient organizer height or floor;
- insufficient wall material at the organizer edge or between cavities;
- cavity or scoop boundary breakout;
- invalid Gridfinity magnet/screw/base interactions;
- CadQuery/OpenCascade failure, empty output, or a final result that is not one valid solid.

Warnings do not block output. Examples include near-limit but still valid walls, a scoop that had to shrink, or a stacking-lip segment omitted for tool access. User-facing messages identify the affected tool/feature instead of exposing a raw CAD-kernel exception as the primary explanation.

### 3D preview and manufacturing export

After a successful explicit Generate action, Stage 5 shows the tessellated organizer in an orbit/pan/zoom Qt preview. The preview adds no separate 3D runtime dependency; it uses the existing CadQuery solid plus PySide6 and NumPy.

Stage 6 keeps editable project saving separate from manufacturing output and offers:

- **Export STEP** - complete BREP organizer for CAD/CNC interchange;
- **Export STL** - complete printable organizer mesh;
- **Export DXF** - top/profile manufacturing representation with an outer-boundary layer plus deterministic cavity layers;
- **Export All** - all three formats.

Manufacturing export is refused when the generated result is missing or stale. Saving the editable `.tds` project remains independent of export.

### `.tds` schema V4

Schema V4 adds persistent generation settings plus generation currentness/review metadata while preserving all prior captures, calibrations, contours, Measure data, and Arrange placements. V3 projects migrate to V4 without generating a model or moving tools. V1 and V2 continue through the existing non-destructive migration chain.

'''
    text = replace_once(
        text,
        "## Image import safety\n",
        generate_section + "## Image import safety\n",
        "Generate section insertion",
    )

    README.write_text(text, encoding="utf-8")
    print("readme-patched")


if __name__ == "__main__":
    main()
