from pathlib import Path
import runpy


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_release_hashes_are_sorted_and_named(tmp_path):
    module = runpy.run_path(str(_root() / "packaging" / "write_hashes.py"))
    write_hashes = module["write_hashes"]

    setup = tmp_path / "ToolDrawer-Studio-0.1.0-Setup.exe"
    portable = tmp_path / "ToolDrawer-Studio-0.1.0-Portable.zip"
    setup.write_bytes(b"setup")
    portable.write_bytes(b"portable")

    output = tmp_path / "SHA256SUMS.txt"
    write_hashes([portable, setup], output)
    lines = output.read_text(encoding="utf-8").splitlines()

    assert [line.split("  ", 1)[1] for line in lines] == [setup.name, portable.name]
    assert all(len(line.split("  ", 1)[0]) == 64 for line in lines)
