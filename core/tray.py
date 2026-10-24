# core/tray.py
"""
System-tray icon: AirMouse runs without a terminal window.

The icon's colour follows the current mode (grey = OFF, blue = MOVE, …) and
its menu pauses gestures, toggles the look check and "Start with Windows",
opens the settings page (in the browser) or the log, and quits cleanly
(restoring the Windows settings main.py changed). Needs `pystray`; without it
AirMouse runs as before.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import webbrowser

from core import paths, startup
from core.app_control import AppControl
from core.icon import MODE_COLORS, draw_icon

logger = logging.getLogger(__name__)

APP_DIR = paths.SOURCE_DIR

CONFIG_TEMPLATE = """\
# config_local.py — your personal AirMouse settings (git-ignored).
# Any setting from config.py can be overridden here; restart AirMouse to apply.
# Examples:
#   CAMERA_INDEX = 1
#   INTERACTION_MODE = "modal"
#   POINTER_SPEED = 400
#   ATTENTION_GATE = "off"
"""


class Tray:
    def __init__(self, control: AppControl, log_file: str | None = None) -> None:
        self._control = control
        self._log_file = log_file
        self._icon = None
        self._key = None
        self._thread: threading.Thread | None = None

    # ── Life cycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        try:
            import pystray
        except ImportError:
            logger.warning("Tray icon disabled: install it with  pip install pystray")
            return False

        item = pystray.MenuItem
        c = self._control
        menu = pystray.Menu(
            item(lambda _: f"AirMouse — {c.status_text()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Pause gestures", self._toggle_pause, checked=lambda _: c.paused),
            item(
                "Look check",
                lambda: c.toggle_attention(),
                checked=lambda _: c.attention_on,
                visible=lambda _: c.attention_available,
            ),
            item("Start with Windows", self._toggle_startup, checked=lambda _: self._startup_enabled()),
            pystray.Menu.SEPARATOR,
            item("Settings…", self._open_settings, default=True),
            item("Open log", self._open_log, visible=lambda _: bool(self._log_file)),
            item("Advanced: edit config_local.py", self._open_config_local, visible=lambda _: not paths.FROZEN),
            pystray.Menu.SEPARATOR,
            item("Quit AirMouse", self._quit),
        )
        self._key = c.status_key()
        self._icon = pystray.Icon("AirMouse", self._image(self._key), f"AirMouse — {c.status_text()}", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="tray")
        self._thread.start()
        return True

    def notify(self, message: str) -> None:
        try:
            if self._icon is not None:
                self._icon.notify(message, "AirMouse")
        except Exception as exc:  # notifications are best-effort
            logger.debug("Tray notification failed: %s", exc)

    def refresh(self) -> None:
        """Call from the camera loop now and then: recolours the icon when the mode changes."""
        if self._icon is None:
            return
        key = self._control.status_key()
        if key == self._key:
            return
        self._key = key
        try:
            self._icon.icon = self._image(key)
            self._icon.title = f"AirMouse — {self._control.status_text()}"
            self._icon.update_menu()
        except Exception as exc:
            logger.debug("Tray refresh failed: %s", exc)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    # ── Menu actions ──────────────────────────────────────────────────────────

    @staticmethod
    def _image(key: str):
        return draw_icon(MODE_COLORS.get(key, MODE_COLORS["move"]), 64, paused=key == "paused")

    def _toggle_pause(self) -> None:
        self._control.toggle_pause()
        self.refresh()

    @staticmethod
    def _startup_enabled() -> bool:
        try:
            return startup.is_enabled()
        except Exception:
            return False

    def _toggle_startup(self) -> None:
        try:
            if startup.is_enabled():
                startup.disable()
                self.notify("AirMouse will no longer start with Windows.")
            else:
                startup.enable()
                self.notify("AirMouse will start automatically when you sign in.")
        except Exception as exc:
            logger.warning("Could not change 'Start with Windows': %s", exc)

    def _open_settings(self) -> None:
        """The settings page in the browser (a left click on the icon does this too)."""
        if self._control.settings_url:
            webbrowser.open(self._control.settings_url + "#settings")
        else:
            self._open_config_local()

    def _open_config_local(self) -> None:
        path = APP_DIR / "config_local.py"
        if not path.exists():
            path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        # Notepad explicitly: opening a .py file directly may *run* it with Python.
        subprocess.Popen(["notepad.exe", str(path)])

    def _open_log(self) -> None:
        if self._log_file:
            subprocess.Popen(["notepad.exe", str(paths.data(self._log_file))])

    def _quit(self) -> None:
        logger.info("Quit from the tray icon")
        self._control.stop.set()
        self.stop()
