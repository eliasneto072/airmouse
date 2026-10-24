# core/attention.py
"""
Attention gate: only react to gestures while the user faces the screen.

The head direction is the normal of the face plane (eye corners × forehead →
chin) built from MediaPipe face landmarks. It ignores head roll (tilting the
head to the side while reclined) and does not depend on any axis convention:
we only measure the angle between the current direction and the "screen
direction" (the baseline).

The baseline starts as "facing the camera", follows the user's posture slowly
while a mode is in use (ATTENTION_ADAPT_S), and is re-learned whenever a mode
is started with the override (holding the start gesture ATTENTION_OVERRIDE_S).

``facing`` is the instant decision (used to start modes); ``looking`` is
debounced (turns False only after ATTENTION_AWAY_S facing away) and is used to
pause an active mode. When no face is found the user counts as not looking
(strict default); ATTENTION_NO_FACE_ALLOWS = True makes gestures count
instead, so the gate only blocks when it sees the user looking elsewhere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from config import ATTENTION_ADAPT_S, ATTENTION_AWAY_S, ATTENTION_MAX_ANGLE, ATTENTION_NO_FACE_ALLOWS

# MediaPipe Face Mesh landmark indices
EYE_OUTER_A, EYE_OUTER_B, FOREHEAD, CHIN = 33, 263, 10, 152

Vector = tuple[float, float, float]


def _sub(a: Vector, b: Vector) -> Vector:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a: Vector, b: Vector) -> Vector:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a: Vector) -> Vector:
    n = math.sqrt(_dot(a, a))
    if n < 1e-9:
        raise ValueError("degenerate vector")
    return a[0] / n, a[1] / n, a[2] / n


def angle_between(a: Vector, b: Vector) -> float:
    """Angle in degrees between two directions, ignoring their sign."""
    return math.degrees(math.acos(min(1.0, abs(_dot(_unit(a), _unit(b))))))


def face_direction(landmarks, frame_width: int, frame_height: int) -> Vector:
    """Unit normal of the face plane. MediaPipe z uses roughly the x scale."""

    def p(i: int) -> Vector:
        lm = landmarks[i]
        return lm.x * frame_width, lm.y * frame_height, lm.z * frame_width

    across = _sub(p(EYE_OUTER_B), p(EYE_OUTER_A))
    down = _sub(p(CHIN), p(FOREHEAD))
    return _unit(_cross(across, down))


CAMERA_AXIS: Vector = (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class AttentionState:
    face: bool             # a face was found
    angle: float | None    # degrees between the head direction and the screen direction
    facing: bool           # instant: facing the screen now
    looking: bool          # debounced: has not been facing away for ATTENTION_AWAY_S


ALWAYS_LOOKING = AttentionState(face=True, angle=None, facing=True, looking=True)


class Attention:
    """Pure decision logic (no MediaPipe), fed one head direction per frame."""

    def __init__(
        self,
        max_angle: float = ATTENTION_MAX_ANGLE,
        away_s: float = ATTENTION_AWAY_S,
        adapt_s: float = ATTENTION_ADAPT_S,
        no_face_allows: bool = ATTENTION_NO_FACE_ALLOWS,
    ) -> None:
        self._max_angle = max_angle
        self._no_face_allows = no_face_allows
        self._away_s = away_s
        self._adapt_s = adapt_s
        self.baseline: Vector = CAMERA_AXIS
        self._direction: Vector | None = None
        self._away_since: float | None = None
        self._last: float | None = None
        self.state = AttentionState(face=False, angle=None, facing=False, looking=False)

    def update(self, direction: Vector | None, now: float, adapt: bool = False) -> AttentionState:
        dt = 0.0 if self._last is None else max(0.0, now - self._last)
        self._last = now
        self._direction = direction

        angle = None if direction is None else angle_between(direction, self.baseline)
        if angle is None:
            facing = self._no_face_allows
        else:
            facing = angle <= self._max_angle

        if facing:
            self._away_since = None
            if adapt and self._adapt_s > 0 and direction is not None:
                self._blend(direction, min(1.0, dt / self._adapt_s))
        elif self._away_since is None:
            self._away_since = now
        looking = facing or (self._away_since is not None and now - self._away_since < self._away_s)

        self.state = AttentionState(face=direction is not None, angle=angle, facing=facing, looking=looking)
        return self.state

    def calibrate(self) -> None:
        """The current head direction becomes the screen direction."""
        if self._direction is not None:
            self.baseline = self._direction

    def _blend(self, direction: Vector, weight: float) -> None:
        d = direction if _dot(direction, self.baseline) >= 0 else (-direction[0], -direction[1], -direction[2])
        b = self.baseline
        self.baseline = _unit(
            (b[0] + (d[0] - b[0]) * weight, b[1] + (d[1] - b[1]) * weight, b[2] + (d[2] - b[2]) * weight)
        )
