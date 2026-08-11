# ToolDrawer Studio Design Specification

**Date:** 2026-08-11  
**Status:** Approved design, pending written-spec review  
**Repository:** `red20e2/ToolDrawer-Studio`  
**License target:** GPL-3.0-or-later  
**Primary platform:** Windows desktop  

## 1. Product Vision

ToolDrawer Studio is an open-source, local-first Windows application for turning photographs of tools into reusable tool geometry and manufacturing-ready organizers.

The application combines photo calibration, multi-object tracing, manual contour refinement, depth capture, layout optimization, Gridfinity generation, foam/shadow-board generation, editable CAD, and manufacturing exports in one workflow.

The core application must remain fully usable offline, with no account requirement, project limit, export paywall, or mandatory paid API. Online features are optional enhancements rather than prerequisites.

The target user experience is:

`Capture -> Calibrate -> Detect -> Refine -> Measure -> Arrange -> Generate -> Verify -> Export`

The product is inspired by the useful workflow category demonstrated by ToolTrace.ai, but ToolDrawer Studio will be an independent implementation with its own code, architecture, user interface, project format, and branding.

## 2. Product Goals

### 2.1 Core goals

1. Convert real tools into dimensionally useful 2D/2.5D/3D geometry from photographs.
2. Detect and separate multiple tools from a single photograph.
3. Support both Gridfinity inserts and foam/shadow-board layouts from the same saved tool geometry.
4. Allow automatic layout with full manual drag, rotate, group, and lock control afterward.
5. Preserve editable project geometry instead of reducing projects to STL files.
6. Export common additive, CAD, CNC, laser, knife-cutting, and verification formats.
7. Work fully offline for all core design and export operations.
8. Remain free and open source with no artificial feature or project limits.

### 2.2 Non-goals for the first release

1. Precision industrial metrology from uncontrolled photographs.
2. Fully automatic reconstruction of arbitrary hidden geometry.
3. Mandatory cloud storage or user accounts.
4. A browser-first SaaS product.
5. A replacement for a full CAD system.
6. Direct printer firmware control.

## 3. Release Strategy

### V0.1 - Production Core

V0.1 must include both Gridfinity and foam workflows.

Features:

- Windows desktop application.
- Import JPG, PNG, and other formats supported by the image stack.
- A4 and Letter calibration.
- Printable calibration target support.
- Two-point known-distance calibration for ruler/caliper workflows.
- Known-size-object calibration.
- Perspective correction.
- Multiple tool detection from one image.
- Hybrid tracing pipeline.
- Per-tool manual contour editing.
- Clearance/offset controls.
- Manual thickness/depth entry.
- Drawer/tray/bin dimensions.
- Automatic layout plus manual editing.
- Standard Gridfinity generation.
- Custom Gridfinity grid pitch and core structural parameters.
- Single-layer and multi-layer foam generation.
- Stepped pocket support through manually defined regions.
- Finger-access geometry.
- Labels.
- Magnet and screw-hole options.
- Save/reopen native project files.
- Reusable local tool library.
- STL, 3MF, STEP, DXF, SVG, and 1:1 PDF export where applicable.
- One-click open/handoff to OrcaSlicer and FreeCAD when installed.

### V0.2 - Capture and Library Expansion

- Webcam capture.
- Phone-to-PC photo capture through a QR-code local-network upload page.
- Enhanced saved-tool library metadata.
- Duplicate/tool-template workflows.
- Side-view image measurement for thickness estimation.
- Better stepped-depth editing.
- Improved automatic packing.
- Additional custom-shape tools.
- More configurable direct handoff targets for laser/CNC software.

### V0.3 - Advanced Geometry

- Multi-view tool capture.
- Top, side, and angled image association.
- Approximate point-cloud or volume reconstruction.
- 3D cavity source generation.
- Region-specific depth editing.
- Geometry cleanup and repair tools.
- Advanced shape-fitting assistance.

### V1.0 - Stable Public Release

- Stable project-file compatibility policy.
- Polished installer and portable release.
- Model manager and optional model downloads.
- Application updater.
- Full user documentation.
- Automated regression suite.
- Community-library-ready architecture.
- Accessibility and keyboard-navigation pass.
- Crash recovery and autosave hardening.

## 4. Technical Architecture

### 4.1 Recommended stack

- **Language:** Python 3.12-compatible codebase.
- **Desktop UI:** PySide6 / Qt.
- **Image processing:** OpenCV.
- **Local AI inference:** ONNX Runtime with pluggable execution providers.
- **CAD/solid modeling:** CadQuery backed by OpenCascade.
- **Advanced 3D processing:** Open3D where justified by V0.3 requirements.
- **Local metadata database:** SQLite.
- **Project serialization:** Versioned JSON metadata plus embedded binary/image assets in a ZIP-based `.tds` container.
- **Testing:** pytest plus image/geometry regression fixtures.
- **Packaging:** Qt/Python Windows packaging path with GitHub Actions-generated release artifacts.

### 4.2 Architectural principles

1. Local-first.
2. Core features have no network dependency.
3. Geometry is stored in real-world millimetres after calibration.
4. AI is advisory, not authoritative.
5. Manual correction is always available.
6. Each subsystem communicates through explicit data contracts.
7. Exporters consume validated internal geometry rather than UI state.
8. Project-file schema is versioned from the beginning.
9. AI models are replaceable without rewriting the application.
10. CAD generation is deterministic for identical parameters.

## 5. High-Level Components

### 5.1 Application Shell

Responsibilities:

- Main navigation.
- Project lifecycle.
- Window/layout persistence.
- Recent projects.
- Settings.
- Installed integration discovery.
- Crash recovery/autosave coordination.

Dependencies:

- Project Service.
- Settings Service.
- Integration Service.

### 5.2 Capture Service

Inputs:

- Imported image.
- Webcam image.
- Phone-upload image.

Outputs:

- Original image asset.
- EXIF orientation-normalized working image.
- Capture metadata.

Phone capture must use a temporary LAN-only upload endpoint initiated by the desktop app. The QR code contains the local upload address and a short-lived random session token. The app must not require internet connectivity for this transfer.

### 5.3 Calibration Service

Supported methods:

1. A4 sheet.
2. US Letter sheet.
3. ToolDrawer Studio printable calibration marker.
4. Two-point known distance.
5. Known-size object.

Responsibilities:

- Determine pixel-to-mm transform.
- Correct perspective/homography when enough reference geometry exists.
- Estimate confidence.
- Store calibration method and parameters.

The printable calibration target should contain multiple known dimensions and fiducial markers so scale and perspective can be solved together.

### 5.4 Tracing Service

Tracing is hybrid and modular.

Common interface:

- `trace(image, hints, calibration) -> TraceResult`

Implementations:

- `OpenCVTracer`
- `LocalAITracer`
- `OnlineAITracer` (optional, disabled unless configured)
- `HybridTracer`

Hybrid pipeline:

1. Normalize/correct source image.
2. Generate candidate object masks.
3. Use local AI segmentation when enabled/available.
4. Combine AI and deterministic image evidence.
5. Separate disconnected tool candidates.
6. Clean masks morphologically.
7. Extract contours.
8. Simplify and smooth contours within bounded tolerances.
9. Transform contours from pixels into millimetres.
10. Score trace confidence.
11. Present every tool independently for review.

No online AI provider may be required for baseline functionality.

### 5.5 Tool Geometry Editor

Each tool is represented as an independent `ToolObject`.

Editable properties include:

- Name.
- Category/tags.
- Source image reference.
- 2D outline.
- Holes/internal islands.
- Nominal width/height.
- Clearance.
- Rotation.
- Uniform depth.
- Region-specific depth.
- Finger-access regions.
- Labels.
- Optional multi-view assets.
- Optional reconstructed 3D source.

Editing operations:

- Add/remove mask paint.
- Node/segment editing.
- Smooth contour.
- Simplify contour.
- Undo/redo.
- Symmetry assistance.
- Offset preview.
- Exact dimension override.
- Region creation for stepped depths.

All manual edits must be non-destructive relative to the original photograph and initial trace.

### 5.6 Tool Library

SQLite stores searchable metadata. Project/tool assets remain file-backed.

Library features:

- Save traced tool for reuse.
- Search by name/tag/category.
- Preview image and outline.
- Store calibration-derived dimensions.
- Store depth information.
- Version tool geometry when edited.
- Duplicate a tool as a new template.
- Reuse the same tool in Gridfinity and foam projects without retracing.

The application must never require cloud synchronization for the local library.

### 5.7 Layout Engine

Inputs:

- Available rectangular or custom boundary.
- Tool footprints including clearance.
- Rotation rules.
- Locked positions.
- Finger-access exclusion regions.
- Border spacing.
- Grid constraints when generating Gridfinity layouts.

Outputs:

- Candidate placement.
- Utilization score.
- Conflict list.

Workflow:

1. Generate an automatic arrangement.
2. Present it as editable rather than final.
3. Allow drag, rotate, lock, unlock, group, and manual alignment.
4. Re-optimize only unlocked items when requested.

The optimizer must favor practical access, not merely mathematical packing density.

### 5.8 Gridfinity Generator

Defaults:

- Standard 42 mm Gridfinity pitch.

Configurable parameters:

- Grid pitch.
- X/Y grid count.
- Base dimensions.
- Base height.
- Bin/insert height.
- Wall thickness.
- Floor thickness.
- Stacking lip.
- Tool clearance.
- Pocket depth.
- Magnet hole diameter/depth/pattern.
- Screw holes.
- Finger scoops.
- Labels.
- Combined inserts versus individual bins.

Generation flow:

1. Validate requested dimensions.
2. Build Gridfinity base/body parametrically.
3. Build tool cavity solids from stored tool geometry.
4. Apply clearance.
5. Apply pocket depth/stepped regions.
6. Add finger-access geometry.
7. Subtract tool cavities.
8. Add labels/optional geometry.
9. Validate final solid.
10. Export.

### 5.9 Foam / Shadow-Board Generator

Supports:

- Single-layer foam.
- Multiple layers.
- Different layer thicknesses.
- Through-cut outlines.
- Stepped cavities.
- Different depth regions.
- Finger scoops.
- Labels.
- Alignment holes.
- Registration marks.
- Per-layer manufacturing output.

Each layer must be viewable and exportable independently.

### 5.10 3D Reconstruction Service

This component is optional until V0.3.

Inputs:

- Top image.
- Side image.
- One or more angled images.
- Calibration for each view.

Outputs:

- Approximate aligned 3D geometry.
- Confidence/warnings.

The resulting geometry is a cavity-design aid, not certified dimensional inspection data. The user can override dimensions and local depths manually.

### 5.11 Export Service

Supported outputs by geometry type:

- STL.
- 3MF.
- STEP.
- DXF.
- SVG.
- 1:1 PDF.

Rules:

- STL and 3MF must be generated from validated solids/meshes.
- STEP should preserve usable CAD geometry when practical.
- DXF/SVG coordinates must remain in real-world scale.
- PDF verification output must provide an explicit 100% / no-scaling print instruction.
- Every export records app version, project revision, and key dimensional settings in project export history.

### 5.12 Integration Service

V0.1 integrations:

- Detect OrcaSlicer executable.
- Detect FreeCAD executable.
- Launch generated file in selected target.
- Allow manually configured executable paths.

Later versions may add laser/CNC-specific launch profiles, but generation/export must never depend on a specific third-party application.

## 6. Native `.tds` Project Format

The project file is a ZIP-based container with a versioned manifest.

Example conceptual structure:

```text
project.tds
  manifest.json
  project.json
  images/
    capture_001.jpg
    capture_002.jpg
  tools/
    <tool-id>/tool.json
    <tool-id>/mask.png
    <tool-id>/outline.json
    <tool-id>/views/
  layouts/
    layout.json
  exports/
    history.json
```

Requirements:

- `schema_version` is mandatory.
- Assets use stable UUIDs.
- Paths inside the archive are relative.
- Original images are preserved.
- Editing operations should not destroy original source data.
- Future schema migration must be explicit and testable.

## 7. Core Data Model

### Project

- ID.
- Name.
- Creation/modification timestamps.
- Schema version.
- Unit system display preference.
- Capture assets.
- Calibration records.
- Tool objects.
- Layouts.
- Gridfinity settings.
- Foam settings.
- Export history.

Internal geometry units remain millimetres regardless of display preference.

### CalibrationRecord

- ID.
- Capture ID.
- Method.
- Reference dimensions.
- Transform/homography.
- Residual error estimate.
- Confidence score.

### ToolObject

- ID.
- Name.
- Tags.
- Source capture ID.
- Base contour.
- Edited contour.
- Internal contours.
- Dimensions.
- Clearance.
- Uniform depth.
- Depth regions.
- Finger-access definition.
- View references.
- Optional 3D geometry reference.
- Trace confidence.

### LayoutItem

- Tool ID.
- Position X/Y.
- Rotation.
- Locked state.
- Group ID.
- Access margin.

## 8. Offline / Online Boundary

### Must work offline

- Open/save projects.
- Image import.
- Calibration.
- Perspective correction.
- Local tracing.
- Manual refinement.
- Tool library.
- Layout optimization.
- Gridfinity generation.
- Foam generation.
- CAD/vector exports.
- PDF verification sheets.
- OrcaSlicer/FreeCAD launch.
- LAN phone transfer when PC and phone share a network.

### Optional online features

- Application update checks.
- Downloadable local AI models.
- Optional online AI tracing fallback.
- Optional backup/sync.
- Future community tool library.

Network failure must never corrupt or block an active project.

## 9. Error Handling and Safety

### Calibration errors

The application must reject or warn on:

- Insufficient reference points.
- Extreme perspective.
- Blurry calibration edges.
- Inconsistent known dimensions.
- Poor fit residuals.

### Trace errors

Warnings should include:

- Tool touching image boundary.
- Merged tools.
- Very low contrast.
- Heavy shadow/reflection.
- Internal holes not confidently resolved.
- Contour ambiguity.

The user can always enter manual-edit mode.

### Geometry errors

Before export:

- Detect invalid/self-intersecting contours.
- Reject impossible negative dimensions.
- Detect pockets deeper than available material.
- Check minimum wall/floor constraints.
- Validate solids before STEP/STL/3MF export.
- Warn about inaccessible finger geometry or overlapping tools.

## 10. Accuracy Targets

The initial design target under a good calibrated photograph is:

- **2D outline dimensional error:** <= 0.5 mm for typical hand-tool organizer use when calibration confidence is high.

This is a product target, not a promise for every photograph.

The UI must expose confidence and encourage a physical verification step when image quality is insufficient.

For manufacturing verification, the application generates a true-scale PDF or 2D outline that the user can print at 100% scale and physically place the tool against before committing foam or filament.

## 11. Testing Strategy

### Unit tests

- Calibration math.
- Homography transforms.
- mm/pixel conversions.
- Contour offsets.
- Simplification bounds.
- Packing constraints.
- Project serialization/migrations.
- Export parameter validation.

### Golden-image tests

Maintain a fixture library containing:

- High-contrast tools.
- Dark tools on dark backgrounds.
- Reflective tools.
- Multiple overlapping-nearby tools.
- Pliers.
- Ratchets.
- Screwdrivers.
- Wrenches.
- Sockets.
- Irregular hand tools.

Each fixture records expected approximate masks/contours and calibration truth.

### Geometry regression tests

For known ToolObjects:

- Generate Gridfinity solids.
- Generate foam layers.
- Validate solid health.
- Validate bounding dimensions.
- Check minimum thickness constraints.
- Confirm deterministic geometry hash/measurements where practical.

### Export tests

- STL mesh validity/watertightness.
- 3MF package opens and has correct units.
- STEP importer round-trip dimensions.
- DXF scale.
- SVG scale.
- PDF 1:1 scale reference.

### Integration tests

- Save/reopen project without geometry drift.
- Offline startup.
- Optional online feature failure while core operations continue.
- OrcaSlicer/FreeCAD path detection.
- Phone upload token expiry and rejection of invalid sessions.

## 12. Security and Privacy

- Imported photos remain local unless the user explicitly invokes an online feature.
- Online AI providers are opt-in and visibly identified.
- No background photo upload.
- Phone upload server binds only for an active capture session and uses a random short-lived token.
- LAN upload sessions time out automatically.
- Uploaded phone content is validated as supported image data before processing.
- Project archives never execute embedded content.
- Application update packages must eventually be integrity-checked/signed.

## 13. User Interface Structure

Primary screens:

1. Home / Recent Projects.
2. Capture.
3. Calibration.
4. Tool Detection.
5. Tool Editor.
6. Tool Library.
7. Layout.
8. Gridfinity Designer.
9. Foam Designer.
10. 2D/3D Preview.
11. Verification.
12. Export.
13. Settings / Models / Integrations.

The workflow should behave like a guided pipeline without locking experienced users into a wizard. Users can move backward to correct source data and downstream geometry should be marked dirty/recomputed explicitly.

## 14. UX Requirements

- Undo/redo for all manual geometry edits.
- Autosave recovery.
- Clear dirty/unsaved indicator.
- Real-time dimension display in mm and optional inches.
- Mouse-wheel zoom centered near pointer.
- Pan, fit, 1:1 view.
- Snap/align tools in layout view.
- Clear visibility of clearance versus actual tool outline.
- Separate visibility toggles for source photo, mask, raw trace, cleaned trace, cavity outline, and finger-access geometry.
- Keyboard shortcuts for common editing operations.
- No feature requires creating an account.

## 15. Licensing and Third-Party Dependencies

Application source target license:

- GPL-3.0-or-later.

Before release, every bundled dependency and AI model must be reviewed for license compatibility and redistribution requirements. Model files with incompatible redistribution terms must not be bundled; the model manager may instead provide instructions/download integration when lawful.

Third-party brand names such as Gridfinity, OrcaSlicer, FreeCAD, ToolTrace, OpenCV, Qt/PySide, CadQuery, and ONNX Runtime are used descriptively and do not imply affiliation.

## 16. Repository Structure Target

```text
ToolDrawer-Studio/
  README.md
  LICENSE
  pyproject.toml
  docs/
    architecture/
    user-guide/
    superpowers/specs/
  src/tooldrawer_studio/
    app/
    capture/
    calibration/
    tracing/
    geometry/
    library/
    layout/
    gridfinity/
    foam/
    reconstruction/
    export/
    integrations/
    persistence/
    ui/
  tests/
    unit/
    fixtures/
    golden_images/
    geometry/
    integration/
  tools/
  .github/workflows/
```

The modules above are boundaries, not a requirement to create empty placeholder packages before they have behavior.

## 17. Acceptance Criteria for V0.1

A V0.1 build is acceptable when a user can, entirely offline:

1. Create a project.
2. Import a photograph containing multiple hand tools.
3. Calibrate it using at least A4/Letter, a known distance, or the printable target.
4. Correct perspective when applicable.
5. Automatically obtain separate candidate outlines for multiple tools.
6. Manually correct each outline.
7. Assign names, depth, and clearance.
8. Enter drawer/tray dimensions.
9. Automatically arrange tools and manually adjust placement.
10. Generate either a Gridfinity design or a multi-layer/single-layer foam design from the same ToolObjects.
11. Add finger access and labels.
12. Configure relevant Gridfinity or foam settings.
13. Preview dimensions before export.
14. Save and reopen the project without losing editability.
15. Export manufacturing files at correct scale.
16. Generate a 1:1 physical verification output.
17. Open applicable output in OrcaSlicer or FreeCAD when configured.

No V0.1 acceptance criterion may require an internet connection, account, subscription, or paid API.

## 18. Implementation Boundaries

Implementation should begin with the smallest vertical slice that proves the architecture:

`Import one image -> calibrate -> trace one/multiple silhouettes -> manually refine -> save ToolObject -> generate one valid parametric pocket -> export STEP/STL/DXF -> reopen project`

Only after that slice is reliable should work expand into richer layout optimization, foam layering, capture methods, and advanced AI.

This reduces the chance of building a visually impressive application around geometry that cannot be trusted.

## 19. Design Decisions Locked by User Approval

The approved product decisions are:

- Windows desktop application.
- Both Gridfinity and foam output.
- Existing-photo import, webcam capture, and phone capture.
- Online and offline operation, with local-first core features.
- Calibration via paper, ruler/calipers, printable marker, and known-size object.
- Hybrid AI + traditional image-processing tracing.
- Multiple tools per photo.
- Automatic layout followed by full manual editing.
- Standard Gridfinity defaults plus full customization.
- Single- and multi-layer foam with stepped pockets, finger scoops, labels, alignment holes, and per-layer outputs.
- Tool depth by manual entry and side-image estimation.
- Fast stepped 2.5D geometry plus optional multi-view 3D reconstruction.
- Fully editable project geometry plus STEP and manufacturing exports.
- Direct handoff to OrcaSlicer, FreeCAD, and configurable CNC/laser workflows.
- Open-source distributable application.

## 20. Spec Self-Review Checklist

This specification intentionally contains no TBD/TODO placeholders for V0.1 behavior. The architecture separates capture, calibration, tracing, geometry, layout, generation, export, and persistence. Core features are consistently defined as offline-capable. Advanced reconstruction is explicitly deferred to V0.3 so it does not block a useful V0.1. Accuracy is treated as a measurable target with confidence warnings rather than as guaranteed metrology.
