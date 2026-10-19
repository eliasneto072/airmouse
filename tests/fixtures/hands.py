"""
Synthetic MediaPipe hand landmarks — no camera needed.

Builds an upright hand (fingers pointing up, palm facing the camera) and returns
21 landmarks in normalized image coordinates. Only the geometry the gesture code
reads is modelled: which fingers are extended or curled, and where the thumb tip is.

Geometry is defined in "hand units" (1.0 = wrist → middle-MCP distance, roughly)
and then placed in the image:

- ``frame=None`` (default): one hand unit = ``scale`` in both normalized axes.
  This is what the classic processors were tuned against.
- ``frame=(width, height)``: one hand unit = ``scale × height`` pixels in both
  axes, i.e. a physically proportioned hand in a non-square frame. Use this for
  code that works in pixel space (PoseClassifier, Pointer).
"""

from __future__ import annotations

import math

from core.tracker import Landmark

# (MCP, PIP, DIP, TIP) landmark indices and the MCP x-offset in hand units
_FINGERS = {
    "index": ((5, 6, 7, 8), -0.30),
    "middle": ((9, 10, 11, 12), -0.10),
    "ring": ((13, 14, 15, 16), 0.10),
    "pinky": ((17, 18, 19, 20), 0.30),
}

# Which fingers are extended:  index, middle, ring, pinky, thumb
_POSES = {
    "open": (True, True, True, True, True),
    "point": (True, False, False, False, True),
    "peace": (True, True, False, False, False),
    "three": (True, True, True, False, False),
    "four": (True, True, True, True, False),
    "fist": (False, False, False, False, False),
    "ok": (False, True, True, True, True),  # 👌: index curled into a ring with the thumb
}

_PINCH_TARGET = {"index": 8, "middle": 12}


def make_hand(
    pose: str = "point",
    pinch: str | None = None,
    center: tuple[float, float] = (0.5, 0.6),
    scale: float = 0.15,
    rotation_deg: float = 0.0,
    frame: tuple[int, int] | None = None,
) -> list[Landmark]:
    """
    Args:
        pose:         "open" (5 fingers), "point", "peace", "three", "four" (thumb
                      folded), "fist" or "ok" (a realistic 👌)
        pinch:        None, "index" or "middle" — put the thumb tip on that fingertip
        center:       wrist position (normalized x, y)
        scale:        hand size (see module docstring)
        rotation_deg: tilt of the hand around the wrist (positive = clockwise on screen)
        frame:        (width, height) for pixel-proportioned output, or None
    """
    extended = dict(zip(("index", "middle", "ring", "pinky", "thumb"), _POSES[pose]))
    pts: list[tuple[float, float]] = [(0.0, 0.0)] * 21  # hand units, wrist at origin

    mcp_v = -0.9
    for name, ((mcp, pip, dip, tip), du) in _FINGERS.items():
        pts[mcp] = (du, mcp_v)
        if extended[name]:
            pts[pip] = (du, mcp_v - 0.35)
            pts[dip] = (du, mcp_v - 0.60)
            pts[tip] = (du, mcp_v - 0.80)
        else:  # curled: the tip folds back below the PIP joint, onto the palm
            pts[pip] = (du, mcp_v - 0.25)
            pts[dip] = (du, mcp_v - 0.10)
            pts[tip] = (du, mcp_v + 0.05)

    # Thumb: CMC(1), MCP(2), IP(3), TIP(4) on the index side
    pts[1] = (-0.35, -0.20)
    pts[2] = (-0.50, -0.40)
    if extended["thumb"]:  # sticking out to the side
        pts[3] = (-0.68, -0.48)
        pts[4] = (-0.85, -0.55)
    else:  # folded across the palm towards the pinky, tip below the thumb MCP
        pts[3] = (-0.22, -0.38)
        pts[4] = (0.05, -0.35)

    if pose == "ok":  # a real 👌: the index bends towards the thumb, its tip ends up near the palm
        pts[6] = (-0.32, -1.20)
        pts[7] = (-0.42, -1.18)
        pts[8] = (-0.45, -1.02)
        pts[4] = (-0.48, -1.00)
        pts[3] = (-0.55, -0.70)

    if pinch is not None:
        tu, tv = pts[_PINCH_TARGET[pinch]]
        pts[4] = (tu - 0.05, tv + 0.05)
        pts[3] = ((pts[2][0] + pts[4][0]) / 2, (pts[2][1] + pts[4][1]) / 2)

    a = math.radians(rotation_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    cx, cy = center
    if frame is None:
        sx = sy = scale
    else:
        width, height = frame
        sy = scale
        sx = scale * height / width

    landmarks = []
    for u, v in pts:
        ru = u * cos_a - v * sin_a
        rv = u * sin_a + v * cos_a
        landmarks.append(Landmark(x=cx + ru * sx, y=cy + rv * sy, z=0.0))
    return landmarks
