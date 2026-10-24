# core/preview.py
"""
Pictures for the settings page: the live camera preview (mirrored, with the
tracked hands drawn on it) and one snapshot per camera for the camera picker.
"""

from __future__ import annotations

import base64
import logging

import cv2

logger = logging.getLogger(__name__)

# MediaPipe hand skeleton: (from, to) landmark pairs
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),  # pinky + palm
)
SUPPORT_COLOR = "#e6e8ec"


def _bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def _resize(frame, width: int):
    h, w = frame.shape[:2]
    if w <= width:
        return frame.copy()
    return cv2.resize(frame, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)


def _draw_hand(img, landmarks, color: str) -> None:
    h, w = img.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    bgr = _bgr(color)
    thick = max(2, w // 240)
    for a, b in HAND_CONNECTIONS:
        cv2.line(img, pts[a], pts[b], bgr, thick, cv2.LINE_AA)
    for i, p in enumerate(pts):
        radius = thick + 2 if i in (4, 8, 12, 16, 20) else thick + 1
        cv2.circle(img, p, radius, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, p, radius, bgr, max(1, thick // 2), cv2.LINE_AA)


def encode_jpeg(img, quality: int = 75) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else None


def render_preview(frame, hands=None, dominant: str = "right", color: str = "#4c8dff", width: int = 640) -> bytes | None:
    """JPEG of the frame as the user sees themselves (mirrored), hands drawn on top."""
    if frame is None:
        return None
    img = _resize(frame, width)
    if hands is not None:
        main, support = (hands.right, hands.left) if dominant == "right" else (hands.left, hands.right)
        if support is not None:
            _draw_hand(img, support, SUPPORT_COLOR)
        if main is not None:
            _draw_hand(img, main, color)
    return encode_jpeg(cv2.flip(img, 1))


def snapshot_data_url(frame, width: int = 320) -> str | None:
    if frame is None:
        return None
    jpeg = encode_jpeg(cv2.flip(_resize(frame, width), 1), 70)
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii") if jpeg else None


def probe_cameras(active_index: int, active_frame, max_index: int = 5) -> list[dict]:
    """
    One entry per camera index that opens: {"index", "active", "thumb"}.

    The camera AirMouse is using is not reopened (that can fail while it is
    streaming): its latest frame is used instead. Stops after two missing
    indices past the active one. Takes about a second per camera.
    """
    cameras, misses = [], 0
    for index in range(max_index + 1):
        if index == active_index:
            cameras.append({"index": index, "active": True, "thumb": snapshot_data_url(active_frame)})
            continue
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                misses += 1
                if misses >= 2 and index > active_index:
                    break
                continue
            misses = 0
            frame = None
            for _ in range(8):  # the first frames are often black while the camera adjusts
                ok, grabbed = cap.read()
                if ok and grabbed is not None:
                    frame = grabbed
            cameras.append({"index": index, "active": False, "thumb": snapshot_data_url(frame)})
        except Exception as exc:  # a broken driver must not break the page
            logger.warning("Camera %d probe failed: %s", index, exc)
        finally:
            cap.release()
    return cameras
