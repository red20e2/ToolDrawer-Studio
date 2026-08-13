from pathlib import Path

path = Path("src/tooldrawer_studio/ui/main_window.py")
text = path.read_text(encoding="utf-8")

broken = '            self.export_status.setText("Exported:\n" + "\n".join(exported))\n'
# The scripted integration accidentally embedded literal line breaks inside the
# quoted strings. Express that exact broken source separately from the intended
# escaped Python string.
broken_literal = '''            self.export_status.setText("Exported:
" + "
".join(exported))
'''
fixed = '            self.export_status.setText("Exported:\\n" + "\\n".join(exported))\n'

if fixed in text:
    print("export-string-already-fixed")
elif broken_literal in text:
    text = text.replace(broken_literal, fixed, 1)
    print("fixed-export-string")
else:
    raise RuntimeError("Expected malformed export-status string not found")

# Remove the now-dead Pocket Settings handler so Stage 5 has one authority.
start = text.find("    def _configure_pocket(self) -> None:\n")
if start >= 0:
    end = text.find("    def _save_project(self) -> None:\n", start)
    if end < 0:
        raise RuntimeError("Could not find end of obsolete _configure_pocket method")
    text = text[:start] + text[end:]
    print("removed-obsolete-pocket-handler")

path.write_text(text, encoding="utf-8")
