# core/single_instance.py
"""Only one AirMouse at a time: two instances would fight over the camera and the cursor."""

from __future__ import annotations

import ctypes
import sys

_ERROR_ALREADY_EXISTS = 183
_handle = None


def acquire(name: str = "Local\\AirMouseSingleInstance") -> bool:
    """True if this is the only running instance (always True outside Windows)."""
    global _handle
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _handle = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS


def show_already_running() -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(
            None,
            "AirMouse is already running.\n\nLook for its icon next to the clock (it may be under the ^ arrow).",
            "AirMouse",
            0x40,  # MB_ICONINFORMATION
        )
