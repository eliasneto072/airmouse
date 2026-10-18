# core/actions.py
"""
Named actions that gesture bindings refer to (SHORTCUT_BINDINGS, MEDIA_BINDINGS, …).

Bindings are plain config data — {"swipe_right": "next_tab"} — so users can remap
gestures without touching code. Each action is a key combination sent with
MouseActuator.press_combo(); key names follow pynput (``ctrl``, ``cmd`` = Win key,
``media_play_pause``, …) and single characters are literal keys.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ACTIONS: dict[str, tuple[str, ...]] = {
    # Windows & desktop
    "alt_tab": ("alt", "tab"),
    "task_view": ("cmd", "tab"),
    "show_desktop": ("cmd", "d"),
    "start_menu": ("cmd",),
    "lock_screen": ("cmd", "l"),
    "snap_left": ("cmd", "left"),
    "snap_right": ("cmd", "right"),
    "maximize": ("cmd", "up"),
    "minimize": ("cmd", "down"),
    "next_desktop": ("ctrl", "cmd", "right"),
    "prev_desktop": ("ctrl", "cmd", "left"),
    "close_window": ("alt", "f4"),
    "voice_typing": ("cmd", "h"),
    # Navigation
    "next_tab": ("ctrl", "tab"),
    "prev_tab": ("ctrl", "shift", "tab"),
    "new_tab": ("ctrl", "t"),
    "close_tab": ("ctrl", "w"),
    "back": ("alt", "left"),
    "forward": ("alt", "right"),
    "enter": ("enter",),
    "escape": ("esc",),
    # Editing
    "copy": ("ctrl", "c"),
    "paste": ("ctrl", "v"),
    "cut": ("ctrl", "x"),
    "undo": ("ctrl", "z"),
    "redo": ("ctrl", "y"),
    "save": ("ctrl", "s"),
    "command_palette": ("ctrl", "shift", "p"),
    "zoom_in": ("ctrl", "="),
    "zoom_out": ("ctrl", "-"),
    # Media
    "play_pause": ("media_play_pause",),
    "next_track": ("media_next",),
    "prev_track": ("media_previous",),
    "volume_up": ("media_volume_up",),
    "volume_down": ("media_volume_down",),
    "mute": ("media_volume_mute",),
}


def run_action(actuator, name: str | None) -> bool:
    """Send the key combination for ``name``. None (an unbound gesture) does nothing."""
    if not name:
        return False
    keys = ACTIONS.get(name)
    if keys is None:
        logger.warning("Unknown action %r — see core/actions.py for the list", name)
        return False
    actuator.press_combo(*keys)
    logger.debug("Action %s %s", name, "+".join(keys))
    return True


def validate_bindings(bindings: dict[str, str | None], setting: str) -> None:
    """Log a warning for every binding that names an unknown action."""
    for gesture, action in bindings.items():
        if action is not None and action not in ACTIONS:
            logger.warning("%s[%r] = %r is not a known action", setting, gesture, action)
