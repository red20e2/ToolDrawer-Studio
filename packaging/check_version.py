from __future__ import annotations

import runpy
import sys
from pathlib import Path


def application_version() -> str:
    root = Path(__file__).resolve().parents[1]
    data = runpy.run_path(root / "src" / "tooldrawer_studio" / "version.py")
    return str(data["__version__"])


def check_tag(tag: str) -> int:
    version = application_version()
    expected = f"v{version}"
    if tag != expected:
        print(
            f"Tag {tag} does not match application version {version}",
            file=sys.stderr,
        )
        return 1
    print(f"version-ok: {version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: check_version.py vX.Y.Z", file=sys.stderr)
        return 2
    return check_tag(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
