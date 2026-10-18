"""End-to-end tests of the modal interaction layer (synthetic hands, fake clock/actuator)."""

import pytest

from core.display import TrackpadZone, VirtualDesktop
from core.gestures.modal import ModalOrchestrator
from core.gestures.mode_manager import Mode
from core.tracker import HandsResult
from tests.fakes import FakeActuator, FakeClock
from tests.fixtures.hands import make_hand

FRAME = (1280, 720)
DT = 1 / 75
SCALE = 0.25                    # hand length = 180 px
HAND_LENGTH_X = SCALE * 720 / 1280  # one hand length in normalized x
HAND_LENGTH_Y = SCALE             # one hand length in normalized y
HOME = (0.5, 0.8)


class Rig:
    def __init__(
        self,
        enabled=("move", "scroll", "shortcuts", "media", "windows"),
        start_needs_fist=False,
        scroll_style="stroke",
    ):
        self.clock = FakeClock()
        self.actuator = FakeActuator()
        self.actuator.pos = (960, 540)
        self.sounds = []
        self.modal = ModalOrchestrator(
            self.actuator,
            VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1),
            TrackpadZone(x_min=100, x_max=1180, y_min=100, y_max=620),
            sounds=self,
            enabled=enabled,
            start_needs_fist=start_needs_fist,
            scroll_style=scroll_style,
            clock=self.clock,
        )

    # sounds stub
    def play(self, event):
        self.sounds.append(event)

    @property
    def mode(self):
        return self.modal.manager.mode

    @property
    def paused(self):
        return self.modal.manager.paused

    def hold(self, seconds, pose="point", pinch=None, center=HOME, end=None):
        """Feed a pose for `seconds`; with `end`, the wrist glides from center to end."""
        n = max(1, round(seconds / DT))
        for i in range(1, n + 1):
            if end is None:
                c = center
            else:
                c = (center[0] + (end[0] - center[0]) * i / n, center[1] + (end[1] - center[1]) * i / n)
            self.clock.advance(DT)
            self.modal.process(HandsResult(right=make_hand(pose, pinch=pinch, center=c, scale=SCALE, frame=FRAME)))

    def no_hand(self, seconds):
        for _ in range(max(1, round(seconds / DT))):
            self.clock.advance(DT)
            self.modal.process(HandsResult())

    def arm(self):
        self.hold(0.9)
        assert self.mode == Mode.MOVE

    def tap(self, finger="index", pose="point", center=HOME):
        """Pinch, release, and wait for the click to be confirmed (CLICK_CONFIRM_S)."""
        self.hold(0.12, pose=pose, pinch=finger, center=center)
        self.hold(0.15, pose=pose, center=center)

    def switch(self, pose):
        """Hold a fist until OFF, then open straight into the new number."""
        self.hold(1.4, pose="fist")
        assert self.mode == Mode.DISARMED
        self.hold(0.7, pose=pose)


def above(dy_hand_lengths, base=HOME):
    return (base[0], base[1] - dy_hand_lengths * HAND_LENGTH_Y)


def users_right(dx_hand_lengths, base=HOME):
    return (base[0] - dx_hand_lengths * HAND_LENGTH_X, base[1])  # raw frame is unmirrored


# ── Arming / disarming ────────────────────────────────────────────────────────

def test_starts_disarmed_and_ignores_everything():
    rig = Rig()
    rig.hold(0.5, pose="open")
    rig.hold(0.3, pose="point", pinch="index")
    rig.hold(0.5, pose="peace", end=above(1.0))
    rig.hold(0.5, pose="fist")
    rig.hold(0.4, pose="three", end=users_right(1.0))
    assert rig.mode == Mode.DISARMED
    assert rig.actuator.calls == []


def test_moving_pointing_hand_does_not_arm():
    # e.g. scratching the face with the index finger
    rig = Rig()
    rig.hold(2.0, pose="point", center=(0.6, 0.8), end=(0.3, 0.8))
    assert rig.mode == Mode.DISARMED
    assert rig.actuator.calls == []


def test_still_pointing_hand_arms_into_move():
    rig = Rig()
    rig.hold(0.5)
    assert rig.mode == Mode.DISARMED
    rig.hold(0.4)
    assert rig.mode == Mode.MOVE
    assert rig.sounds == ["arm"]


def test_fist_pauses_and_long_fist_disarms():
    rig = Rig()
    rig.arm()
    rig.hold(0.3, pose="fist")
    assert rig.mode == Mode.MOVE and rig.paused
    rig.hold(0.3)
    assert not rig.paused
    rig.hold(1.8, pose="fist")
    assert rig.mode == Mode.DISARMED
    assert rig.sounds[-1] == "disarm"


def test_hand_out_of_frame_disarms():
    rig = Rig()
    rig.arm()
    rig.no_hand(1.0)
    assert rig.mode == Mode.MOVE
    rig.no_hand(1.2)
    assert rig.mode == Mode.DISARMED


# ── MOVE ──────────────────────────────────────────────────────────────────────

def test_move_mode_moves_cursor():
    rig = Rig()
    rig.arm()
    rig.hold(0.5, end=users_right(0.6))
    rig.hold(0.3, center=users_right(0.6))
    assert rig.actuator.pos[0] > 960 + 100


def test_tap_clicks_and_double_tap_double_clicks():
    rig = Rig()
    rig.arm()
    rig.tap()
    assert rig.actuator.count("left_click") == 1
    rig.hold(0.6)
    rig.tap()
    rig.hold(0.1)
    rig.tap()
    assert rig.actuator.count("left_click") == 3
    second, third = rig.actuator.positions("left_click")[1:]
    assert second == third


def test_pinch_hold_drags_and_hand_loss_releases():
    rig = Rig()
    rig.arm()
    rig.hold(0.6, pinch="index")
    assert rig.actuator.is_dragging
    rig.no_hand(0.5)
    assert not rig.actuator.held  # safety: nothing stays pressed


def test_right_click_with_thumb_on_middle():
    rig = Rig()
    rig.arm()
    rig.hold(1.0, pose="peace", pinch="middle")  # held: fires once, does not switch mode
    assert rig.actuator.count("right_click") == 1
    assert rig.mode == Mode.MOVE


def test_fist_is_a_clutch():
    rig = Rig()
    rig.arm()
    before = rig.actuator.pos
    rig.hold(0.3, pose="fist")
    rig.hold(0.4, pose="fist", end=users_right(1.0))   # reposition the hand
    rig.hold(0.4, center=users_right(1.0))             # reopen: no jump
    assert abs(rig.actuator.pos[0] - before[0]) < 30


# ── SCROLL ────────────────────────────────────────────────────────────────────

def test_two_fingers_switch_to_scroll_and_hand_height_scrolls():
    rig = Rig()
    rig.arm()
    rig.switch("peace")
    assert rig.mode == Mode.SCROLL
    moves_before = rig.actuator.count("move")

    rig.hold(0.2, pose="peace")                       # at the center: nothing
    assert rig.actuator.count("scroll") == 0
    rig.hold(0.2, pose="peace", end=above(0.8))
    rig.hold(0.5, pose="peace", center=above(0.8))
    assert rig.actuator.total("scroll") > 0           # up
    up = rig.actuator.total("scroll")
    rig.hold(0.2, pose="peace", end=above(-0.8))
    rig.hold(0.5, pose="peace", center=above(-0.8))
    assert rig.actuator.total("scroll") < up          # then down
    assert rig.actuator.count("move") == moves_before  # cursor does not move


def test_scroll_strokes_horizontal_and_zoom():
    rig = Rig()
    rig.arm()
    rig.switch("peace")
    rig.hold(0.15, pose="peace", end=users_right(0.8))      # quick stroke to the right
    rig.hold(0.3, pose="peace", center=users_right(0.8))
    assert rig.actuator.total("hscroll") > 0

    rig.hold(1.5, pose="peace", center=users_right(0.8), end=HOME)  # slow return: nothing
    assert rig.actuator.total("scroll") == 0
    rig.hold(0.15, pose="peace", pinch="index", end=above(0.8))     # pinch + stroke up
    rig.hold(0.3, pose="peace", pinch="index", center=above(0.8))
    assert ("ctrl", "=") in rig.actuator.combos()


def test_scroll_flick_up_then_slow_return_then_flick_again():
    rig = Rig()
    rig.arm()
    rig.switch("peace")
    for _ in range(2):
        rig.hold(0.12, pose="peace", end=above(0.5))
        rig.hold(0.1, pose="peace", center=above(0.5))
        rig.hold(1.2, pose="peace", center=above(0.5), end=HOME)   # bring the hand back slowly
    ticks = [args[0] for name, args, _ in rig.actuator.calls if name == "scroll"]
    assert ticks and all(t > 0 for t in ticks)
    assert 2 <= sum(ticks) <= 12   # a flick scrolls a little, not a page


def test_joystick_scroll_style_still_available():
    rig = Rig(scroll_style="joystick")
    rig.arm()
    rig.switch("peace")
    rig.hold(0.2, pose="peace", end=above(0.8))
    rig.hold(0.5, pose="peace", center=above(0.8))
    assert rig.actuator.total("scroll") > 0


# ── SHORTCUTS ─────────────────────────────────────────────────────────────────

def test_three_fingers_switch_to_shortcuts_swipes_and_taps():
    rig = Rig()
    rig.arm()
    rig.switch("three")
    assert rig.mode == Mode.SHORTCUTS
    rig.hold(0.1, pose="three", end=users_right(0.8))   # quick flick to the right
    rig.hold(0.4, pose="three", center=users_right(0.8))
    assert rig.actuator.combos() == [("ctrl", "tab")]
    rig.tap(pose="three", center=users_right(0.8))
    assert rig.actuator.combos()[-1] == ("enter",)


def test_slow_movement_is_not_a_swipe():
    rig = Rig()
    rig.arm()
    rig.switch("three")
    rig.hold(1.5, pose="three", end=users_right(1.0))
    assert rig.actuator.combos() == []


# ── MEDIA ─────────────────────────────────────────────────────────────────────

def test_four_fingers_media_volume_and_play_pause():
    rig = Rig()
    rig.arm()
    rig.switch("four")
    assert rig.mode == Mode.MEDIA
    rig.hold(0.2, pose="four", end=above(0.8))
    rig.hold(0.5, pose="four", center=above(0.8))
    assert ("media_volume_up",) in rig.actuator.combos()
    rig.hold(0.3, pose="four", center=HOME)
    rig.tap(pose="four")
    assert rig.actuator.combos()[-1] == ("media_play_pause",)


def test_disabled_mode_is_never_entered():
    rig = Rig(enabled=("move", "scroll"))
    rig.arm()
    rig.switch("four")
    assert rig.mode == Mode.DISARMED


def test_back_to_move_from_scroll():
    rig = Rig()
    rig.arm()
    rig.switch("peace")
    rig.switch("point")
    assert rig.mode == Mode.MOVE
    assert [e for e in rig.sounds if e != "pause"] == ["arm", "disarm", "arm", "disarm", "arm"]


# ── Locked modes and choosing a mode ──────────────────────────────────────────

def test_modes_are_locked_open_palm_keeps_moving():
    rig = Rig()
    rig.arm()
    rig.hold(2.0, pose="open")                 # would have been MEDIA before
    rig.hold(1.0, pose="peace")
    rig.hold(1.0, pose="three")
    assert rig.mode == Mode.MOVE
    before = rig.actuator.pos
    rig.hold(0.5, pose="open", end=users_right(0.6))
    assert rig.actuator.pos[0] > before[0] + 100  # the open palm drives the cursor


def test_scroll_works_with_any_hand_shape():
    rig = Rig()
    rig.arm()
    rig.switch("peace")
    rig.hold(0.2, pose="open", end=above(0.8))
    rig.hold(0.5, pose="open", center=above(0.8))
    assert rig.mode == Mode.SCROLL
    assert rig.actuator.total("scroll") > 0


def test_any_number_held_still_starts_its_mode():
    for pose, mode in [("peace", Mode.SCROLL), ("three", Mode.SHORTCUTS), ("four", Mode.MEDIA), ("open", Mode.WINDOWS)]:
        rig = Rig()
        rig.hold(0.9, pose=pose)
        assert rig.mode == mode, pose


def test_with_start_needs_fist_a_resting_open_hand_does_not_start_a_mode():
    rig = Rig(start_needs_fist=True)
    rig.hold(3.0, pose="open")
    rig.hold(3.0, pose="peace")
    assert rig.mode == Mode.DISARMED
    assert rig.actuator.calls == []


def test_fist_then_number_starts_that_mode():
    rig = Rig()
    rig.hold(0.3, pose="fist")
    rig.hold(0.6, pose="three")
    assert rig.mode == Mode.SHORTCUTS


def test_number_shown_too_late_after_fist_is_ignored():
    rig = Rig(start_needs_fist=True)
    rig.hold(0.3, pose="fist")
    rig.hold(1.8, pose="point", center=(0.6, 0.8), end=(0.3, 0.8))  # moving: no arm
    rig.hold(1.0, pose="peace")
    assert rig.mode == Mode.DISARMED


def test_moving_number_after_fist_does_not_select():
    rig = Rig(start_needs_fist=True)
    rig.hold(0.3, pose="fist")
    rig.hold(1.4, pose="four", center=(0.6, 0.8), end=(0.3, 0.8))
    assert rig.mode == Mode.DISARMED


def test_closing_the_hand_into_a_fist_does_not_click():
    # On the way to a fist the thumb passes the index tip, which looks like a tap.
    rig = Rig()
    rig.arm()
    rig.hold(0.07, pinch="index")
    rig.hold(0.6, pose="fist")
    assert rig.actuator.count("left_click") == 0
    assert rig.paused


def test_open_palm_is_five_and_four_is_media():
    rig = Rig()
    rig.hold(0.9, pose="four")
    assert rig.mode == Mode.MEDIA
    rig.switch("open")
    assert rig.mode == Mode.WINDOWS


def test_windows_mode_swipes():
    rig = Rig()
    rig.hold(0.9, pose="open")
    assert rig.mode == Mode.WINDOWS
    rig.hold(0.1, pose="open", end=users_right(0.8))
    rig.hold(0.4, pose="open", center=users_right(0.8))
    assert rig.actuator.combos() == [("cmd", "right")]
