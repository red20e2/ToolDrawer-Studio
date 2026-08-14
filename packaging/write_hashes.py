from hashlib import sha256
from pathlib import Path
import sys


def write_hashes(paths, output):
    rows = []
    for path in sorted((Path(p) for p in paths), key=lambda p: p.name):
        rows.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}")
    Path(output).write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    destination = Path(sys.argv[1])
    write_hashes([Path(value) for value in sys.argv[2:]], destination)
