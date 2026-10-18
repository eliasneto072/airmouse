"""StrokeTracker: quick strokes scroll, slow returns don't."""

from core.gestures.poses import PoseClassifier
from core.gestures.motion import StrokeTracker
from tests.fixtures.hands import make_hand

FRAME = (1280, 720)
DT = 1 / 75
SCALE = 0.25


class Hand:
    def __init__(self):
        self.classifier = PoseClassifier(*FRAME)
        self.t = 0.0
        self.y = 0.8

    def glide(self, tracker, dy_hand_lengths, seconds):
        """Move the hand up (+) / down (-) by dy hand lengths over `seconds`; return total (x, y) steps."""
        n = max(1, round(seconds / DT))
        start = self.y
        total_x = total_y = 0
        for i in range(1, n + 1):
            self.t += DT
            self.y = start - dy_hand_lengths * SCALE * i / n
            pose = self.classifier.classify(make_hand("open", center=(0.5, self.y), scale=SCALE, frame=FRAME))
            sx, sy = tracker.update(pose, self.t)
            total_x += sx
            total_y += sy
        return total_x, total_y

    def rest(self, tracker, seconds):
        return self.glide(tracker, 0.0, seconds)


def test_quick_stroke_up_scrolls_up_proportionally():
    hand, tracker = Hand(), StrokeTracker(steps_per_hand_length=6)
    hand.rest(tracker, 0.2)
    _, small = hand.glide(tracker, 0.3, 0.12)
    small += hand.rest(tracker, 0.3)[1]
    _, big = hand.glide(tracker, 0.9, 0.2)
    big += hand.rest(tracker, 0.3)[1]
    assert 1 <= small < big
    assert big <= 6


def test_quick_stroke_down_scrolls_down():
    hand, tracker = Hand(), StrokeTracker(steps_per_hand_length=6)
    hand.rest(tracker, 0.2)
    _, steps = hand.glide(tracker, -0.6, 0.15)
    steps += hand.rest(tracker, 0.3)[1]
    assert steps < 0


def test_slow_movement_does_nothing():
    hand, tracker = Hand(), StrokeTracker(steps_per_hand_length=6)
    hand.rest(tracker, 0.2)
    assert hand.glide(tracker, 0.8, 2.0) == (0, 0)


def test_quick_return_right_after_a_stroke_is_ignored():
    hand, tracker = Hand(), StrokeTracker(steps_per_hand_length=6)
    hand.rest(tracker, 0.2)
    _, up = hand.glide(tracker, 0.6, 0.12)
    up += hand.rest(tracker, 0.05)[1]
    _, back = hand.glide(tracker, -0.6, 0.12)   # bring the hand back quickly
    back += hand.rest(tracker, 0.3)[1]
    assert up > 0 and back == 0


def test_repeated_flicks_keep_scrolling():
    hand, tracker = Hand(), StrokeTracker(steps_per_hand_length=6)
    hand.rest(tracker, 0.2)
    total = 0
    for _ in range(3):
        total += hand.glide(tracker, 0.5, 0.1)[1] + hand.rest(tracker, 0.1)[1]
        total += hand.glide(tracker, -0.5, 1.0)[1]   # slow return
        total += hand.rest(tracker, 0.1)[1]
    assert total >= 6
