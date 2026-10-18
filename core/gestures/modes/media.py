# core/gestures/modes/media.py
"""MEDIA mode: volume strokes, play/pause, mute, tracks."""

from __future__ import annotations

from config import MEDIA_BINDINGS, VOLUME_STEPS_PER_HAND_LENGTH
from core.actions import run_action, validate_bindings
from core.gestures.modes.base import ModeHandler, PinchEdges
from core.gestures.motion import StrokeTracker, SwipeDetector
from core.gestures.poses import HandPose, Pose


class MediaMode(ModeHandler):
    """
    A quick move of the hand up / down raises / lowers the volume (proportional
    to the movement, at least one step). Left / right flicks and thumb taps fire
    MEDIA_BINDINGS (previous / next track, play / pause, mute by default). Any
    hand shape works (the mode is locked).
    """

    name = "media"

    def __init__(self, actuator, bindings: dict[str, str | None] | None = None) -> None:
        self._actuator = actuator
        self._bindings = dict(MEDIA_BINDINGS if bindings is None else bindings)
        validate_bindings(self._bindings, "MEDIA_BINDINGS")
        self._volume = StrokeTracker(VOLUME_STEPS_PER_HAND_LENGTH, horizontal=False)
        self._swipes = SwipeDetector()
        self._pinches = PinchEdges()

    def enter(self, hand: HandPose, now: float) -> None:
        self._volume.reset()
        self._swipes.reset()
        self._pinches.reset()
        self._pinches.update(hand)  # a pinch already held when entering does not fire

    def exit(self) -> None:
        self._volume.reset()
        self._swipes.reset()
        self._pinches.reset()

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        swipe = self._swipes.update(hand, now)
        if swipe in ("swipe_left", "swipe_right"):
            run_action(self._actuator, self._bindings.get(swipe))

        index_tap, middle_tap = self._pinches.update(hand)
        if index_tap:
            run_action(self._actuator, self._bindings.get("pinch_index"))
        if middle_tap:
            run_action(self._actuator, self._bindings.get("pinch_middle"))

        _, steps = self._volume.update(hand, now)
        if hand.any_pinch:
            return
        for _ in range(abs(steps)):
            run_action(self._actuator, "volume_up" if steps > 0 else "volume_down")
