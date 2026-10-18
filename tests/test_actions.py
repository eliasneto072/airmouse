"""Named actions registry."""

from core.actions import ACTIONS, run_action
from tests.fakes import FakeActuator


def test_run_action_sends_the_combo():
    actuator = FakeActuator()
    assert run_action(actuator, "prev_tab")
    assert actuator.combos() == [("ctrl", "shift", "tab")]


def test_unbound_and_unknown_actions_do_nothing():
    actuator = FakeActuator()
    assert not run_action(actuator, None)
    assert not run_action(actuator, "does_not_exist")
    assert actuator.calls == []


def test_every_action_uses_known_key_names():
    special = {
        "alt", "ctrl", "shift", "cmd", "tab", "left", "right", "up", "down", "enter", "esc", "f4",
        "media_play_pause", "media_next", "media_previous",
        "media_volume_up", "media_volume_down", "media_volume_mute",
    }
    for name, keys in ACTIONS.items():
        for key in keys:
            assert len(key) == 1 or key in special, f"{name}: {key}"
