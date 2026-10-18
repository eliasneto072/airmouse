# core/gestures/modes/base.py
"""Interface every modal mode implements."""

from __future__ import annotations

from core.gestures.poses import HandPose, Pose


class ModeHandler:
    """
    Life cycle, driven by ModeManager:

        enter → process* → (pause → resume)* → exit

    Invariant: after exit(), pause() or hand_lost() the mode holds no mouse
    button or key.
    """

    name = "base"

    def enter(self, hand: HandPose, now: float) -> None:
        pass

    def exit(self) -> None:
        pass

    def pause(self, now: float) -> None:
        """Fist: stop acting. Default: same as exit()."""
        self.exit()

    def resume(self, hand: HandPose, now: float) -> None:
        """Fist released (or hand back after being lost). Default: start fresh."""
        self.enter(hand, now)

    def hand_lost(self) -> None:
        self.exit()

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        pass

    @property
    def busy(self) -> bool:
        """True while an interaction is in progress (e.g. dragging): blocks mode switches."""
        return False


class PinchEdges:
    """Turns pinch flags into one-shot "pinch started" events."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._index = False
        self._middle = False

    def update(self, hand: HandPose) -> tuple[bool, bool]:
        index_started = hand.pinch_index and not self._index
        middle_started = hand.pinch_middle and not self._middle
        self._index = hand.pinch_index
        self._middle = hand.pinch_middle
        return index_started, middle_started
