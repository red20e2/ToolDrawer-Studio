# ToolDrawer Studio

ToolDrawer Studio is a pre-release, open-source Windows desktop application for turning calibrated photographs of tools into editable organizer geometry.

The current V0.1 foundation includes the dimensional core: import or capture source photos, calibrate pixels to millimetres, trace one or more tool silhouettes, refine contours without destroying the base trace, save/reopen editable `.tds` projects, re-trace stored source images, generate a parametric pocket, and export STEP/STL/DXF manufacturing geometry.

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
