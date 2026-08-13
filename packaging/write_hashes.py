from hashlib import sha256
from pathlib import Path


def write_hashes(paths, output):
    rows = []
    for path in sorted((Path(p) for p in paths), key=lambda p: p.name):
        rows.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}")
    Path(output).write_text("\n".join(rows) + "\n", encoding="utf-8")
