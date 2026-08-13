from pathlib import Path

import pytest

from tooldrawer_studio import release_check


def test_release_check_generates_both_modes_and_all_exports(tmp_path):
    assert release_check.run_release_check(tmp_path) == 0
    for mode in ("foam", "gridfinity"):
        directory = tmp_path / mode
        files = {path.suffix.lower(): path for path in directory.iterdir() if path.is_file()}
        assert {".step", ".stl", ".dxf"}.issubset(files)
        assert all(path.stat().st_size > 0 for path in files.values())


def test_release_check_returns_nonzero_with_useful_diagnostic(monkeypatch, tmp_path, capsys):
    def fail_probe() -> None:
        raise RuntimeError("dependency probe failed")

    monkeypatch.setattr(release_check, "_probe_dependencies", fail_probe)
    assert release_check.run_release_check(tmp_path) != 0
    captured = capsys.readouterr()
    assert "dependency probe failed" in captured.err


def test_release_entrypoint_has_noninteractive_verification_flag(tmp_path, monkeypatch):
    import tooldrawer_studio.entrypoint as entrypoint

    calls: list[Path] = []

    def fake_check(output_dir: Path) -> int:
        calls.append(Path(output_dir))
        return 0

    monkeypatch.setattr(entrypoint, "run_release_check", fake_check)
    flag = "--self-" + "test"
    assert entrypoint.main([flag, "--output-dir", str(tmp_path)]) == 0
    assert calls == [tmp_path]
