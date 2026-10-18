# core/gestures/stabilizer.py
"""Debouncing for per-frame pose classifications."""

from __future__ import annotations

from config import POSE_STABLE_S, POSE_NONE_STABLE_S
from core.gestures.poses import Pose


class PoseStabilizer:
    """
    Reports a pose only after it has been seen continuously for ``stable_s``.

    ``Pose.NONE`` (unrecognized) must persist for the longer ``none_stable_s``:
    a fast swipe or a pinch briefly blurs the hand, and that should not cancel
    the pose the user is actually holding.
    """

    def __init__(self, stable_s: float = POSE_STABLE_S, none_stable_s: float = POSE_NONE_STABLE_S) -> None:
        self._stable_s = stable_s
        self._none_stable_s = none_stable_s
        self.reset()

    def reset(self) -> None:
        self.pose = Pose.NONE
        self._candidate: Pose | None = None
        self._since = 0.0

    def update(self, pose: Pose, now: float) -> Pose:
        if pose == self.pose:
            self._candidate = None
            return self.pose
        if pose != self._candidate:
            self._candidate = pose
            self._since = now
        needed = self._none_stable_s if pose == Pose.NONE else self._stable_s
        if now - self._since >= needed:
            self.pose = pose
            self._candidate = None
        return self.pose
