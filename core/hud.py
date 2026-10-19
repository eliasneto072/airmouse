# core/hud.py
"""
On-screen HUD for the modal mode: a small always-on-top label with the current
mode, the progress of a pending hold (starting a mode, turning off) and whether
the hand is visible. It is click-through and hidden from the taskbar.

The HUD runs its own Tk event loop in a daemon thread. update() only stores the
latest status, so the camera loop never waits on the UI. If Tk cannot start, the
HUD disables itself with a warning instead of stopping the app.
"""

from __future__ import annotations

import ctypes
import gc
import logging
import threading

from config import HUD_POSITION
from core.gestures.mode_manager import ModalStatus, Mode

logger = logging.getLogger(__name__)

POSITIONS = ("bottom-right", "bottom-left", "top-right", "top-left")

BACKGROUND = "#1d1f24"
TEXT = "#f2f3f5"
MUTED = "#a3a8b3"
HAND_MISSING = "#4a4d55"
SUPPORT = "#f2c94c"  # left-hand badge

STYLE: dict[Mode, tuple[str, str]] = {
    Mode.DISARMED: ("OFF", "#8a8f98"),
    Mode.MOVE: ("MOVE", "#4c8dff"),
    Mode.SCROLL: ("SCROLL", "#3fbf7f"),
    Mode.SHORTCUTS: ("SHORTCUTS", "#f2a33a"),
    Mode.MEDIA: ("MEDIA", "#a970ff"),
    Mode.WINDOWS: ("WINDOWS", "#2bb3c0"),
}

# Win32 extended window styles
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000


def _pending_text(status: ModalStatus) -> tuple[str, str]:
    """(text, color) describing the hold in progress."""
    if status.pending == "choose":
        return "show 1–5 fingers", MUTED
    if status.pending == "look":
        return "look at the screen", MUTED
    if status.pending == "away":
        return "not looking", MUTED
    if status.pending == "attention":
        return "look check on/off…", SUPPORT
    if status.pending == "disarm":
        return "paused · hold = off", STYLE[Mode.DISARMED][1]
    if status.pending:
        label, color = STYLE[Mode(status.pending)]
        return f"→ {label}", color
    if status.paused:
        return "paused", MUTED
    return "", MUTED


class Hud:
    def __init__(self, position: str = HUD_POSITION) -> None:
        if position not in POSITIONS:
            raise ValueError(f"HUD_POSITION must be one of {POSITIONS}, not {position!r}")
        self._position = position
        self._lock = threading.Lock()
        self._latest: ModalStatus | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="hud")
        self._thread.start()

    def update(self, status: ModalStatus) -> None:
        with self._lock:
            self._latest = status

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    # ── Tk thread ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg=BACKGROUND)

            scale = root.winfo_fpixels("1i") / 96.0  # the process is DPI-aware
            width, height = int(250 * scale), int(38 * scale)
            canvas = tk.Canvas(root, width=width, height=height, bg=BACKGROUND, highlightthickness=0, bd=0)
            canvas.pack()

            screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
            margin, taskbar = int(16 * scale), int(60 * scale)
            x = screen_w - width - margin if self._position.endswith("right") else margin
            y = screen_h - height - taskbar if self._position.startswith("bottom") else margin
            root.geometry(f"{width}x{height}+{x}+{y}")
            root.update_idletasks()
            self._make_click_through(root)
            root.attributes("-alpha", 0.9)
        except Exception as exc:  # no display, Tk missing, …
            logger.warning("HUD disabled: %s", exc)
            return

        last: list[ModalStatus | None] = [None]
        frames = [0]

        def tick() -> None:
            if self._stop.is_set():
                root.destroy()
                return
            with self._lock:
                status = self._latest
            if status is not None and status != last[0]:
                self._draw(canvas, status, width, height, scale)
                last[0] = status
            frames[0] += 1
            if frames[0] % 60 == 0:  # other always-on-top windows can cover it
                root.attributes("-topmost", True)
            root.after(33, tick)

        root.after(0, tick)
        try:
            root.mainloop()
        except Exception as exc:
            logger.warning("HUD stopped: %s", exc)
        finally:
            # Tk objects must be freed in the thread that created them, otherwise
            # Tcl aborts at interpreter exit ("async handler deleted by the wrong thread").
            del tick, canvas, root
            gc.collect()

    @staticmethod
    def _make_click_through(root) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(root.winfo_id())
            style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
        except Exception as exc:
            logger.debug("Could not make the HUD click-through: %s", exc)

    @staticmethod
    def _draw(canvas, status: ModalStatus, width: int, height: int, scale: float) -> None:
        label, color = STYLE[status.mode]
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width - 1, height - 1, fill=BACKGROUND, outline=color, width=max(1, round(2 * scale)))

        mid = height / 2
        r = 5 * scale
        dot_x = 16 * scale
        canvas.create_oval(
            dot_x - r, mid - r, dot_x + r, mid + r,
            fill=color if status.hand_visible else HAND_MISSING, outline="",
        )
        label_id = canvas.create_text(30 * scale, mid, text=label, anchor="w", fill=TEXT, font=("Segoe UI", 10, "bold"))
        hint, hint_color = _pending_text(status)
        if status.support and not hint:  # the hint is temporary and takes the same space
            right = canvas.bbox(label_id)[2]
            canvas.create_text(
                right + 8 * scale, mid, text=status.support, anchor="w", fill=SUPPORT, font=("Segoe UI", 9, "bold")
            )

        if hint:
            canvas.create_text(width - 10 * scale, mid, text=hint, anchor="e", fill=hint_color, font=("Segoe UI", 9))
        if status.progress > 0:
            bar = max(1, round(3 * scale))
            canvas.create_rectangle(0, height - bar, width * status.progress, height, fill=hint_color, outline="")
