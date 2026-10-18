# core/gestures/mode_manager.py
"""
Global state machine of the modal interaction layer.

    DISARMED ── hold ☝️ still ARM_HOLD_S ──► MOVE
    armed    ── hold N fingers MODE_SWITCH_HOLD_S ──► mode N (1 MOVE, 2 SCROLL, 3 SHORTCUTS, 4 MEDIA)
    armed    ── fist ──► paused (mode suspended; reopen the hand to resume)
    paused   ── fist held DISARM_HOLD_S ──► DISARMED
    armed    ── hand out of frame AUTO_DISARM_S ──► DISARMED

While DISARMED nothing is sent to the OS, whatever the hand does.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from config import (
    ARM_HOLD_S,
    ARM_STILLNESS,
    AUTO_DISARM_S,
    DISARM_HOLD_S,
    HAND_LOST_RELEASE_S,
    MODE_SWITCH_HOLD_S,
    MODES_ENABLED,
)
from core.gestures.modes.base import ModeHandler
from core.gestures.poses import POSE_FINGER_COUNT, HandPose, Pose
from core.gestures.stabilizer import PoseStabilizer

logger = logging.getLogger(__name__)


class Mode(Enum):
    DISARMED = "disarmed"
    MOVE = "move"
    SCROLL = "scroll"
    SHORTCUTS = "shortcuts"
    MEDIA = "media"


MODE_FOR_FINGERS = {1: Mode.MOVE, 2: Mode.SCROLL, 3: Mode.SHORTCUTS, 4: Mode.MEDIA}


@dataclass(frozen=True)
class ModalStatus:
    """Snapshot for the HUD / debug overlay."""

    mode: Mode
    paused: bool
    hand_visible: bool
    pending: str | None   # "arm", "disarm" or the name of the mode being switched to
    progress: float       # 0..1 progress of the pending hold


class ModeManager:
    def __init__(
        self,
        handlers: dict[Mode, ModeHandler],
        actuator,
        enabled: tuple[str, ...] = MODES_ENABLED,
        on_event: Callable[[str, Mode], None] | None = None,
        arm_hold_s: float = ARM_HOLD_S,
        arm_stillness: float = ARM_STILLNESS,
        switch_hold_s: float = MODE_SWITCH_HOLD_S,
        disarm_hold_s: float = DISARM_HOLD_S,
        auto_disarm_s: float = AUTO_DISARM_S,
        hand_lost_release_s: float = HAND_LOST_RELEASE_S,
    ) -> None:
        self._handlers = handlers
        self._actuator = actuator
        self._enabled = {Mode(name) for name in enabled} & set(handlers)
        if not self._enabled:
            raise ValueError("MODES_ENABLED must contain at least one mode")
        self._first_mode = Mode.MOVE if Mode.MOVE in self._enabled else next(
            m for m in MODE_FOR_FINGERS.values() if m in self._enabled
        )
        self._on_event = on_event or (lambda event, mode: None)
        self._arm_hold_s = arm_hold_s
        self._arm_stillness = arm_stillness
        self._switch_hold_s = switch_hold_s
        self._disarm_hold_s = disarm_hold_s
        self._auto_disarm_s = auto_disarm_s
        self._hand_lost_release_s = hand_lost_release_s

        self._stabilizer = PoseStabilizer()
        self.mode = Mode.DISARMED
        self.paused = False
        self._hand_visible = False
        self._hold_target: str | Mode | None = None
        self._hold_since = 0.0
        self._hold_origin: tuple[float, float] | None = None
        self._hold_progress = 0.0
        self._fist_since = 0.0
        self._lost_since: float | None = None
        self._released_on_loss = False

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def status(self) -> ModalStatus:
        pending: str | None = None
        if isinstance(self._hold_target, Mode):
            pending = self._hold_target.value
        elif self._hold_target is not None:
            pending = self._hold_target
        return ModalStatus(self.mode, self.paused, self._hand_visible, pending, self._hold_progress)

    @property
    def handler(self) -> ModeHandler | None:
        return self._handlers.get(self.mode)

    def disarm(self) -> None:
        if self.mode == Mode.DISARMED:
            return
        self.handler.exit()
        self._actuator.release_all()
        self.mode = Mode.DISARMED
        self.paused = False
        self._clear_hold()
        logger.info("Disarmed")
        self._on_event("disarm", self.mode)

    def process(self, hand: HandPose | None, now: float) -> None:
        if hand is None:
            self._no_hand(now)
            return

        self._hand_visible = True
        if self._lost_since is not None:
            if self._released_on_loss and self.mode != Mode.DISARMED and not self.paused:
                self.handler.resume(hand, now)
            self._lost_since = None
            self._released_on_loss = False

        pose = self._stabilizer.update(hand.pose, now)

        if self.mode == Mode.DISARMED:
            self._process_disarmed(hand, pose, now)
            return

        if pose == Pose.FIST and not hand.any_pinch:
            if not self.paused:
                self.paused = True
                self._fist_since = now
                self._clear_hold()
                self.handler.pause(now)
                self._on_event("pause", self.mode)
            self._hold_target = "disarm"
            self._hold_progress = min(1.0, (now - self._fist_since) / self._disarm_hold_s)
            if now - self._fist_since >= self._disarm_hold_s:
                self.disarm()
            return

        if self.paused:
            self.paused = False
            self._clear_hold()
            self.handler.resume(hand, now)
            self._on_event("resume", self.mode)

        if self._update_switch(hand, pose, now):
            return
        self.handler.process(hand, pose, now)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _clear_hold(self) -> None:
        self._hold_target = None
        self._hold_origin = None
        self._hold_progress = 0.0

    def _process_disarmed(self, hand: HandPose, pose: Pose, now: float) -> None:
        if pose != Pose.ONE or hand.any_pinch:
            self._clear_hold()
            return
        moved = (
            self._hold_origin is not None
            and math.dist(hand.wrist, self._hold_origin) / hand.scale > self._arm_stillness
        )
        if self._hold_target != "arm" or moved:
            self._hold_target = "arm"
            self._hold_since = now
            self._hold_origin = hand.wrist
            self._hold_progress = 0.0
            return
        self._hold_progress = min(1.0, (now - self._hold_since) / self._arm_hold_s)
        if now - self._hold_since >= self._arm_hold_s:
            self._clear_hold()
            self.mode = self._first_mode
            self.paused = False
            self.handler.enter(hand, now)
            logger.info("Armed → %s", self.mode.name)
            self._on_event("arm", self.mode)

    def _update_switch(self, hand: HandPose, pose: Pose, now: float) -> bool:
        target = MODE_FOR_FINGERS.get(POSE_FINGER_COUNT.get(pose, 0))
        if (
            target is None
            or target == self.mode
            or target not in self._enabled
            or hand.any_pinch
            or self.handler.busy
        ):
            self._clear_hold()
            return False
        if self._hold_target != target:
            self._hold_target = target
            self._hold_since = now
            self._hold_progress = 0.0
            return False
        self._hold_progress = min(1.0, (now - self._hold_since) / self._switch_hold_s)
        if now - self._hold_since < self._switch_hold_s:
            return False
        self._clear_hold()
        self.handler.exit()
        self.mode = target
        self.handler.enter(hand, now)
        logger.info("Mode → %s", self.mode.name)
        self._on_event("switch", self.mode)
        return True

    def _no_hand(self, now: float) -> None:
        self._hand_visible = False
        self._clear_hold()
        if self._lost_since is None:
            self._lost_since = now
        if self.mode == Mode.DISARMED:
            return
        lost = now - self._lost_since
        if lost >= self._hand_lost_release_s and not self._released_on_loss:
            self._released_on_loss = True
            self._stabilizer.reset()
            if not self.paused:
                self.handler.hand_lost()
        if lost >= self._auto_disarm_s:
            self.disarm()
