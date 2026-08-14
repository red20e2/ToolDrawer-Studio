from pathlib import Path

import tooldrawer_studio.frozen_runtime as frozen_runtime


def test_source_runtime_does_not_add_dll_directory(monkeypatch):
    calls: list[Path] = []
    monkeypatch.delattr(frozen_runtime.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(frozen_runtime.sys, "platform", "win32")
    monkeypatch.setattr(
        frozen_runtime.os,
        "add_dll_directory",
        lambda path: calls.append(Path(path)),
        raising=False,
    )

    frozen_runtime.prepare_frozen_runtime()
    assert calls == []


def test_frozen_windows_runtime_adds_casadi_dll_directory(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    casadi_dir = bundle / "casadi"
    casadi_dir.mkdir(parents=True)
    calls: list[Path] = []

    class Handle:
        pass

    monkeypatch.setattr(frozen_runtime.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(frozen_runtime.sys, "platform", "win32")
    monkeypatch.setattr(
        frozen_runtime.os,
        "add_dll_directory",
        lambda path: calls.append(Path(path)) or Handle(),
        raising=False,
    )
    frozen_runtime._DLL_DIRECTORY_HANDLES.clear()

    frozen_runtime.prepare_frozen_runtime()
    assert calls == [casadi_dir]
    assert len(frozen_runtime._DLL_DIRECTORY_HANDLES) == 1
