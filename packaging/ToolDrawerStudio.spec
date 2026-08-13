a = Analysis(
    ["src/tooldrawer_studio/__main__.py"],
    pathex=["src"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ToolDrawer Studio",
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ToolDrawer Studio",
)
