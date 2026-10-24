# core/face_tracker.py
"""MediaPipe FaceLandmarker wrapper used by the attention gate."""

from __future__ import annotations

import logging
import time

import cv2

from config import (
    ATTENTION_EVERY_N_FRAMES,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    FACE_MODEL_PATH,
    FACE_MODEL_URL,
    FACE_TRACKING_WIDTH,
)
from core import models
from core.attention import Vector, face_direction

logger = logging.getLogger(__name__)


def load_face_model(path: str = FACE_MODEL_PATH, url: str = FACE_MODEL_URL) -> bytes:
    """The face model (bundled, or downloaded on first use — it is git-ignored like the hand model)."""
    return models.load_model(path, url, "MediaPipe face (~3.7 MB)")


class FaceTracker:
    """
    Returns the head direction (unit vector) of the most prominent face, or None.
    Runs the model every ``every_n`` frames and reuses the last result in between.
    """

    def __init__(self, model_path: str = FACE_MODEL_PATH, every_n: int = ATTENTION_EVERY_N_FRAMES) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

        options = FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_buffer=load_face_model(model_path)),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp = mp
        self._landmarker = FaceLandmarker.create_from_options(options)
        self._every_n = max(1, every_n)
        self._frame = 0
        self._last_timestamp_ms = -1
        self._direction: Vector | None = None
        logger.info("Face tracking ready (every %d frames)", self._every_n)

    def process(self, frame) -> Vector | None:
        self._frame += 1
        if frame is None or (self._frame - 1) % self._every_n:
            return self._direction
        try:
            height, width = frame.shape[:2]
            if FACE_TRACKING_WIDTH and width > FACE_TRACKING_WIDTH:
                small_h = round(height * FACE_TRACKING_WIDTH / width)
                frame = cv2.resize(frame, (FACE_TRACKING_WIDTH, small_h), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = max(int(time.perf_counter() * 1000), self._last_timestamp_ms + 1)
            self._last_timestamp_ms = timestamp_ms
            result = self._landmarker.detect_for_video(image, timestamp_ms)
            if result.face_landmarks:
                self._direction = face_direction(result.face_landmarks[0], CAMERA_WIDTH, CAMERA_HEIGHT)
            else:
                self._direction = None
        except Exception as exc:
            logger.warning("Face tracking error: %s", exc)
            self._direction = None
        return self._direction

    def close(self) -> None:
        self._landmarker.close()


class AttentionGate:
    """FaceTracker + Attention: one call per camera frame."""

    def __init__(self, tracker: FaceTracker, attention) -> None:
        self._tracker = tracker
        self.attention = attention
        self._no_face_since: float | None = None
        self._warned = False

    def process(self, frame, now: float, adapt: bool):
        direction = self._tracker.process(frame)
        state = self.attention.update(direction, now, adapt=adapt)
        if state.face:
            self._no_face_since = None
        elif self._no_face_since is None:
            self._no_face_since = now
        elif not self._warned and now - self._no_face_since > 10.0:
            self._warned = True
            logger.info(
                "No face seen for 10 s (too far from the camera?) — hold the OK sign 1.5 s to turn the look check off."
            )
        return state

    def calibrate(self) -> None:
        self.attention.calibrate()

    def close(self) -> None:
        self._tracker.close()
