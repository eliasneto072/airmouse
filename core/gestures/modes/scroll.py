# core/gestures/modes/scroll.py
"""SCROLL mode: flick the hand up / down to scroll (or joystick style), pinch to zoom."""

from __future__ import annotations

from config import (
    HSCROLL_ENABLED,
    SCROLL_DEADZONE,
    SCROLL_MAX_RATE,
    SCROLL_SPEED,
    SCROLL_STYLE,
    SCROLL_TICKS_PER_HAND_LENGTH,
    ZOOM_MAX_RATE,
    ZOOM_SPEED,
    ZOOM_STEPS_PER_HAND_LENGTH,
)
from core.actions import run_action
from core.gestures.modes.base import ModeHandler
from core.gestures.motion import RateAccumulator, StrokeTracker
from core.gestures.poses import HandPose, Pose


class ScrollMode(ModeHandler):
    """
    stroke (default): a quick move of the hand up / down scrolls up / down by an
      amount proportional to the movement (SCROLL_TICKS_PER_HAND_LENGTH, at least
      one tick); left / right scrolls sideways. Slow movements are ignored, so you
      can bring the hand back and flick again. Thumb + index pinched while moving
      up / down zooms in / out.

    joystick: where the hand is when the mode starts (or resumes after a fist) is
      the center; the hand above / below it scrolls continuously, further = faster.

    Any hand shape works (the mode is locked). The cursor does not move.
    """

    name = "scroll"

    def __init__(self, actuator, style: str = SCROLL_STYLE, hscroll: bool = HSCROLL_ENABLED) -> None:
        if style not in ("stroke", "joystick"):
            raise ValueError(f"SCROLL_STYLE must be 'stroke' or 'joystick', not {style!r}")
        self._actuator = actuator
        self._style = style
        self._hscroll = hscroll
        # stroke style
        self._strokes = StrokeTracker(SCROLL_TICKS_PER_HAND_LENGTH, horizontal=hscroll)
        self._zoom_strokes = StrokeTracker(ZOOM_STEPS_PER_HAND_LENGTH, horizontal=False)
        # joystick style
        self._vertical = RateAccumulator(SCROLL_DEADZONE, SCROLL_SPEED, SCROLL_MAX_RATE)
        self._horizontal = RateAccumulator(SCROLL_DEADZONE, SCROLL_SPEED, SCROLL_MAX_RATE)
        self._zoom = RateAccumulator(SCROLL_DEADZONE, ZOOM_SPEED, ZOOM_MAX_RATE)
        self._center: tuple[float, float] | None = None
        self._last: float | None = None

    def enter(self, hand: HandPose, now: float) -> None:
        self._center = hand.anchor
        self._last = now
        self._reset()

    def exit(self) -> None:
        self._center = None
        self._reset()

    def _reset(self) -> None:
        self._strokes.reset()
        self._zoom_strokes.reset()
        self._vertical.reset()
        self._horizontal.reset()
        self._zoom.reset()

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        if self._style == "stroke":
            self._process_strokes(hand, now)
        else:
            self._process_joystick(hand, now)

    # ── stroke style ──────────────────────────────────────────────────────────

    def _process_strokes(self, hand: HandPose, now: float) -> None:
        if hand.pinch_index:
            self._strokes.reset()
            _, steps = self._zoom_strokes.update(hand, now)
            self._zoom_steps(steps)
            return
        self._zoom_strokes.reset()
        x_steps, y_steps = self._strokes.update(hand, now)
        if y_steps:
            self._actuator.scroll(y_steps)   # positive = up
        if x_steps:
            self._actuator.hscroll(x_steps)  # positive = right

    # ── joystick style ────────────────────────────────────────────────────────

    def _process_joystick(self, hand: HandPose, now: float) -> None:
        dt = 0.0 if self._last is None else now - self._last
        self._last = now
        if self._center is None:
            self._center = hand.anchor
        dx = (hand.anchor[0] - self._center[0]) / hand.scale
        dy = (hand.anchor[1] - self._center[1]) / hand.scale  # image y grows downwards

        if hand.pinch_index:
            self._vertical.reset()
            self._horizontal.reset()
            self._zoom_steps(self._zoom.update(-dy, dt))
            return

        self._zoom.reset()
        if self._hscroll and abs(dx) > abs(dy):
            self._vertical.reset()
            ticks = self._horizontal.update(dx, dt)
            if ticks:
                self._actuator.hscroll(ticks)
        else:
            self._horizontal.reset()
            ticks = self._vertical.update(-dy, dt)
            if ticks:
                self._actuator.scroll(ticks)

    def _zoom_steps(self, steps: int) -> None:
        for _ in range(abs(steps)):
            run_action(self._actuator, "zoom_in" if steps > 0 else "zoom_out")
