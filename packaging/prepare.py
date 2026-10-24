"""
Get everything the Windows package needs, before PyInstaller runs:

- the MediaPipe models in models/ (bundled, so the app works offline from the start)
- build/airmouse.ico and build/version_info.txt (icon and file properties of AirMouse.exe)

Run from the repository root:  python packaging/prepare.py
Prints the version; with GITHUB_REF=refs/tags/vX.Y.Z it fails unless the tag
matches core/version.py, so a release can't ship the wrong number.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("AIRMOUSE_IGNORE_LOCAL_CONFIG", "1")  # build with the defaults

import config  # noqa: E402
from core.icon import save_ico  # noqa: E402
from core.models import ensure_model  # noqa: E402
from core.version import __version__  # noqa: E402

VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'AirMouse contributors'),
      StringStruct('FileDescription', 'AirMouse - control your PC with hand gestures'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'AirMouse'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'AirMouse.exe'),
      StringStruct('ProductName', 'AirMouse'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/tags/v") and ref[len("refs/tags/v"):] != __version__:
        print(f"Tag {ref} does not match core/version.py ({__version__})", file=sys.stderr)
        return 1

    ensure_model(config.MP_MODEL_PATH, config.MP_MODEL_URL, "MediaPipe hand")
    ensure_model(config.FACE_MODEL_PATH, config.FACE_MODEL_URL, "MediaPipe face")
    save_ico(ROOT / "build" / "airmouse.ico")

    parts = [int(p) for p in __version__.split(".")[:3]] + [0]
    nums = tuple((parts + [0, 0, 0, 0])[:4])
    (ROOT / "build" / "version_info.txt").write_text(
        VERSION_INFO.format(nums=nums, version=__version__), encoding="utf-8"
    )
    print(__version__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
