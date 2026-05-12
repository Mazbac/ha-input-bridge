# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hiddenimports = []
hiddenimports += collect_submodules("pystray")
hiddenimports += collect_submodules("PIL")
hiddenimports += collect_submodules("pynput")

hiddenimports += [
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
    "pynput._util",
    "pynput._util.win32",
    "pynput.mouse._win32",
    "pynput.keyboard._win32",
    "six",
]

datas = []
datas += collect_data_files("pynput")
datas += copy_metadata("pynput")

a = Analysis(
    ["../ha_input_bridge_tray.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ha-input-bridge-tray",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
