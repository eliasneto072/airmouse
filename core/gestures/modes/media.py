# core/gestures/modes/media.py
"""MEDIA mode (4 fingers): volume joystick, play/pause, mute, tracks."""

from __future__ import annotations

from config import MEDIA_BINDINGS, VOLUME_DEADZONE, VOLUME_MAX_RATE, VOLUME_SPEED
from core.actions import run_action, validate_bindings
from core.gestures.modes.base import ModeHandler, PinchEdges
from core.gestures.motion import RateAccumulator, SwipeDetector
from core.gestures.poses import HandPose, Pose


class MediaMode(ModeHandler):
    """
    Open hand (4 fingers). Hand above / below where the mode started raises /
    lowers the volume (further = faster). Left / right flicks and thumb taps fire
    MEDIA_BINDINGS (previous / next track, play / pause, mute by default).
    """

    name = "media"
    # Thumb–index pinch with the other fingers extended is classified as OK.
    poses = (Pose.FOUR, Pose.OK)

    def __init__(self, actuator, bindings: dict[str, str | None] | None = None) -> None:
        self._actuator = actuator
        self._bindings = dict(MEDIA_BINDINGS if bindings is None else bindings)
        validate_bindings(self._bindings, "MEDIA_BINDINGS")
        self._volume = RateAccumulator(VOLUME_DEADZONE, VOLUME_SPEED, VOLUME_MAX_RATE)
        self._swipes = SwipeDetector()
        self._pinches = PinchEdges()
        self._center: tuple[float, float] | None = None
        self._last: float | None = None

    def enter(self, hand: HandPose, now: float) -> None:
        self._center = hand.anchor
        self._last = now
        self._volume.reset()
        self._swipes.reset()
        self._pinches.reset()
        self._pinches.update(hand)

    def exit(self) -> None:
        self._center = None
        self._volume.reset()
        self._swipes.reset()
        self._pinches.reset()

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        dt = 0.0 if self._last is None else now - self._last
        self._last = now
        if self._center is None:
            self._center = hand.anchor
        if pose not in self.poses:
            self._volume.reset()
            self._swipes.reset()
            self._pinches.update(hand)
            return

        swipe = self._swipes.update(hand, now)
        if swipe in ("swipe_left", "swipe_right"):
            run_action(self._actuator, self._bindings.get(swipe))

        index_tap, middle_tap = self._pinches.update(hand)
        if index_tap:
            run_action(self._actuator, self._bindings.get("pinch_index"))
        if middle_tap:
            run_action(self._actuator, self._bindings.get("pinch_middle"))
        if hand.any_pinch:
            self._volume.reset()
            return

        dy = (hand.anchor[1] - self._center[1]) / hand.scale
        steps = self._volume.update(-dy, dt)  # hand above center → louder
        for _ in range(abs(steps)):
            run_action(self._actuator, "volume_up" if steps > 0 else "volume_down")
