# core/gestures/modal.py
"""Modal interaction pipeline: classify → stabilize → ModeManager → mode handlers."""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Callable

from config import (
    ATTENTION_GATE,
    ATTENTION_MAX_ANGLE,
    DOMINANT_HAND,
    LEFT_HAND_ENABLED,
    MODE_START_NEEDS_FIST,
    MODES_ENABLED,
    SCROLL_STYLE,
    WINDOW_BINDINGS,
)
from core.display import TrackpadZone, VirtualDesktop
from core.gestures.mode_manager import Mode, ModeManager, ModalStatus
from core.gestures.modes.media import MediaMode
from core.gestures.modes.move import MoveMode
from core.gestures.modes.scroll import ScrollMode
from core.gestures.modes.shortcuts import ShortcutsMode
from core.gestures.poses import PoseClassifier
from core.gestures.support_hand import SupportHand
from core.pointer import Pointer
from core.tracker import HandsResult

logger = logging.getLogger(__name__)


class ModalOrchestrator:
    """
    Drop-in replacement for GestureOrchestrator when INTERACTION_MODE = "modal".

    Args:
        hud:       object with update(ModalStatus) / stop(), or None
        sounds:    object with play(event), or None
        attention: AttentionGate (process(frame, now, adapt) / calibrate() / close()), or None
        clock:     time source (tests inject a fake one)
    """

    def __init__(
        self,
        actuator,
        desktop: VirtualDesktop,
        trackpad: TrackpadZone,
        hud=None,
        sounds=None,
        dominant_hand: str = DOMINANT_HAND,
        enabled: tuple[str, ...] = MODES_ENABLED,
        start_needs_fist: tuple[str, ...] = MODE_START_NEEDS_FIST,
        scroll_style: str = SCROLL_STYLE,
        support_hand: bool = LEFT_HAND_ENABLED,
        attention=None,
        attention_gate: str = ATTENTION_GATE,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if dominant_hand not in ("right", "left"):
            raise ValueError(f"DOMINANT_HAND must be 'right' or 'left', not {dominant_hand!r}")
        self._actuator = actuator
        self._dominant = dominant_hand
        self._clock = clock
        self._hud = hud
        self._sounds = sounds
        if attention_gate not in ("always", "start", "off"):
            raise ValueError(f"ATTENTION_GATE must be 'always', 'start' or 'off', not {attention_gate!r}")
        self._attention = attention if attention_gate != "off" else None
        self._attention_gate = attention_gate
        self._attention_on = self._attention is not None
        self._started = False
        self._toast: tuple[str, float] | None = None
        self._last_attention: tuple[bool, bool] | None = None  # (face, looking), for logging changes
        self._attention_text = ""
        self._classifier = PoseClassifier()
        self._support_classifier = PoseClassifier()
        self._support = SupportHand(actuator) if support_hand else None
        self._pointer = Pointer(actuator, desktop, trackpad)
        handlers = {
            Mode.MOVE: MoveMode(actuator, self._pointer),
            Mode.SCROLL: ScrollMode(actuator, style=scroll_style),
            Mode.SHORTCUTS: ShortcutsMode(actuator),
            Mode.MEDIA: MediaMode(actuator),
            Mode.WINDOWS: ShortcutsMode(actuator, WINDOW_BINDINGS, name="windows", setting="WINDOW_BINDINGS"),
        }
        self._manager = ModeManager(
            handlers, actuator, enabled=enabled, start_needs_fist=start_needs_fist, on_event=self._on_event
        )
        logger.info(
            "Modal mode ready (dominant hand: %s, modes: %s, support hand: %s) — hold 1–4 fingers still to start",
            dominant_hand,
            ", ".join(enabled),
            "on" if support_hand else "off",
        )
        if self._hud is not None:
            self._hud.update(self._manager.status)

    @property
    def manager(self) -> ModeManager:
        return self._manager

    @property
    def status(self) -> ModalStatus:
        status = self._manager.status
        now = self._clock()
        if self._toast is not None and now - self._toast[1] < 1.5:
            return dataclasses.replace(status, support=self._toast[0])
        if self._support is not None:
            status = dataclasses.replace(status, support=self._support.status_text(now))
        return status

    @property
    def attention_on(self) -> bool:
        return self._attention_on

    @property
    def right_state(self) -> str:
        """Short state text for the debug overlay."""
        status = self._manager.status
        text = status.mode.name
        if status.paused:
            text += " (paused)"
        if status.pending:
            text += f" → {status.pending} {status.progress:.0%}"
        if self._attention_on and self._attention_text:
            text += f" | {self._attention_text}"
        return text

    def process(self, hands: HandsResult, frame=None) -> None:
        now = self._clock()
        facing = looking = True
        if self._attention is not None and self._attention_on:
            mode_on = self._manager.mode != Mode.DISARMED and not self._manager.paused
            state = self._attention.process(frame, now, adapt=mode_on)
            facing = state.facing
            looking = state.looking if self._attention_gate == "always" else True
            self._log_attention(state)

        if self._dominant == "right":
            dominant_lm, support_lm = hands.right, hands.left
        else:
            dominant_lm, support_lm = hands.left, hands.right

        if dominant_lm is None:
            self._classifier.reset()
            hand = None
        else:
            hand = self._classifier.classify(dominant_lm)
        self._started = False
        self._manager.process(hand, now, facing=facing, looking=looking)
        if self._started and self._attention_on and self._manager.started_with_override:
            self._attention.calibrate()  # started on purpose while "not facing": that is where the screen is

        if self._support is not None:
            if support_lm is None:
                self._support_classifier.reset()
                support = None
            else:
                support = self._support_classifier.classify(support_lm)
            self._support.process(
                support,
                now,
                active=self._manager.mode != Mode.DISARMED,
                dominant_visible=hand is not None,
                enabled=looking and (facing or self._manager.mode != Mode.DISARMED),
            )

        if self._hud is not None:
            self._hud.update(self.status)

    def shutdown(self) -> None:
        if self._support is not None:
            self._support.release()
        self._manager.disarm()
        self._actuator.release_all()
        if self._hud is not None:
            self._hud.stop()
        if self._attention is not None:
            self._attention.close()

    def _log_attention(self, state) -> None:
        if state.face and state.angle is not None:
            self._attention_text = f"look {state.angle:.0f}°"
        else:
            self._attention_text = "look: no face"
        key = (state.face, state.looking)
        if key == self._last_attention:
            return
        self._last_attention = key
        if not state.face:
            logger.info("Look check: no face found — gestures count")
        elif state.looking:
            logger.info("Look check: looking at the screen (head %.0f° from the screen direction)", state.angle)
        else:
            logger.info(
                "Look check: NOT looking (head %.0f° from the screen direction, limit %s°) — "
                "hold 👌 1.5 s to turn the check off",
                state.angle,
                ATTENTION_MAX_ANGLE,
            )

    def _on_event(self, event: str, mode: Mode) -> None:
        if event == "arm":
            self._started = True
        if event == "toggle_attention":
            if self._attention is None:
                self._toast = ("look check unavailable", self._clock())
                return
            self._attention_on = not self._attention_on
            self._toast = ("look check ON" if self._attention_on else "look check OFF", self._clock())
            logger.info("Look check %s", "on" if self._attention_on else "off")
            event = "attention_on" if self._attention_on else "attention_off"
        if self._sounds is not None:
            self._sounds.play(event)
