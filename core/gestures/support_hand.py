# core/gestures/support_hand.py
"""
Left hand (support hand) of the modal mode: system shortcuts while the right
hand drives the current mode.

- Ignored entirely while the system is OFF.
- A pose has to be held LEFT_HOLD_S (the open hand LEFT_PALM_HOLD_S) before its
  action fires, and fires once: change pose to fire again.
- ☝️ + a quick flick left / right / up / down fires the one_swipe_* bindings.
- "window_switcher": Alt+Tab with Alt kept down while the pose is held; thumb
  taps on the index / middle move to the next / previous window; dropping the
  pose releases Alt, which picks the highlighted window.
- "hold_ctrl": Ctrl is down while the pose is held and the right hand is in view,
  and only if the hand was seen closing (a fist that enters the frame already
  closed — a resting hand — never presses Ctrl).
- Poses in LEFT_NEEDS_FIST (the open hand by default, which is also how a
  resting hand looks) only fire right after a fist.
- Everything held is released when the pose changes, the hand leaves the frame,
  the system turns off, or after ALT_SWITCHER_MAX_S for the switcher.
"""

from __future__ import annotations

import logging

from config import (
    ALT_SWITCHER_MAX_S,
    HAND_LOST_RELEASE_S,
    LEFT_HAND_BINDINGS,
    LEFT_HOLD_S,
    LEFT_NEEDS_FIST,
    LEFT_PALM_HOLD_S,
)
from core.actions import run_action, validate_bindings
from core.gestures.modes.base import PinchEdges
from core.gestures.motion import SwipeDetector
from core.gestures.poses import HandPose, Pose
from core.gestures.stabilizer import PoseStabilizer

logger = logging.getLogger(__name__)

WINDOW_SWITCHER = "window_switcher"
HOLD_CTRL = "hold_ctrl"

_POSE_KEYS = {
    Pose.FIST: "fist",
    Pose.ONE: "one",
    Pose.TWO: "two",
    Pose.THREE: "three",
    Pose.FOUR: "four",
    Pose.FIVE: "five",
    Pose.OK: "ok",
}

_ACTION_LABELS = {
    "back": "← back",
    "forward": "forward →",
    "task_view": "task view",
    "show_desktop": "desktop",
    "start_menu": "start",
}


class SupportHand:
    def __init__(
        self,
        actuator,
        bindings: dict[str, str | None] | None = None,
        hold_s: float = LEFT_HOLD_S,
        palm_hold_s: float = LEFT_PALM_HOLD_S,
        switcher_max_s: float = ALT_SWITCHER_MAX_S,
        lost_release_s: float = HAND_LOST_RELEASE_S,
        needs_fist: tuple[str, ...] = LEFT_NEEDS_FIST,
    ) -> None:
        self._actuator = actuator
        self._bindings = dict(LEFT_HAND_BINDINGS if bindings is None else bindings)
        validate_bindings(self._bindings, "LEFT_HAND_BINDINGS", extra=(WINDOW_SWITCHER, HOLD_CTRL))
        self._hold_s = hold_s
        self._palm_hold_s = palm_hold_s
        self._switcher_max_s = switcher_max_s
        self._lost_release_s = lost_release_s
        self._needs_fist = set(needs_fist)
        self._stabilizer = PoseStabilizer()
        self._swipes = SwipeDetector()
        self._pinches = PinchEdges()
        self._ctrl = False
        self._switcher_since: float | None = None
        self._lost_since: float | None = None
        self._toast: tuple[str, float] | None = None
        self._reset_pose()

    def _reset_pose(self) -> None:
        self._pose = Pose.NONE
        self._pose_since = 0.0
        self._fired = False
        self._after_fist = False     # the current pose came straight from a fist
        self._closed_in_view = False  # the current fist was formed from an open pose

    # ── Public ────────────────────────────────────────────────────────────────

    def status_text(self, now: float) -> str | None:
        """Short label for the HUD: what the left hand is holding or just did."""
        if self._switcher_since is not None:
            return "ALT+TAB"
        if self._ctrl:
            return "CTRL"
        if self._toast is not None and now - self._toast[1] < 1.0:
            return self._toast[0]
        return None

    def release(self) -> None:
        """Let go of everything held (Alt, Ctrl)."""
        if self._switcher_since is not None:
            self._actuator.key_up("alt")
            self._switcher_since = None
        if self._ctrl:
            self._actuator.key_up("ctrl")
            self._ctrl = False

    def process(self, hand: HandPose | None, now: float, active: bool, dominant_visible: bool) -> None:
        """
        Args:
            hand:             the support hand this frame, or None
            active:           the system is on (a mode is active)
            dominant_visible: the right hand is in view (required to hold Ctrl)
        """
        if not active:
            self.release()
            self._stabilizer.reset()
            self._swipes.reset()
            self._pinches.reset()
            self._reset_pose()
            self._lost_since = None
            return

        if hand is None:
            if self._lost_since is None:
                self._lost_since = now
            if now - self._lost_since >= self._lost_release_s:
                self.release()
                self._stabilizer.reset()
                self._swipes.reset()
                self._reset_pose()
            return
        self._lost_since = None

        pose = self._stabilizer.update(hand.pose, now)
        if pose != self._pose:
            self.release()
            self._after_fist = self._pose == Pose.FIST
            self._closed_in_view = pose == Pose.FIST and self._pose in _POSE_KEYS
            self._pose = pose
            self._pose_since = now
            self._fired = False
            self._swipes.reset()
            self._pinches.reset()
            self._pinches.update(hand)

        key = _POSE_KEYS.get(pose)
        if key is None:
            return
        held_for = now - self._pose_since

        if pose == Pose.ONE:
            swipe = self._swipes.update(hand, now)
            if swipe:
                self._fire(self._bindings.get(f"one_{swipe}"), now)
            return

        action = self._bindings.get(key)
        if action is None:
            return

        if key in self._needs_fist and not self._after_fist:
            return

        if action == HOLD_CTRL:
            if not self._closed_in_view:
                return
            if dominant_visible and held_for >= self._hold_s and not self._ctrl:
                self._actuator.key_down("ctrl")
                self._ctrl = True
            elif not dominant_visible and self._ctrl:
                self._actuator.key_up("ctrl")
                self._ctrl = False
            return

        if action == WINDOW_SWITCHER:
            self._window_switcher(hand, held_for, now)
            return

        needed = self._palm_hold_s if pose == Pose.FIVE else self._hold_s
        if not self._fired and held_for >= needed:
            self._fired = True
            self._fire(action, now)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _fire(self, action: str | None, now: float) -> None:
        if run_action(self._actuator, action):
            self._toast = (_ACTION_LABELS.get(action, action.replace("_", " ")), now)

    def _window_switcher(self, hand: HandPose, held_for: float, now: float) -> None:
        index_tap, middle_tap = self._pinches.update(hand)
        if self._switcher_since is None:
            if not self._fired and held_for >= self._hold_s:
                self._fired = True
                self._actuator.key_down("alt")
                self._actuator.press_combo("tab")
                self._switcher_since = now
            return
        if now - self._switcher_since >= self._switcher_max_s:
            self.release()
            return
        if index_tap:
            self._actuator.press_combo("tab")
        if middle_tap:
            self._actuator.press_combo("shift", "tab")
