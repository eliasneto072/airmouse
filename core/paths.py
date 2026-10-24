# core/paths.py
"""
Where AirMouse's files live, from a source checkout or the installed AirMouse.exe.

- RESOURCE_DIR: read-only files shipped with the app (the settings page, the
  bundled models). The repository folder, or PyInstaller's bundle folder.
- DATA_DIR: files AirMouse writes (the log, downloaded models). The repository
  folder when run from source (as before), or %LOCALAPPDATA%\\AirMouse when
  installed: Program Files-style install folders are not writable.

User settings are separate: %APPDATA%\\AirMouse\\settings.json (settings_store).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
SOURCE_DIR = Path(__file__).resolve().parents[1]


def _resource_dir() -> Path:
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return SOURCE_DIR


def _data_dir() -> Path:
    override = os.environ.get("AIRMOUSE_DATA_DIR")
    if override:
        return Path(override)
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "AirMouse"
    return SOURCE_DIR


RESOURCE_DIR = _resource_dir()
DATA_DIR = _data_dir()


def resource(relative: str) -> Path:
    return RESOURCE_DIR / relative


def data(relative: str) -> Path:
    return DATA_DIR / relative
