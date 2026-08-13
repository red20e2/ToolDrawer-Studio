from pathlib import Path

import pytest


def _release_check_module():
    try:
        import tooldrawer_studio.release_check as release_check
    except ModuleNotFoundError:
        pytest.fail("release verification module is not implemented")
    return release_check


def test_release_self_test_generates_both_modes_and_all_exports(tmp_path):
    release_check = _release_check_module()
    assert release_check.run_release_check(tmp_path) == 0
    for mode in ("foam", "gridfinity"):
        directory = tmp_path / mode
        files = {path.suffix.lower(): path for path in directory.iterdir() if path.is_file()}
        assert {".step", ".stl", ".dxf"}.issubset(files)
        assert all(path.stat().st_size > 0 for path in files.values())


def test_release_self_test_returns_nonzero_with_useful_diagnostic(monkeypatch, tmp_path, capsys):
    release_check = _release_check_module()

    def fail_probe() -> None:
        raise RuntimeError("dependency probe failed")

    monkeypatch.setattr(release_check, "_probe_dependencies", fail_probe)
    assert release_check.run_release_check(tmp_path) != 0
    captured = capsys.readouterr()
    assert "dependency probe failed" in captured.err


def test_main_accepts_noninteractive_self_test_cli(monkeypatch, tmp_path):
    import tooldrawer_studio.__main__ as app_main

    calls: list[Path] = []

    def fake_run_release_check(output_dir: Path) -> int:
        calls.append(Path(output_dir))
        return 0

    monkeypatch.setattr(app_main, "run_release_check", fake_run_release_check, raising=False)
    assert app_main.main(["--self-test", "--output-dir", str(tmp_path)]) == 0
    assert calls == [tmp_path]
