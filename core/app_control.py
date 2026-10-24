# core/app_control.py
"""State shared between the camera loop (main thread), the tray icon and the settings page."""

from __future__ import annotations

import threading


class AppControl:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.paused = False
        self.processor = None  # set by main.py once the gesture pipeline exists
        self.actuator = None
        # Written by the camera loop, read by the settings page (preview, status)
        self.latest_frame = None
        self.latest_hands = None
        self.fps = 0.0
        # Settings page
        self.settings_url: str | None = None
        self.restart_requested = False
        self.camera_error: str | None = None  # the camera could not be opened (the page offers another)

    # ── Pause ─────────────────────────────────────────────────────────────────

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    # ── Restart (to apply saved settings) ─────────────────────────────────────

    def request_restart(self) -> None:
        """Stop the camera loop; main.py then starts a fresh AirMouse that reads the new settings."""
        self.restart_requested = True
        self.stop.set()

    # ── Look check (modal mode only) ──────────────────────────────────────────

    @property
    def attention_available(self) -> bool:
        return bool(getattr(self.processor, "attention_available", False))

    @property
    def attention_on(self) -> bool:
        return bool(getattr(self.processor, "attention_on", False))

    def toggle_attention(self) -> None:
        if self.attention_available:
            self.processor.toggle_attention()

    # ── Status for the tray ───────────────────────────────────────────────────

    def status_key(self) -> str:
        """Key into core.icon.MODE_COLORS: "paused", "classic" or the modal mode."""
        if self.paused:
            return "paused"
        status = getattr(self.processor, "status", None)
        if status is None:
            return "classic"
        return status.mode.value

    def status_text(self) -> str:
        key = self.status_key()
        return {"paused": "Paused", "classic": "Classic mode", "disarmed": "OFF"}.get(key, key.upper())
