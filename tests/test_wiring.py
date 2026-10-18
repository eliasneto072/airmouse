"""build_orchestrator and feedback plumbing."""

import pytest

from core.display import TrackpadZone, VirtualDesktop
from core.feedback import Sounds
from core.gestures import build_orchestrator
from core.gestures.modal import ModalOrchestrator
from core.gestures.orchestrator import GestureOrchestrator
from tests.fakes import FakeActuator

DESKTOP = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
TRACKPAD = TrackpadZone(x_min=100, x_max=1180, y_min=100, y_max=620)


def test_classic_is_the_default():
    assert isinstance(build_orchestrator(FakeActuator(), DESKTOP, TRACKPAD), GestureOrchestrator)


def test_modal_mode():
    actuator = FakeActuator()
    modal = build_orchestrator(
        actuator, DESKTOP, TRACKPAD, mode="modal", hud_enabled=False, sounds_enabled=False, attention_gate="off"
    )
    assert isinstance(modal, ModalOrchestrator)
    assert modal.right_state == "DISARMED"
    modal.shutdown()
    assert not actuator.held


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        build_orchestrator(FakeActuator(), DESKTOP, TRACKPAD, mode="magic")


def test_sounds_ignore_unknown_events():
    Sounds().play("not-an-event")  # must not raise
