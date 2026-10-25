# packaging/airmouse.spec — PyInstaller recipe for AirMouse.exe (Windows).
#
# Build from the repository root, with the models already in models/:
#     pyinstaller packaging/airmouse.spec --noconfirm
# Result: dist/AirMouse/AirMouse.exe plus its _internal folder (a "one-folder"
# app: it starts much faster than a single self-extracting file). Check it with
#     dist/AirMouse/AirMouse.exe --self-test     (log: %LOCALAPPDATA%\AirMouse\airmouse.log)
# packaging/airmouse.iss turns the folder into AirMouse-Setup-<version>.exe.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is defined by PyInstaller)

datas = [
    (str(ROOT / "core" / "web" / "settings.html"), "core/web"),
    (str(ROOT / "core" / "web" / "phone.html"), "core/web"),
    (str(ROOT / "models" / "hand_landmarker.task"), "models"),
    (str(ROOT / "models" / "face_landmarker.task"), "models"),
]
datas += collect_data_files("mediapipe")
binaries = collect_dynamic_libs("mediapipe")

hiddenimports = [
    # Backends chosen by name at run time
    "pystray._win32",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "screeninfo.enumerators.windows",
]
hiddenimports += collect_submodules("mediapipe.tasks.python")

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "jupyter", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AirMouse",
    icon=str(ROOT / "build" / "airmouse.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
    console=False,  # a tray app: no terminal window
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AirMouse",
)
