from PyInstaller.utils.hooks import (
    collect_dynamic_libs,
    collect_submodules,
    get_module_file_attribute,
)


binaries = collect_dynamic_libs("casadi", destdir="casadi")
binaries.append((get_module_file_attribute("casadi._casadi"), "casadi"))
hiddenimports = collect_submodules("casadi")
