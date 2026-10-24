# core/startup.py
"""'Start with Windows': a value under HKCU\\...\\Run that launches AirMouse without a console."""

from __future__ import annotations

import sys
from pathlib import Path

from core import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AirMouse"
APP_DIR = Path(__file__).resolve().parents[1]


def _winreg():
    import winreg  # Windows only

    return winreg


def launch_command(app_dir: Path = APP_DIR, python: str = sys.executable, frozen: bool = paths.FROZEN) -> str:
    """The installed AirMouse.exe, or pythonw.exe (no console window) from the same environment running main.py."""
    if frozen:
        return f'"{python}"'  # sys.executable is AirMouse.exe itself
    pythonw = Path(python).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(python)
    return f'"{exe}" "{app_dir / "main.py"}"'


def is_enabled(winreg=None) -> bool:
    winreg = winreg or _winreg()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
    except OSError:
        return False
    try:
        winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False
    finally:
        winreg.CloseKey(key)


def enable(command: str | None = None, winreg=None) -> None:
    winreg = winreg or _winreg()
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
    try:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or launch_command())
    finally:
        winreg.CloseKey(key)


def disable(winreg=None) -> None:
    winreg = winreg or _winreg()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except OSError:
        return
    try:
        winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
    finally:
        winreg.CloseKey(key)
