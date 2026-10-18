"""Pointer: relative trackpad mapping, clutch, freeze + rollback."""

import pytest

from core.display import TrackpadZone, VirtualDesktop
from core.gestures.poses import PoseClassifier
from core.pointer import Pointer
from tests.fakes import FakeActuator
from tests.fixtures.hands import make_hand

FRAME = (1280, 720)
DT = 1 / 75
DESKTOP = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
TRACKPAD = TrackpadZone(x_min=100, x_max=1180, y_min=100, y_max=620)
SCALE = 0.25  # hand length = 0.25 × 720 = 180 px


@pytest.fixture
def rig():
    actuator = FakeActuator()
    actuator.pos = (960, 540)
    return Pointer(actuator, DESKTOP, TRACKPAD, mapping="relative"), actuator, PoseClassifier(*FRAME)


def pose_at(classifier, x):
    return classifier.classify(make_hand("point", center=(x, 0.75), scale=SCALE, frame=FRAME))


def glide(pointer, classifier, t, x_from, x_to, seconds):
    """Move the hand horizontally (raw normalized x) at constant speed."""
    n = max(1, round(seconds / DT))
    for i in range(1, n + 1):
        t += DT
        pointer.update(pose_at(classifier, x_from + (x_to - x_from) * i / n), t)
    return t


def settle(pointer, classifier, t, x, seconds=0.3):
    return glide(pointer, classifier, t, x, x, seconds)


def test_moving_hand_to_users_right_moves_cursor_right(rig):
    pointer, actuator, classifier = rig
    t = settle(pointer, classifier, 0.0, 0.5)
    # Raw x decreasing = the user's right. 0.07 × 1280 px ≈ 0.5 hand lengths.
    t = glide(pointer, classifier, t, 0.5, 0.43, 0.5)
    settle(pointer, classifier, t, 0.43)
    x, y = actuator.pos
    assert 960 + 150 < x < 960 + 900
    assert abs(y - 540) <= 2


def test_still_hand_does_not_drift(rig):
    pointer, actuator, classifier = rig
    settle(pointer, classifier, 0.0, 0.5, seconds=2.0)
    assert actuator.pos == (960, 540)


def test_faster_movement_goes_further(rig):
    slow_ptr, slow_act, classifier = rig
    t = settle(slow_ptr, classifier, 0.0, 0.5)
    t = glide(slow_ptr, classifier, t, 0.5, 0.45, 1.0)
    settle(slow_ptr, classifier, t, 0.45)

    fast_act = FakeActuator()
    fast_act.pos = (960, 540)
    fast_ptr = Pointer(fast_act, DESKTOP, TRACKPAD, mapping="relative")
    t = settle(fast_ptr, classifier, 0.0, 0.5)
    t = glide(fast_ptr, classifier, t, 0.5, 0.45, 0.1)
    settle(fast_ptr, classifier, t, 0.45)

    assert fast_act.pos[0] - 960 > slow_act.pos[0] - 960 > 0


def test_reset_is_a_clutch(rig):
    pointer, actuator, classifier = rig
    t = settle(pointer, classifier, 0.0, 0.5)
    pointer.reset()
    t = settle(pointer, classifier, t, 0.3)  # hand reappears somewhere else
    assert actuator.pos == (960, 540)


def test_freeze_rolls_back_and_unfreeze_does_not_jump(rig):
    pointer, actuator, classifier = rig
    t = settle(pointer, classifier, 0.0, 0.5)
    t = glide(pointer, classifier, t, 0.5, 0.47, 0.3)
    moving_pos = actuator.pos
    pointer.freeze(t)
    frozen_pos = actuator.pos
    assert frozen_pos[0] < moving_pos[0]          # rolled back towards where it was aimed

    t = glide(pointer, classifier, t, 0.47, 0.44, 0.3)  # hand keeps moving while frozen
    assert actuator.pos == frozen_pos

    pointer.unfreeze()
    t = settle(pointer, classifier, t, 0.44, seconds=0.5)
    assert abs(actuator.pos[0] - frozen_pos[0]) < 40  # no jump to "catch up"


def test_cursor_is_clamped_to_the_desktop(rig):
    pointer, actuator, classifier = rig
    t = settle(pointer, classifier, 0.0, 0.8)
    for _ in range(4):
        t = glide(pointer, classifier, t, 0.8, 0.2, 0.15)
        pointer.reset()
        t = settle(pointer, classifier, t, 0.8)
    assert actuator.pos[0] == 1919


def test_absolute_mapping_follows_hand_position():
    actuator = FakeActuator()
    pointer = Pointer(actuator, DESKTOP, TRACKPAD, mapping="absolute")
    classifier = PoseClassifier(*FRAME)
    t = 0.0
    for _ in range(60):
        t += DT
        pointer.update(classifier.classify(make_hand("point", center=(0.5, 0.75), scale=SCALE, frame=FRAME)), t)
    left_x = actuator.pos[0]
    for _ in range(60):
        t += DT
        pointer.update(classifier.classify(make_hand("point", center=(0.3, 0.75), scale=SCALE, frame=FRAME)), t)
    assert actuator.pos[0] > left_x
