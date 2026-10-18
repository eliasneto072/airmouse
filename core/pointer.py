# core/pointer.py
"""
Cursor control from a hand anchor point.

relative (default): like a trackpad. Hand movement is measured in hand lengths,
  so it feels the same near or far from the camera, then multiplied by
  POINTER_SPEED and an acceleration curve: slow movements are precise, quick
  ones cross the screen. reset() re-anchors without moving the cursor, which is
  how the fist "clutch" (lifting the mouse) works.

absolute: the anchor's position inside the TRACKPAD_MARGIN zone of the camera
  frame is the cursor position (the classic behaviour).

freeze() stops the cursor and, optionally, rolls it back to where it was
CLICK_ROLLBACK_S ago — the thumb travelling towards the index during a pinch
drags the hand slightly, and the click should land where the user aimed.
"""

from __future__ import annotations

import math
from collections import deque

from config import (
    CAMERA_FPS,
    CLICK_ROLLBACK_S,
    CURSOR_MAPPING,
    ONE_EURO_BETA,
    ONE_EURO_DCUTOFF,
    ONE_EURO_MINCUTOFF,
    POINTER_ACCEL,
    POINTER_FILTER_BETA,
    POINTER_FILTER_MINCUTOFF,
    POINTER_MAX_GAIN,
    POINTER_MIN_SPEED,
    POINTER_SPEED,
)
from core.display import TrackpadZone, VirtualDesktop, map_to_desktop
from core.filter import OneEuroFilter
from core.gestures.poses import HandPose


class Pointer:
    def __init__(
        self,
        actuator,
        desktop: VirtualDesktop,
        trackpad: TrackpadZone,
        mapping: str = CURSOR_MAPPING,
        speed: float = POINTER_SPEED,
        accel: float = POINTER_ACCEL,
        max_gain: float = POINTER_MAX_GAIN,
        min_speed: float = POINTER_MIN_SPEED,
        rollback_s: float = CLICK_ROLLBACK_S,
    ) -> None:
        if mapping not in ("relative", "absolute"):
            raise ValueError(f"CURSOR_MAPPING must be 'relative' or 'absolute', not {mapping!r}")
        self._actuator = actuator
        self._desktop = desktop
        self._trackpad = trackpad
        self._mapping = mapping
        self._speed = speed
        self._accel = accel
        self._max_gain = max_gain
        self._min_speed = min_speed
        self._rollback_s = rollback_s
        self._history: deque[tuple[float, float, float]] = deque(maxlen=120)
        self._frozen = False
        self._pos: list[float] | None = None
        self.reset(sync=True)

    # ── State ─────────────────────────────────────────────────────────────────

    def reset(self, sync: bool = False) -> None:
        """
        Forget the previous anchor, so the next update() does not move the cursor.
        sync=True also re-reads the cursor position from the OS (the user may have
        moved the physical mouse meanwhile).
        """
        if self._mapping == "absolute":
            params = (ONE_EURO_MINCUTOFF, ONE_EURO_BETA)
        else:
            params = (POINTER_FILTER_MINCUTOFF, POINTER_FILTER_BETA)
        self._fx = OneEuroFilter(float(CAMERA_FPS), params[0], params[1], ONE_EURO_DCUTOFF)
        self._fy = OneEuroFilter(float(CAMERA_FPS), params[0], params[1], ONE_EURO_DCUTOFF)
        self._prev: tuple[float, float, float] | None = None
        if sync:
            self._pos = None

    @property
    def frozen(self) -> bool:
        return self._frozen

    def freeze(self, now: float, rollback: bool = True) -> None:
        if self._frozen:
            return
        self._frozen = True
        if rollback:
            past = self._position_at(now - self._rollback_s)
            if past is not None:
                self._set(past, now)

    def unfreeze(self) -> None:
        self._frozen = False

    @property
    def position(self) -> tuple[float, float] | None:
        """Last cursor position this pointer set (None before the first move)."""
        return None if self._pos is None else (self._pos[0], self._pos[1])

    def warp(self, xy: tuple[float, float], now: float) -> None:
        """Move the cursor to an exact position (e.g. the first click of a double click)."""
        self._set(xy, now)

    # ── Per frame ─────────────────────────────────────────────────────────────

    def update(self, hand: HandPose, now: float) -> None:
        if self._mapping == "absolute":
            fx = self._fx(hand.anchor_norm[0], now)
            fy = self._fy(hand.anchor_norm[1], now)
            if not self._frozen:
                self._set(map_to_desktop(fx, fy, self._trackpad, self._desktop), now)
            return

        fx = self._fx(hand.anchor[0], now)
        fy = self._fy(hand.anchor[1], now)
        if self._pos is None:
            x, y = self._actuator.position()
            self._pos = [float(x), float(y)]
        if self._prev is None:
            self._prev = (fx, fy, now)
            return

        px, py, pt = self._prev
        self._prev = (fx, fy, now)
        if self._frozen:
            return  # keep tracking the anchor so unfreezing does not jump

        dt = max(now - pt, 1e-3)
        dx = (fx - px) / hand.scale
        dy = (fy - py) / hand.scale
        speed = math.hypot(dx, dy) / dt  # hand lengths per second
        if speed < self._min_speed:
            return
        gain = self._speed * min(self._max_gain, 1.0 + self._accel * speed)
        self._set((self._pos[0] + dx * gain, self._pos[1] + dy * gain), now)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _set(self, xy: tuple[float, float], now: float) -> None:
        x = min(max(xy[0], 0.0), self._desktop.total_width - 1.0)
        y = min(max(xy[1], 0.0), self._desktop.total_height - 1.0)
        self._pos = [x, y]
        self._actuator.move(int(round(x)), int(round(y)))
        self._history.append((now, x, y))

    def _position_at(self, t: float) -> tuple[float, float] | None:
        """Cursor position at time t (latest recorded position not after t)."""
        best = None
        for when, x, y in self._history:
            if when <= t:
                best = (x, y)
            else:
                break
        if best is None and self._history:
            _, x, y = self._history[0]
            best = (x, y)
        return best
