from __future__ import annotations

from pathlib import Path

MM_TO_PT = 72.0 / 25.4


def mm_to_pt(value_mm: float) -> float:
    return float(value_mm) * MM_TO_PT


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_vector_pdf(
    path: Path,
    width_mm: float,
    height_mm: float,
    polylines: list[tuple[tuple[float, float], ...]],
    texts: list[tuple[float, float, float, str]],
) -> Path:
    """Write a 1:1 millimetre PDF. `texts` are (x_mm, y_mm, size_pt, content)."""

    width_pt = mm_to_pt(width_mm)
    height_pt = mm_to_pt(height_mm)
    if width_pt <= 1.0 or height_pt <= 1.0:
        raise ValueError("PDF page size must be positive")

    operations: list[str] = ["0.35 w", "0 0 0 RG", "0 0 0 rg"]
    for coordinates in polylines:
        if len(coordinates) < 2:
            continue
        first_x, first_y = coordinates[0]
        operations.append(f"{mm_to_pt(first_x):.3f} {mm_to_pt(first_y):.3f} m")
        for x_mm, y_mm in coordinates[1:]:
            operations.append(f"{mm_to_pt(x_mm):.3f} {mm_to_pt(y_mm):.3f} l")
        operations.append("h S")
    for x_mm, y_mm, size_pt, content in texts:
        operations.append(
            "BT /F1 {size:.2f} Tf {x:.3f} {y:.3f} Td ({text}) Tj ET".format(
                size=size_pt,
                x=mm_to_pt(x_mm),
                y=mm_to_pt(y_mm),
                text=_escape(content),
            )
        )
    stream = ("\n".join(operations) + "\n").encode("latin-1", errors="replace")
    page = (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.3f} {h:.3f}] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    ).format(w=width_pt, h=height_pt).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page,
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    chunks = [header]
    position = len(header)
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(position)
        block = f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        chunks.append(block)
        position += len(block)
    xref_lines = [f"xref\n0 {len(objects) + 1}\n", "0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n \n")
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{position}\n%%EOF\n"
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(chunks) + "".join(xref_lines).encode("ascii") + trailer)
    return path
