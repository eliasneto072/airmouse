# core/gestures/motion.py
"""Small motion helpers shared by the modal modes."""

from __future__ import annotations

import math

from config import SWIPE_REARM_VELOCITY, SWIPE_VELOCITY
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
