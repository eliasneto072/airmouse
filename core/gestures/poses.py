# core/gestures/poses.py
"""
Scale- and rotation-invariant hand pose classification.

All geometry is computed in pixel space (normalized coordinates × frame size, so
the 16:9 aspect ratio does not distort distances) and expressed in *hand lengths*
(wrist → middle-finger MCP). Thresholds therefore mean the same thing whether the
hand is close to the camera or far away, and whether it is upright or tilted.

Finger counting uses index → pinky only: MediaPipe's thumb extension is too
unreliable to tell poses apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from config import (
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CURSOR_ANCHOR_LANDMARK,
    FINGER_EXTEND_RATIO,
    FIST_TIP_RADIUS,
    PINCH_INDEX_ENTER_RATIO,
    PINCH_INDEX_EXIT_RATIO,
    PINCH_MIDDLE_ENTER_RATIO,
    PINCH_MIDDLE_EXIT_RATIO,
)
from core.tracker import Landmark

WRIST, THUMB_TIP, MIDDLE_MCP = 0, 4, 9
INDEX_TIP, MIDDLE_TIP = 8, 12
# (PIP, TIP) for index, middle, ring, pinky
_FINGER_JOINTS = ((6, 8), (10, 12), (14, 16), (18, 20))


class Pose(Enum):
    NONE = "none"    # not a recognized pose (transition, partial occlusion, …)
    FIST = "fist"
    ONE = "one"      # index
    TWO = "two"      # index + middle
    THREE = "three"  # index + middle + ring
    FOUR = "four"    # index → pinky (open hand; thumb ignored)
    OK = "ok"        # thumb–index pinch with middle, ring and pinky extended


FINGER_COUNT_POSES = {
    (True, False, False, False): Pose.ONE,
    (True, True, False, False): Pose.TWO,
    (True, True, True, False): Pose.THREE,
    (True, True, True, True): Pose.FOUR,
}

POSE_FINGER_COUNT = {Pose.ONE: 1, Pose.TWO: 2, Pose.THREE: 3, Pose.FOUR: 4}


@dataclass(frozen=True)
class HandPose:
    """Everything the modal gesture layer needs to know about one hand in one frame."""

    pose: Pose
    extended: tuple[bool, bool, bool, bool]  # index, middle, ring, pinky
    pinch_index: bool
    pinch_middle: bool
    scale: float                       # hand length in pixels
    anchor: tuple[float, float]        # cursor anchor, user space px (x grows to the user's right)
    wrist: tuple[float, float]         # user space px
    anchor_norm: tuple[float, float]   # cursor anchor, raw normalized MediaPipe coords

    @property
    def any_pinch(self) -> bool:
        return self.pinch_index or self.pinch_middle


class PoseClassifier:
    """
    Stateful per-hand classifier (pinches use hysteresis, so keep one instance per hand).
    """

    def __init__(
        self,
        frame_width: int = CAMERA_WIDTH,
        frame_height: int = CAMERA_HEIGHT,
        anchor_landmark: int = CURSOR_ANCHOR_LANDMARK,
    ) -> None:
        self._w = frame_width
        self._h = frame_height
        self._anchor = anchor_landmark
        self._pinch_index = False
        self._pinch_middle = False

    def reset(self) -> None:
        self._pinch_index = False
        self._pinch_middle = False

    def _px(self, lm: Landmark) -> tuple[float, float]:
        # Mirror x so that +x is the user's right (the raw webcam frame is unmirrored).
        return (1.0 - lm.x) * self._w, lm.y * self._h

    def classify(self, landmarks: list[Landmark]) -> HandPose:
        p = [self._px(lm) for lm in landmarks]
        wrist = p[WRIST]
        scale = max(math.dist(wrist, p[MIDDLE_MCP]), 1e-6)

        def from_wrist(i: int) -> float:
            return math.dist(wrist, p[i]) / scale

        extended = tuple(
            from_wrist(tip) > from_wrist(pip) * FINGER_EXTEND_RATIO
            for pip, tip in _FINGER_JOINTS
        )
        folded = all(from_wrist(tip) < FIST_TIP_RADIUS for _, tip in _FINGER_JOINTS)

        # A pinch needs the fingertip away from the palm, otherwise a fist (thumb
        # resting on curled fingers) or a pointing hand with the thumb tucked over
        # the middle finger would register as one.
        index_open = from_wrist(INDEX_TIP) >= FIST_TIP_RADIUS
        middle_open = from_wrist(MIDDLE_TIP) >= FIST_TIP_RADIUS
        d_index = math.dist(p[THUMB_TIP], p[INDEX_TIP]) / scale
        d_middle = math.dist(p[THUMB_TIP], p[MIDDLE_TIP]) / scale

        limit = PINCH_INDEX_EXIT_RATIO if self._pinch_index else PINCH_INDEX_ENTER_RATIO
        pinch_index = index_open and d_index < limit
        limit = PINCH_MIDDLE_EXIT_RATIO if self._pinch_middle else PINCH_MIDDLE_ENTER_RATIO
        pinch_middle = middle_open and d_middle < limit
        if pinch_index and pinch_middle:
            # Index and middle tips are close together, so the thumb is near both.
            # The pinches are exclusive: keep the one already active, else the nearer.
            if self._pinch_index or (not self._pinch_middle and d_index <= d_middle):
                pinch_middle = False
            else:
                pinch_index = False
        self._pinch_index = pinch_index
        self._pinch_middle = pinch_middle

        if not any(extended) and folded:
            pose = Pose.FIST
        elif self._pinch_index and extended[1:] == (True, True, True):
            pose = Pose.OK
        else:
            pose = FINGER_COUNT_POSES.get(extended, Pose.NONE)

        anchor_lm = landmarks[self._anchor]
        return HandPose(
            pose=pose,
            extended=extended,
            pinch_index=self._pinch_index,
            pinch_middle=self._pinch_middle,
            scale=scale,
            anchor=p[self._anchor],
            wrist=wrist,
            anchor_norm=(anchor_lm.x, anchor_lm.y),
        )
