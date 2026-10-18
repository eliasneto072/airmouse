# core/gestures/modal.py
"""Modal interaction pipeline: classify → stabilize → ModeManager → mode handlers."""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Callable

from config import (
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
        hud:    object with update(ModalStatus) / stop(), or None
        sounds: object with play(event), or None
        clock:  time source (tests inject a fake one)
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
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if dominant_hand not in ("right", "left"):
            raise ValueError(f"DOMINANT_HAND must be 'right' or 'left', not {dominant_hand!r}")
        self._actuator = actuator
        self._dominant = dominant_hand
        self._clock = clock
        self._hud = hud
        self._sounds = sounds
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
        if self._support is not None:
            status = dataclasses.replace(status, support=self._support.status_text(self._clock()))
        return status

    @property
    def right_state(self) -> str:
        """Short state text for the debug overlay."""
        status = self._manager.status
        text = status.mode.name
        if status.paused:
            text += " (paused)"
        if status.pending:
            text += f" → {status.pending} {status.progress:.0%}"
        return text

    def process(self, hands: HandsResult) -> None:
        now = self._clock()
        if self._dominant == "right":
            dominant_lm, support_lm = hands.right, hands.left
        else:
            dominant_lm, support_lm = hands.left, hands.right

        if dominant_lm is None:
            self._classifier.reset()
            hand = None
        else:
            hand = self._classifier.classify(dominant_lm)
        self._manager.process(hand, now)

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

    def _on_event(self, event: str, mode: Mode) -> None:
        if self._sounds is not None:
            self._sounds.play(event)
