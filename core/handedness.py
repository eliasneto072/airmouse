# core/handedness.py
"""Turns MediaPipe's per-frame handedness labels into stable left/right assignments."""

from __future__ import annotations

import math
from dataclasses import dataclass

from config import HANDEDNESS_STABLE_FRAMES


@dataclass
class _Track:
    is_right: bool
    x: float
    y: float


class HandednessStabilizer:
    """
    - Two hands with the same label: the one on the user's right side of the
      image wins "right" (raw webcam frames are unmirrored, so that is the
      smaller x; pass ``mirrored=True`` for a mirrored feed).
    - One hand: while it is continuously tracked (wrist did not jump), its label
      only flips after ``stable_frames`` consecutive frames that disagree.
    """

    def __init__(
        self,
        stable_frames: int = HANDEDNESS_STABLE_FRAMES,
        mirrored: bool = False,
        max_jump: float = 0.15,
    ) -> None:
        self._stable_frames = stable_frames
        self._mirrored = mirrored
        self._max_jump = max_jump
        self._last: _Track | None = None
        self._disagree = 0

    def assign(self, hands: list[tuple[bool, float, float]]) -> list[bool]:
        """
        Args:
            hands: one ``(labelled_right, wrist_x, wrist_y)`` per detected hand
                   (normalized coordinates).
        Returns:
            ``is_right`` for each hand, in the same order.
        """
        if not hands:
            self._last = None
            self._disagree = 0
            return []

        if len(hands) >= 2:
            self._last = None
            self._disagree = 0
            labels = [label for label, _, _ in hands]
            if len(set(labels[:2])) == 2:
                return labels
            # Same label on both: decide by position.
            order = sorted(range(len(hands)), key=lambda i: hands[i][1], reverse=self._mirrored)
            result = [False] * len(hands)
            result[order[0]] = True
            return result

        label, x, y = hands[0]
        last = self._last
        if last is None or math.dist((x, y), (last.x, last.y)) > self._max_jump:
            self._disagree = 0
            is_right = label  # a new hand: trust the label
        elif label == last.is_right:
            self._disagree = 0
            is_right = label
        else:
            self._disagree += 1
            if self._disagree >= self._stable_frames:
                self._disagree = 0
                is_right = label
            else:
                is_right = last.is_right
        self._last = _Track(is_right, x, y)
        return [is_right]
