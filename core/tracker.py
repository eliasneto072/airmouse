# core/tracker.py
"""
MediaPipe HandLandmarker wrapper (Tasks API — mediapipe ≥0.10.14).

Extracts hand landmarks from a BGR frame.
Returns None if no hand detected; returns list of 21 Landmark objects otherwise.

Key optimizations:
- RunningMode.VIDEO (MP_VIDEO_MODE): landmarks are tracked from frame to frame and
  the palm detector only runs when tracking is lost — less jitter, less CPU and
  steadier handedness labels than per-frame IMAGE mode
- HandednessStabilizer: smooths left/right label flicker
- RGB conversion + mp.Image wrapper: required by Tasks API
- No internal array copy: mp.Image takes ownership of the numpy buffer
"""

import logging
import time
from dataclasses import dataclass

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
import numpy as np

from core.handedness import HandednessStabilizer
from config import (
    MP_DETECTION_CONFIDENCE,
    MP_TRACKING_CONFIDENCE,
    MP_MODEL_PATH,
    MP_MAX_HANDS,
    MP_VIDEO_MODE,
    FLIP_HANDEDNESS,
    LEFT_HAND_ENABLED,
    TWO_HAND_GESTURES_ENABLED,
)

logger = logging.getLogger(__name__)


@dataclass
class Landmark:
    """Normalized [0.0–1.0] landmark coordinate."""
    x: float
    y: float
    z: float
    visibility: float = 0.0


@dataclass
class HandsResult:
    """Holds landmarks for both hands. None = that hand not detected this frame."""
    left: list[Landmark] | None = None   # user's left hand (21 landmarks)
    right: list[Landmark] | None = None  # user's right hand (21 landmarks)


# Landmark index constants — MediaPipe Hand Landmark Model
LM_INDEX_TIP = 8
LM_INDEX_PIP = 6
LM_MIDDLE_TIP = 12
LM_MIDDLE_PIP = 10
LM_RING_TIP = 16
LM_RING_PIP = 14
LM_PINKY_TIP = 20
LM_PINKY_PIP = 18
LM_THUMB_TIP = 4
LM_THUMB_MCP = 2


def resolve_num_hands(max_hands: int, left_hand_enabled: bool, two_hand_enabled: bool) -> int:
    """
    Number of hands MediaPipe should track.

    A second hand is only tracked when a feature uses it: with both the left-hand
    and two-hand layers off, tracking one hand is cheaper and a stray left hand can
    never take the slot of the right hand.
    """
    if not (left_hand_enabled or two_hand_enabled):
        return 1
    return max(1, max_hands)


class HandTracker:
    """
    Wraps MediaPipe HandLandmarker (Tasks API) for single-hand landmark extraction.
    Intended to be used as a context manager.
    """

    def __init__(self) -> None:
        base_options = python.BaseOptions(model_asset_path=MP_MODEL_PATH)
        num_hands = resolve_num_hands(MP_MAX_HANDS, LEFT_HAND_ENABLED, TWO_HAND_GESTURES_ENABLED)
        options = HandLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO if MP_VIDEO_MODE else RunningMode.IMAGE,
            num_hands=num_hands,
            min_hand_detection_confidence=MP_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=MP_TRACKING_CONFIDENCE,
            min_tracking_confidence=MP_TRACKING_CONFIDENCE,
        )
        self._detector = HandLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1
        self._handedness = HandednessStabilizer(mirrored=FLIP_HANDEDNESS)
        logger.info(
            "MediaPipe HandLandmarker initialized (max_hands=%d, mode=%s)",
            num_hands,
            "video" if MP_VIDEO_MODE else "image",
        )

    def process(self, frame: np.ndarray) -> HandsResult:
        """
        Process one BGR frame. Always returns HandsResult (never None).
        Each field is None if that hand was not detected.

        MediaPipe 'Left' from camera perspective = user's Right hand (mirrored).
        """
        result_obj = HandsResult()
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            if MP_VIDEO_MODE:
                # VIDEO mode needs strictly increasing timestamps
                timestamp_ms = max(int(time.perf_counter() * 1000), self._last_timestamp_ms + 1)
                self._last_timestamp_ms = timestamp_ms
                result = self._detector.detect_for_video(mp_image, timestamp_ms)
            else:
                result = self._detector.detect(mp_image)
        except Exception as e:
            logger.warning("MediaPipe processing error: %s", e)
            return result_obj

        if not result.hand_landmarks:
            self._handedness.assign([])
            return result_obj

        detected: list[list[Landmark]] = []
        labels: list[tuple[bool, float, float]] = []
        for i, hand_lms in enumerate(result.hand_landmarks):
            landmarks = [
                Landmark(
                    x=lm.x,
                    y=lm.y,
                    z=lm.z,
                    visibility=getattr(lm, "visibility", None) or 0.0,
                )
                for lm in hand_lms
            ]
            cam_label = result.handedness[i][0].category_name
            logger.debug("MediaPipe label=%s FLIP_HANDEDNESS=%s", cam_label, FLIP_HANDEDNESS)
            # MediaPipe Tasks API assumes mirrored input → "Right" = user's right.
            # If FLIP_HANDEDNESS=True, invert (for non-standard camera setups).
            labelled_right = (cam_label == "Right") if not FLIP_HANDEDNESS else (cam_label == "Left")
            detected.append(landmarks)
            labels.append((labelled_right, landmarks[0].x, landmarks[0].y))

        for landmarks, is_right in zip(detected, self._handedness.assign(labels)):
            if is_right:
                result_obj.right = landmarks
            else:
                result_obj.left = landmarks

        return result_obj

    def close(self) -> None:
        self._detector.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, *_) -> None:
        self.close()
