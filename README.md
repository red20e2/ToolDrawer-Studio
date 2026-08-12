# ToolDrawer Studio

ToolDrawer Studio is a pre-release, open-source Windows desktop application for turning calibrated photographs of tools into editable organizer geometry.

The current V0.1 foundation includes the dimensional core: import a source photo, calibrate pixels to millimetres, trace one or more tool silhouettes, refine contours without destroying the base trace, save/reopen editable `.tds` projects, re-trace stored source images, generate a parametric pocket, and export STEP/STL/DXF manufacturing geometry.

## Calibration workflow

The calibration screen works directly on the imported photo. Clicked points are stored in native image-pixel coordinates; all downstream geometry is converted to millimetres through the active calibration transform.

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
