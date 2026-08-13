from __future__ import annotations

import apply_generate_main_window_patch as patcher

_original_replace_once = patcher.replace_once


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if label == "organizer export handler":
        start_marker = "    def _export_files(self) -> None:\n"
        end_marker = "    def closeEvent(self, event) -> None:"
        start = text.find(start_marker)
        if start < 0:
            raise RuntimeError("organizer export handler: start marker not found")
        end = text.find(end_marker, start)
        if end < 0:
            raise RuntimeError("organizer export handler: end marker not found")
        return text[:start] + new + text[end:]
    return _original_replace_once(text, old, new, label)


patcher.replace_once = _replace_once

if __name__ == "__main__":
    changed = patcher.patch_main_window()
    print("main-window-patched" if changed else "main-window-already-patched")
