# ToolDrawer Studio

ToolDrawer Studio is a pre-release, open-source Windows desktop application for turning calibrated photographs of tools into editable organizer geometry.

The current V0.1 foundation includes the dimensional core: import or capture source photos, calibrate pixels to millimetres, trace one or more tool silhouettes, refine contours without destroying the base trace, measure physical tool thickness from an independently calibrated side view, arrange calibrated tool cavities inside foam/drawer or Gridfinity boundaries, derive a pocket-depth suggestion, save/reopen editable `.tds` projects, generate a parametric pocket, and export STEP/STL/DXF manufacturing geometry.

## Capture workflow

ToolDrawer Studio can receive images three ways:

1. **Import Photo** - choose an existing image on the PC.
2. **Webcam** - open the webcam panel, select an available camera, view the live preview, and press **Capture**.
3. **Phone** - press **Start Phone Session**, scan the displayed QR code with a phone on the same local network, then use **Take Photo** or **Choose Existing Photo** in the phone browser.

Phone and webcam captures enter one shared pending-capture tray. Pending images may be previewed, rotated in 90-degree steps, or deleted before they are added to a project. **Add to Project** promotes the selected orientation into the editable project without deleting that pending image or any other pending images.

### Phone capture sessions

Phone transfer is local-network-only. No cloud relay, account, or internet connection is required for the transfer itself.

Each phone session:

- creates a fresh temporary random token;
- accepts multiple photos while active;
- binds only to an RFC1918 private IPv4 address (`10.x.x.x`, `172.16-31.x.x`, or `192.168.x.x`);
- fails closed if the PC does not have a suitable private IPv4 address;
- stops if the bound private address disappears;
- stops when **Stop Phone Session** is pressed;
- also stops after **30 minutes of inactivity**.

Only an authenticated phone-page load or a successfully accepted image refreshes the inactivity timer. Invalid tokens, malformed requests, rejected images, and unrelated traffic do not keep the session alive. Stopping, expiring, or replacing a session invalidates its old token and QR URL.

The upload endpoint accepts images only and never exposes project files, arbitrary folders, shell commands, or a general-purpose file server. The phone page is served directly by ToolDrawer Studio and does not load remote JavaScript, stylesheets, fonts, or analytics.

### Pending-capture limits

All captured/uploaded images use the same validation path as imported source images:

- maximum source size: **50 MB**;
- maximum decoded image size: **40 megapixels**.

Corrupt, unsupported, oversized, incomplete, or non-image uploads are rejected before entering the pending tray.

Pending tray contents are temporary application-session data in V0.1. Once **Add to Project** is used, that promoted capture becomes normal persistent `.tds` project data. Unpromoted pending images are not restored after an application restart or crash.

Special HEIC/HEIF codec installation is not part of this capture slice. Images already supported by the installed OpenCV image stack continue to work normally.

## Calibration workflow

The calibration screen works directly on the imported or promoted photo. Clicked points are stored in native image-pixel coordinates; all downstream geometry is converted to millimetres through the active calibration transform.

Five calibration modes are available:

1. **Known distance** - click two points and enter the real distance between them.
2. **A4 sheet** - click the four paper corners in this order: top-left, top-right, bottom-right, bottom-left. The physical reference is 210 x 297 mm.
3. **US Letter** - click the four paper corners in the same order. The physical reference is 215.9 x 279.4 mm.
4. **Known-size object** - click four corners in the same order, then enter the object's real width and height.
5. **Printable target** - choose A4 or US Letter, save the generated SVG, print it at true size, photograph it with the tools, then use **Detect Target**. Four square fiducials provide scale and perspective correction automatically.

### Printing the calibration target

Print the SVG at **100% / Actual Size**. Disable options such as **Fit to page**, **Shrink oversized pages**, or other printer scaling. The target includes labelled 100 mm horizontal and vertical verification bars; measure them after printing before relying on the target.

A photographed target is a manufacturing aid, not a metrology instrument. Camera focus, lens distortion, paper flatness, printer scaling, lighting, and click placement can all affect the result.

### Calibration confidence

Calibration confidence is displayed after calibration. Automatic tracing requires confidence of at least **75%** by default. If confidence is lower, ToolDrawer Studio shows an explicit **Allow low-confidence automatic tracing** override instead of silently treating uncertain dimensions as precise.

Using a larger reference in the photo generally produces better dimensional confidence than measuring a very short pixel span. A4/Letter, a large known object, or the printable target are preferred when practical.

## Measure / thickness workflow

The **Measure** stage keeps physical tool thickness separate from manufacturing pocket depth.

For each traced tool, attach one side-view capture. The side view must be calibrated independently from the top-view image; ToolDrawer Studio never reuses another photo's pixel scale. A pending phone/webcam capture can be selected as a side view without consuming or deleting it from the pending tray.

After side-view calibration, **Measure Automatically** uses deterministic local OpenCV image analysis to estimate the tool's maximum calibrated thickness. The automatic source value, confidence, measurement endpoints, silhouette, and any warning state are stored in the editable project.

Automatic thickness confidence uses an **80%** acceptance threshold:

- at or above 80%, the result may become the accepted thickness automatically when no exact manual thickness already has precedence;
- below 80%, the automatic result is shown for review but cannot drive the pocket-depth suggestion until it is explicitly accepted or corrected.

Manual correction remains available even when automatic silhouette detection fails. You can place or drag two measurement endpoints on the calibrated side image, or enter an exact physical thickness directly. An exact manual thickness takes precedence over later automatic remeasurement while the automatic source result is still preserved separately.

### Pocket-depth suggestion

Project defaults are:

- desired exposed height: **4.0 mm**;
- bottom clearance: **0.8 mm**.

Each tool can override either value independently. The suggested manufacturing depth is:

```text
accepted tool thickness - desired exposed height + bottom clearance
```

For example, an 18.0 mm tool using the default 4.0 mm exposed height and 0.8 mm bottom clearance produces a 14.8 mm suggested pocket depth.

The suggested depth and final manufacturing depth are separate. You can explicitly override final pocket depth; that explicit override is never silently replaced by a later side-view measurement. Pocket generation and STEP/STL/DXF export use the resolved final depth from the Measure stage.

Replacing or recalibrating a side-view image invalidates image-derived automatic/endpoint measurements. Exact manual thickness and explicit final pocket-depth overrides are preserved and flagged for review rather than silently discarded.

Measure state was introduced in `.tds` schema V2 and remains preserved in the current V3 format. Existing V1 projects migrate non-destructively through V2 to V3: the old `depth_mm` value is preserved exactly as the explicit pocket-depth override. Reopening a project restores saved Measure state without automatically rerunning image analysis.

Photo-derived measurements remain manufacturing aids rather than metrology-grade inspection data. Focus, lens distortion, calibration quality, shadows, reflections, silhouette ambiguity, and image resolution can all affect accuracy.

## Arrange / layout workflow

The **Arrange** stage lays calibrated tool cavities into one continuous rectangular organizer area. Packing and validation use the actual edited tool contour in millimetres rather than rectangular bounding boxes.

Two boundary modes are available:

- **Foam / drawer** - enter the exact inside width and depth in millimetres.
- **Gridfinity** - enter columns and rows. The default pitch is **42.0 mm**, so a 6 x 5 layout is 252 x 210 mm. Gridfinity cell lines are visual guides only; tools may span cell boundaries because the usable region is treated as one continuous rectangular area.

### Clearance and access rules

Arrange deliberately keeps manufacturing fit allowance separate from organizer spacing:

- **Pocket clearance** is stored per tool and expands the physical contour into the planned cleared cavity footprint.
- **Layout spacing** is the minimum edge-to-edge separation between neighboring cleared cavity footprints. Default: **3.0 mm**.
- **Border margin** is the minimum distance from a cleared cavity or required grab zone to the organizer boundary. Default: **4.0 mm**.
- **Grab clearance** reserves additional removal space on a selected local side of a tool. Default: **12.0 mm**.
- **Manual snap increment** affects editing only and defaults to **1.0 mm**. Stored placement coordinates remain canonical millimetres.

Grab side may be none, left, right, top, or bottom. The selected side rotates with the tool. Grab clearance is a layout exclusion rule; it does not create finger-scoop CAD or mutate the source contour.

Required spacing, boundary containment, grab access, locked placements, and rotation rules are hard constraints. Arrange never silently reduces them to force a fit.

### Rotation, locks, and manual editing

Each tool can use one rotation policy:

- **Free** - Auto Arrange tests 15-degree increments; manual rotation may use arbitrary angles.
- **90° only** - Auto Arrange tests 0, 90, 180, and 270 degrees.
- **Fixed** - preserves the current/reference orientation.

Tools may be locked. **Re-pack Unlocked** treats locked placements as immutable obstacles and preserves their exact X/Y position and rotation. Manual movement supports selection, multi-selection, alignment, distribution, and optional snapping. Arrange edits are undoable/redoable.

Changing dimensions, spacing, a tool contour, or pocket clearance can mark the saved layout as requiring review, but it does not silently move tools. Repacking occurs only after an explicit **Auto Arrange** or **Re-pack Unlocked** command.

### Automatic packing and partial fits

Auto Arrange is deterministic: the same project geometry and settings produce the same result. Harder-to-place/restricted tools are considered before smaller flexible tools. Candidate layouts must satisfy all hard geometry rules before lower-priority practical-access, orientation-consistency, and compactness scoring is considered.

If every requested tool cannot fit, Arrange keeps the best valid partial layout and records the remaining tool IDs as unplaced. It never overlaps cavities or weakens required spacing merely to increase the placed count.

`.tds` schema V3 persists Arrange defaults, boundary settings, every tool placement, rotation policy, lock state, grab-side settings, explicit unplaced tools, and review-required state. V2 projects migrate to V3 non-destructively with no invented layout. Opening a saved project restores the exact saved placement state and never automatically repacks it.

Arrange validates 2D layout geometry only. Final foam/Gridfinity solid generation remains responsible for confirming that the requested wall, base, and manufacturing geometry can actually be produced.

## Image import safety

Source images are decoded locally. The current limits are:

- maximum source file size: **50 MB**
- maximum decoded image size: **40 megapixels**

Original source bytes remain embedded in the editable `.tds` project while the working image is decoded for tracing/calibration.

## Development

Windows is the primary target platform and Python 3.12 is required.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m tooldrawer_studio
```

Core design and export features are local-first and do not require an account, subscription, paid API, or internet connection.

## License

ToolDrawer Studio is released under **GPL-3.0-or-later**. See `LICENSE` for the project license notice and terms reference.

This project is **pre-release**. File formats and APIs may change until V1.0.
