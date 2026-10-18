"""PoseClassifier: poses at any distance and tilt, pinches with hysteresis."""

import pytest

from core.gestures.poses import Pose, PoseClassifier
from core.gestures.stabilizer import PoseStabilizer
from tests.fixtures.hands import make_hand

FRAME = (1280, 720)

POSES = [
    ("fist", None, Pose.FIST),
    ("point", None, Pose.ONE),
    ("peace", None, Pose.TWO),
    ("three", None, Pose.THREE),
    ("four", None, Pose.FOUR),
    ("open", None, Pose.FOUR),  # thumb is ignored on purpose
]


def hand(pose, pinch=None, scale=0.25, rotation=0.0, center=(0.5, 0.75)):
    return make_hand(pose, pinch=pinch, scale=scale, rotation_deg=rotation, center=center, frame=FRAME)


@pytest.mark.parametrize("name, pinch, expected", POSES)
@pytest.mark.parametrize("scale", [0.12, 0.25, 0.4])        # far, medium, close to the camera
@pytest.mark.parametrize("rotation", [-35.0, 0.0, 35.0])    # tilted hand
def test_pose_classification(name, pinch, expected, scale, rotation):
    result = PoseClassifier(*FRAME).classify(hand(name, pinch, scale, rotation))
    assert result.pose == expected
    assert not result.pinch_index and not result.pinch_middle


@pytest.mark.parametrize("scale", [0.12, 0.25, 0.4])
def test_pinches(scale):
    classifier = PoseClassifier(*FRAME)
    assert classifier.classify(hand("point", "index", scale)).pinch_index
    classifier.reset()
    pinch_middle = classifier.classify(hand("peace", "middle", scale))
    assert pinch_middle.pinch_middle and not pinch_middle.pinch_index


def test_ok_sign():
    result = PoseClassifier(*FRAME).classify(hand("open", "index"))
    assert result.pose == Pose.OK


def test_thumb_on_curled_middle_is_not_a_pinch():
    # Pointing with the thumb tucked over the curled middle finger is common;
    # it must not count as a thumb–middle pinch (right click).
    lm = hand("point")
    lm[4] = lm[10]  # thumb tip on the middle finger's PIP joint
    assert not PoseClassifier(*FRAME).classify(lm).pinch_middle


def test_pinch_hysteresis():
    classifier = PoseClassifier(*FRAME)
    closed = hand("point", "index")
    assert classifier.classify(closed).pinch_index

    # Open the pinch to ~0.38 hand lengths: above the enter threshold (0.30) but
    # below the exit threshold (0.45) → still pinching.
    half_open = list(closed)
    tip = closed[8]
    half_open[4] = type(tip)(x=tip.x + 0.38 * 0.25 * 720 / 1280, y=tip.y, z=0.0)
    assert classifier.classify(half_open).pinch_index

    # A fresh classifier at the same distance has not entered the pinch.
    assert not PoseClassifier(*FRAME).classify(half_open).pinch_index


def test_anchor_is_in_user_space():
    # Moving the hand to the user's right (smaller raw x) increases anchor x.
    classifier = PoseClassifier(*FRAME)
    left = classifier.classify(hand("point", center=(0.6, 0.75)))
    right = classifier.classify(hand("point", center=(0.4, 0.75)))
    assert right.anchor[0] > left.anchor[0]


def test_stabilizer_ignores_flicker_and_holds_through_none():
    stabilizer = PoseStabilizer(stable_s=0.08, none_stable_s=0.3)
    t = 0.0
    for _ in range(10):
        t += 0.013
        stabilizer.update(Pose.ONE, t)
    assert stabilizer.pose == Pose.ONE

    t += 0.013
    assert stabilizer.update(Pose.TWO, t) == Pose.ONE          # one-frame flicker
    t += 0.013
    assert stabilizer.update(Pose.ONE, t) == Pose.ONE

    for _ in range(15):                                          # ~0.2 s of NONE
        t += 0.013
        assert stabilizer.update(Pose.NONE, t) == Pose.ONE

    for _ in range(8):                                           # a real change
        t += 0.013
        stabilizer.update(Pose.TWO, t)
    assert stabilizer.pose == Pose.TWO
