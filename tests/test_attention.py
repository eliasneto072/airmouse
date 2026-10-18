"""Head direction and the attention decision."""

import math

import pytest

from core.attention import Attention, CAMERA_AXIS, angle_between, face_direction
from core.tracker import Landmark

W, H = 1280, 720


def face(yaw=0.0, pitch=0.0, roll=0.0, center=(0.5, 0.4), size=0.12):
    """Minimal synthetic face: only the landmarks face_direction() reads, in a 478-long list."""
    # Canonical points (in face-width units): x right, y down, z towards the back of the head
    pts = {33: (-0.5, 0.0, 0.0), 263: (0.5, 0.0, 0.0), 10: (0.0, -0.6, 0.0), 152: (0.0, 0.8, 0.0)}
    y, p, r = (math.radians(a) for a in (yaw, pitch, roll))

    def rotate(v):
        x, yy, z = v
        x, yy = x * math.cos(r) - yy * math.sin(r), x * math.sin(r) + yy * math.cos(r)        # roll (z axis)
        yy, z = yy * math.cos(p) - z * math.sin(p), yy * math.sin(p) + z * math.cos(p)        # pitch (x axis)
        x, z = x * math.cos(y) + z * math.sin(y), -x * math.sin(y) + z * math.cos(y)          # yaw (y axis)
        return x, yy, z

    lms = [Landmark(0.0, 0.0, 0.0)] * 478
    s = size * W
    for i, v in pts.items():
        x, yy, z = rotate(v)
        lms[i] = Landmark(x=center[0] + x * s / W, y=center[1] + yy * s / H, z=z * s / W)
    return lms


@pytest.mark.parametrize("yaw, pitch", [(0, 0), (20, 0), (-35, 0), (0, 25), (0, -40), (15, 20)])
def test_direction_angle_matches_head_rotation(yaw, pitch):
    expected = math.degrees(math.acos(math.cos(math.radians(yaw)) * math.cos(math.radians(pitch))))
    assert angle_between(face_direction(face(yaw, pitch), W, H), CAMERA_AXIS) == pytest.approx(expected, abs=1.0)


def test_head_roll_is_ignored():
    straight = face_direction(face(), W, H)
    tilted = face_direction(face(roll=30), W, H)
    assert angle_between(straight, tilted) < 1.0


def test_looking_away_is_debounced():
    att = Attention(max_angle=28, away_s=0.8, adapt_s=0)
    t = 0.0
    assert att.update(face_direction(face(), W, H), t).looking
    t += 0.5
    state = att.update(face_direction(face(pitch=45), W, H), t)   # glance at the phone
    assert not state.facing and state.looking
    t += 0.9
    assert not att.update(face_direction(face(pitch=45), W, H), t).looking
    t += 0.1
    assert att.update(face_direction(face(), W, H), t).looking     # back immediately


def test_no_face_is_not_facing():
    att = Attention(max_angle=28, away_s=0.8)
    state = att.update(None, 0.0)
    assert not state.face and not state.facing


def test_calibrate_makes_current_direction_the_screen():
    att = Attention(max_angle=28, away_s=0.8, adapt_s=0)
    side = face_direction(face(yaw=40), W, H)   # e.g. the camera is off to the side of the monitor
    assert not att.update(side, 0.0).facing
    att.calibrate()
    assert att.update(side, 0.1).facing
    assert not att.update(face_direction(face(), W, H), 0.2).facing


def test_baseline_follows_posture_while_adapting():
    att = Attention(max_angle=28, away_s=0.8, adapt_s=2.0)
    leaning = face_direction(face(pitch=20), W, H)
    t = 0.0
    for _ in range(600):   # 8 s of use at 75 FPS while slightly looking down
        t += 1 / 75
        att.update(leaning, t, adapt=True)
    assert angle_between(att.baseline, leaning) < 3.0
