# core/single_instance.py
"""Only one AirMouse at a time: two instances would fight over the camera and the cursor."""

from __future__ import annotations

import ctypes
import sys
import time

_ERROR_ALREADY_EXISTS = 183
_handle = None


def acquire(name: str = "Local\\AirMouseSingleInstance", wait_s: float = 0.0) -> bool:
    """
    True if this is the only running instance (always True outside Windows).

    wait_s: keep trying this long — after a restart the previous AirMouse may
    still be closing (releasing the camera) for a moment.
    """
    global _handle
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    deadline = time.monotonic() + wait_s
    while True:
        _handle = kernel32.CreateMutexW(None, False, name)
        if ctypes.get_last_error() != _ERROR_ALREADY_EXISTS:
            return True
        kernel32.CloseHandle(_handle)
        _handle = None
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


def release() -> None:
    """Let another AirMouse start now (before this process has fully exited)."""
    global _handle
    if _handle is not None and sys.platform == "win32":
        ctypes.WinDLL("kernel32").CloseHandle(_handle)
    _handle = None


def show_already_running() -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(
            None,
            "AirMouse is already running.\n\nLook for its icon next to the clock (it may be under the ^ arrow).",
            "AirMouse",
            0x40,  # MB_ICONINFORMATION
        )
