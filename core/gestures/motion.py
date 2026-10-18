# core/gestures/motion.py
"""Small motion helpers shared by the modal modes."""

from __future__ import annotations

import math

from config import (
    STROKE_END_VELOCITY,
    STROKE_RETURN_IGNORE_S,
    STROKE_START_VELOCITY,
    SWIPE_REARM_VELOCITY,
    SWIPE_VELOCITY,
)
from core.gestures.poses import HandPose


class SwipeDetector:
    """
    Fires once per quick flick of the hand. Directions are in user space:
    "swipe_right" is the user's right. After firing, the hand has to slow down
    below ``rearm`` before another swipe can fire.
    """

    def __init__(self, threshold: float = SWIPE_VELOCITY, rearm: float = SWIPE_REARM_VELOCITY) -> None:
        self._threshold = threshold
        self._rearm = rearm
        self.reset()

    def reset(self) -> None:
        self._prev: tuple[float, float, float] | None = None
        self._vx = 0.0
        self._vy = 0.0
        self._ready = True

    def update(self, hand: HandPose, now: float) -> str | None:
        x, y = hand.anchor
        if self._prev is None:
            self._prev = (x, y, now)
            return None
        px, py, pt = self._prev
        self._prev = (x, y, now)
        dt = max(now - pt, 1e-3)
        # Light smoothing: one noisy frame should not look like a flick.
        self._vx = 0.5 * self._vx + 0.5 * (x - px) / hand.scale / dt
        self._vy = 0.5 * self._vy + 0.5 * (y - py) / hand.scale / dt
        speed = math.hypot(self._vx, self._vy)

        if not self._ready:
            if speed < self._rearm:
                self._ready = True
            return None
        if speed < self._threshold:
            return None
        self._ready = False
        if abs(self._vx) >= abs(self._vy):
            return "swipe_right" if self._vx > 0 else "swipe_left"
        return "swipe_down" if self._vy > 0 else "swipe_up"


class StrokeTracker:
    """
    Turns quick hand movements ("strokes") into proportional steps — the gesture
    version of a scroll wheel.

    - A stroke starts when the hand moves faster than ``start_velocity`` and ends
      when it slows below ``end_velocity``. Slow movements never count, so the
      hand can be brought back without undoing the stroke.
    - The stroke is locked to the axis it started on. While it lasts, movement
      along that axis is converted into steps (``steps_per_hand_length``); a
      stroke always produces at least one step.
    - A stroke in the opposite direction that starts within ``return_ignore_s``
      of the previous one is the hand coming back quickly, and is ignored.

    update() returns ``(x_steps, y_steps)`` in user space: +x = right, +y = up.
    """

    def __init__(
        self,
        steps_per_hand_length: float,
        start_velocity: float = STROKE_START_VELOCITY,
        end_velocity: float = STROKE_END_VELOCITY,
        return_ignore_s: float = STROKE_RETURN_IGNORE_S,
        horizontal: bool = True,
    ) -> None:
        self.steps_per_hand_length = steps_per_hand_length
        self._start_v = start_velocity
        self._end_v = end_velocity
        self._return_ignore_s = return_ignore_s
        self._horizontal = horizontal
        self.reset()

    def reset(self) -> None:
        self._prev: tuple[float, float, float] | None = None
        self._vx = 0.0
        self._vy = 0.0
        self._axis: str | None = None      # "x" / "y" while a stroke is in progress
        self._sign = 0
        self._ignored = False
        self._acc = 0.0
        self._emitted = 0
        self._last_end: tuple[float, str, int] | None = None  # (time, axis, sign) of the last real stroke

    def update(self, hand: HandPose, now: float) -> tuple[int, int]:
        x, y = hand.anchor
        if self._prev is None:
            self._prev = (x, y, now)
            return 0, 0
        px, py, pt = self._prev
        self._prev = (x, y, now)
        dt = max(now - pt, 1e-3)
        dx = (x - px) / hand.scale            # + = right
        dy = (py - y) / hand.scale            # + = up (image y grows downwards)
        self._vx = 0.5 * self._vx + 0.5 * dx / dt
        self._vy = 0.5 * self._vy + 0.5 * dy / dt
        if not self._horizontal:
            self._vx = 0.0
        speed = math.hypot(self._vx, self._vy)

        if self._axis is None:
            if speed < self._start_v:
                return 0, 0
            self._axis = "x" if abs(self._vx) > abs(self._vy) else "y"
            self._sign = 1 if (self._vx if self._axis == "x" else self._vy) > 0 else -1
            last = self._last_end
            self._ignored = (
                last is not None
                and now - last[0] < self._return_ignore_s
                and last[1] == self._axis
                and last[2] == -self._sign
            )
            self._acc = 0.0
            self._emitted = 0

        axis = self._axis
        steps = 0
        if not self._ignored:
            along = dx if axis == "x" else dy
            if along * self._sign > 0:
                self._acc += along * self.steps_per_hand_length
                steps = int(self._acc)
                self._acc -= steps
                self._emitted += steps

        if speed < self._end_v:
            if not self._ignored:
                if self._emitted == 0:
                    steps += self._sign  # every stroke does something
                self._last_end = (now, axis, self._sign)
            self._axis = None

        return (steps, 0) if axis == "x" else (0, steps)


class RateAccumulator:
    """
    Joystick helper: turns a displacement beyond a dead zone into a steady
    stream of whole steps (scroll ticks, volume steps…). Speed grows with the
    displacement; the first step fires as soon as the dead zone is left.
    """

    def __init__(self, deadzone: float, speed: float, max_rate: float) -> None:
        self._deadzone = deadzone
        self._speed = speed
        self._max_rate = max_rate
        self._acc = 0.0

    def reset(self) -> None:
        self._acc = 0.0

    def update(self, displacement: float, dt: float) -> int:
        excess = abs(displacement) - self._deadzone
        if excess <= 0:
            self._acc = 0.0
            return 0
        if self._acc == 0.0 or math.copysign(1.0, self._acc) != math.copysign(1.0, displacement):
            self._acc = math.copysign(0.999, displacement)  # respond immediately
        rate = min(self._max_rate, excess * self._speed)
        self._acc += math.copysign(rate * dt, displacement)
        steps = int(self._acc)  # truncates toward zero
        self._acc -= steps
        if self._acc == 0.0:
            self._acc = math.copysign(1e-9, displacement)
        return steps
