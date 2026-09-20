# PyInstaller specification for the sidecar executable.
#
# One file, no console window on Windows, and no hidden network anything. The shell
# spawns this binary and talks to it down a pipe.
#
# `console=True` is deliberate and is not a mistake to be tidied up later: on Windows a
# GUI-subsystem executable has no standard input or output to inherit, and this process
# communicates over exactly those. The shell spawns it with CREATE_NO_WINDOW so no
# console is visible; the subsystem and the window are different things, and confusing
# them produces a sidecar that starts and then answers nothing.
#
# Building this is CI's job on Windows. It is built on Linux too, in the same workflow,
# because a spec that is broken is broken on both and the Linux build fails four minutes
# sooner.

import sys
from pathlib import Path

block_cipher = None

analysis = Analysis(
    ["src/duckbot_host/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pydantic builds models at import time through machinery PyInstaller's static
        # analysis does not follow. Named explicitly rather than discovered by a failing
        # build on somebody else's machine.
        "pydantic",
        "pydantic_core",
        "duckbot_schemas",
        "duckbot_core",
        "duckbot_privacy",
        "duckbot_memory",
        "duckbot_gateway",
        "duckbot_engine",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Nothing here should be pulling in a GUI toolkit or a test runner. Excluding
        # them keeps the binary small and makes an accidental dependency loud.
        "tkinter",
        "unittest",
        "pytest",
        "IPython",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name="duckbot-host",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries are a reliable way to be flagged by antivirus.
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
