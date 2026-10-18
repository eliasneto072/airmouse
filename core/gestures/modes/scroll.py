# core/gestures/modes/scroll.py
"""SCROLL mode (✌️): joystick-style vertical/horizontal scroll and pinch-zoom."""

from __future__ import annotations

from config import (
    HSCROLL_ENABLED,
    SCROLL_DEADZONE,
    SCROLL_MAX_RATE,
    SCROLL_SPEED,
    ZOOM_MAX_RATE,
    ZOOM_SPEED,
)
from core.actions import run_action
from core.gestures.modes.base import ModeHandler
from core.gestures.motion import RateAccumulator
from core.gestures.poses import HandPose, Pose


class ScrollMode(ModeHandler):
    """
    Where the hand is when the mode starts (or resumes after a fist) is the
    center. With ✌️ held, the hand above / below the center scrolls up / down,
    left / right scrolls horizontally (dominant axis only); further from the
    center = faster. Pinching thumb + index turns up / down into zoom in / out.
    The cursor does not move in this mode.
    """

    name = "scroll"

    def __init__(self, actuator, hscroll: bool = HSCROLL_ENABLED) -> None:
        self._actuator = actuator
        self._hscroll = hscroll
        self._vertical = RateAccumulator(SCROLL_DEADZONE, SCROLL_SPEED, SCROLL_MAX_RATE)
        self._horizontal = RateAccumulator(SCROLL_DEADZONE, SCROLL_SPEED, SCROLL_MAX_RATE)
        self._zoom = RateAccumulator(SCROLL_DEADZONE, ZOOM_SPEED, ZOOM_MAX_RATE)
        self._center: tuple[float, float] | None = None
        self._last: float | None = None

    def enter(self, hand: HandPose, now: float) -> None:
        self._center = hand.anchor
        self._last = now
        self._reset_rates()

    def exit(self) -> None:
        self._center = None
        self._reset_rates()

    def _reset_rates(self) -> None:
        self._vertical.reset()
        self._horizontal.reset()
        self._zoom.reset()

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        dt = 0.0 if self._last is None else now - self._last
        self._last = now
        if self._center is None:
            self._center = hand.anchor
        if pose != Pose.TWO and not hand.pinch_index:
            self._reset_rates()
            return

        # Displacement from the center in hand lengths; y grows downwards.
        dx = (hand.anchor[0] - self._center[0]) / hand.scale
        dy = (hand.anchor[1] - self._center[1]) / hand.scale

        if hand.pinch_index:
            self._vertical.reset()
            self._horizontal.reset()
            steps = self._zoom.update(-dy, dt)
            for _ in range(abs(steps)):
                run_action(self._actuator, "zoom_in" if steps > 0 else "zoom_out")
            return

        self._zoom.reset()
        if self._hscroll and abs(dx) > abs(dy):
            self._vertical.reset()
            ticks = self._horizontal.update(dx, dt)
            if ticks:
                self._actuator.hscroll(ticks)
        else:
            self._horizontal.reset()
            ticks = self._vertical.update(-dy, dt)  # hand above center → scroll up
            if ticks:
                self._actuator.scroll(ticks)
