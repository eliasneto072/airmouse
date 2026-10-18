"""Left hand (support hand) in modal mode."""

import pytest

from core.display import TrackpadZone, VirtualDesktop
from core.gestures.modal import ModalOrchestrator
from core.gestures.mode_manager import Mode
from core.tracker import HandsResult
from tests.fakes import FakeActuator, FakeClock
from tests.fixtures.hands import make_hand

FRAME = (1280, 720)
DT = 1 / 75
SCALE = 0.25
RIGHT_HOME = (0.35, 0.8)   # raw frame is unmirrored: the user's right hand is on the image's left
LEFT_HOME = (0.75, 0.8)
HAND_LENGTH_X = SCALE * 720 / 1280


class Rig:
    def __init__(self, dominant="right"):
        self.clock = FakeClock()
        self.actuator = FakeActuator()
        self.actuator.pos = (960, 540)
        self.dominant = dominant
        self.modal = ModalOrchestrator(
            self.actuator,
            VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1),
            TrackpadZone(x_min=100, x_max=1180, y_min=100, y_max=620),
            dominant_hand=dominant,
            enabled=("move", "scroll", "shortcuts", "media", "windows"),
            start_needs_fist=("windows",),
            support_hand=True,
            clock=self.clock,
        )

    def frames(self, seconds, right="point", left=None, left_pinch=None, left_end=None, right_visible=True):
        """right / left: pose names or None (hand not visible). left_end: glide the left hand."""
        n = max(1, round(seconds / DT))
        for i in range(1, n + 1):
            self.clock.advance(DT)
            r = make_hand(right, center=RIGHT_HOME, scale=SCALE, frame=FRAME) if right_visible and right else None
            l = None
            if left:
                c = LEFT_HOME
                if left_end is not None:
                    c = (LEFT_HOME[0] + (left_end[0] - LEFT_HOME[0]) * i / n, LEFT_HOME[1])
                l = make_hand(left, pinch=left_pinch, center=c, scale=SCALE, frame=FRAME)
            if self.dominant == "left":
                r, l = l, r
            self.modal.process(HandsResult(right=r, left=l))

    def arm(self):
        self.frames(0.9)
        assert self.modal.manager.mode == Mode.MOVE

    @property
    def held(self):
        return self.actuator.held


def test_left_hand_is_ignored_while_off():
    rig = Rig()
    rig.frames(1.0, right=None, left="peace")
    rig.frames(1.0, right=None, left="three")
    assert rig.actuator.calls == []


def test_held_window_switcher():
    rig = Rig()
    rig.arm()
    rig.frames(0.5, left="peace")
    assert "alt" in rig.held
    assert rig.actuator.combos() == [("tab",)]
    rig.frames(0.1, left="peace", left_pinch="index")   # thumb tap → next window
    rig.frames(0.1, left="peace")
    rig.frames(0.1, left="peace", left_pinch="middle")  # → previous window
    rig.frames(0.1, left="peace")
    assert rig.actuator.combos() == [("tab",), ("tab",), ("shift", "tab")]
    rig.frames(0.3, left="point")                        # drop the V → pick the window
    assert "alt" not in rig.held


def test_window_switcher_lets_go_after_max_time():
    rig = Rig()
    rig.arm()
    rig.frames(11.0, left="peace")
    assert "alt" not in rig.held


def test_ctrl_only_while_right_hand_is_visible():
    rig = Rig()
    rig.arm()
    rig.frames(0.3, left="three")     # open pose first: the fist is closed in view
    rig.frames(0.6, left="fist")
    assert "ctrl" in rig.held
    rig.frames(0.2, left="fist", right_visible=False)
    assert "ctrl" not in rig.held


def test_resting_fist_never_holds_ctrl():
    rig = Rig()
    rig.arm()
    rig.frames(2.0, left="fist")      # the left hand enters the frame already closed
    assert "ctrl" not in rig.held


def test_one_finger_swipes_go_back_and_forward():
    rig = Rig()
    rig.arm()
    rig.frames(0.3, left="point")
    # flick towards the user's left = larger raw x
    rig.frames(0.1, left="point", left_end=(LEFT_HOME[0] + 0.8 * HAND_LENGTH_X, LEFT_HOME[1]))
    rig.frames(0.5, left="point")
    assert ("alt", "left") in rig.actuator.combos()


def test_three_fingers_fire_task_view_once():
    rig = Rig()
    rig.arm()
    rig.frames(3.0, left="three")
    assert rig.actuator.combos() == [("cmd", "tab")]


def test_resting_open_left_hand_does_not_show_desktop():
    rig = Rig()
    rig.arm()
    rig.frames(3.0, left="open")
    assert ("cmd", "d") not in rig.actuator.combos()


def test_fist_then_open_left_hand_shows_desktop():
    rig = Rig()
    rig.arm()
    rig.frames(0.2, left="fist")
    rig.frames(1.2, left="open")
    assert ("cmd", "d") in rig.actuator.combos()


def test_ok_sign_opens_start():
    rig = Rig()
    rig.arm()
    rig.frames(0.6, left="open", left_pinch="index")
    assert ("cmd",) in rig.actuator.combos()


def test_turning_off_releases_left_hand_keys():
    rig = Rig()
    rig.arm()
    rig.frames(0.5, left="peace")
    assert "alt" in rig.held
    rig.frames(1.6, right="fist", left="peace")   # right fist held → OFF
    assert rig.modal.manager.mode == Mode.DISARMED
    assert not rig.held


def test_left_handed_users_swap_roles():
    rig = Rig(dominant="left")
    rig.frames(0.9)                    # the "right" argument is now the left hand
    assert rig.modal.manager.mode == Mode.MOVE
    rig.frames(0.6, left="three")      # and this is the right hand
    assert rig.actuator.combos() == [("cmd", "tab")]


def test_hud_shows_support_state():
    rig = Rig()
    rig.arm()
    rig.frames(0.5, left="peace")
    assert rig.modal.status.support == "ALT+TAB"
