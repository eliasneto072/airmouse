# core/gestures/modes/shortcuts.py
"""SHORTCUTS mode (3 fingers): swipes and pinches mapped to actions."""

from __future__ import annotations

from config import SHORTCUT_BINDINGS
from core.actions import run_action, validate_bindings
from core.gestures.modes.base import ModeHandler, PinchEdges
from core.gestures.motion import SwipeDetector
from core.gestures.poses import HandPose, Pose


class ShortcutsMode(ModeHandler):
    """
    A quick flick left / right / up / down or a thumb tap on the index / middle
    fires the bound action (SHORTCUT_BINDINGS), with any hand shape (the mode is
    locked). One-handed replacement for keyboard shortcuts while reclined.
    """

    name = "shortcuts"

    def __init__(self, actuator, bindings: dict[str, str | None] | None = None) -> None:
        self._actuator = actuator
        self._bindings = dict(SHORTCUT_BINDINGS if bindings is None else bindings)
        validate_bindings(self._bindings, "SHORTCUT_BINDINGS")
        self._swipes = SwipeDetector()
        self._pinches = PinchEdges()

    def enter(self, hand: HandPose, now: float) -> None:
        self._swipes.reset()
        self._pinches.reset()
        self._pinches.update(hand)  # a pinch already held when entering does not fire

    def exit(self) -> None:
        self._swipes.reset()
        self._pinches.reset()

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        swipe = self._swipes.update(hand, now)
        if swipe:
            run_action(self._actuator, self._bindings.get(swipe))
        index_tap, middle_tap = self._pinches.update(hand)
        if index_tap:
            run_action(self._actuator, self._bindings.get("pinch_index"))
        if middle_tap:
            run_action(self._actuator, self._bindings.get("pinch_middle"))
