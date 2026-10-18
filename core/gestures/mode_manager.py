# core/gestures/mode_manager.py
"""
Global state machine of the modal interaction layer.

    OFF ── 1–5 fingers held still ARM_HOLD_S ───────────────────► MOVE / SCROLL / SHORTCUTS / MEDIA / WINDOWS
    OFF ── fist, then 1–5 fingers held still MODE_SELECT_HOLD_S ──► (same, quicker)
    mode ── fist ──► paused (open the hand to continue the same mode)
    mode ── fist held DISARM_HOLD_S, or hand out of view AUTO_DISARM_S ──► OFF

Modes are locked: while a mode is active, the shape of the hand never switches
to another mode (an open palm in MOVE keeps moving the cursor). Changing mode
is always deliberate: hold a fist until OFF, then show the new number — one
continuous gesture. With MODE_START_NEEDS_FIST, 2–5 fingers only start a mode
right after a fist (for setups where a resting open hand is in view).

While OFF nothing is sent to the OS, whatever the hand does.
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
    MODE_SELECT_HOLD_S,
    MODE_SELECT_WINDOW_S,
    MODE_START_NEEDS_FIST,
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
    WINDOWS = "windows"


MODE_FOR_FINGERS = {1: Mode.MOVE, 2: Mode.SCROLL, 3: Mode.SHORTCUTS, 4: Mode.MEDIA, 5: Mode.WINDOWS}


@dataclass(frozen=True)
class ModalStatus:
    """Snapshot for the HUD / debug overlay."""

    mode: Mode
    paused: bool
    hand_visible: bool
    pending: str | None   # "choose", "disarm" or the name of the mode being started
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
        select_window_s: float = MODE_SELECT_WINDOW_S,
        select_hold_s: float = MODE_SELECT_HOLD_S,
        start_needs_fist: bool = MODE_START_NEEDS_FIST,
        disarm_hold_s: float = DISARM_HOLD_S,
        auto_disarm_s: float = AUTO_DISARM_S,
        hand_lost_release_s: float = HAND_LOST_RELEASE_S,
    ) -> None:
        self._handlers = handlers
        self._actuator = actuator
        self._enabled = {Mode(name) for name in enabled} & set(handlers)
        if not self._enabled:
            raise ValueError("MODES_ENABLED must contain at least one mode")
        self._on_event = on_event or (lambda event, mode: None)
        self._arm_hold_s = arm_hold_s
        self._arm_stillness = arm_stillness
        self._select_window_s = select_window_s
        self._select_hold_s = select_hold_s
        self._start_needs_fist = start_needs_fist
        self._disarm_hold_s = disarm_hold_s
        self._auto_disarm_s = auto_disarm_s
        self._hand_lost_release_s = hand_lost_release_s

        self._stabilizer = PoseStabilizer()
        self.mode = Mode.DISARMED
        self.paused = False
        self._hand_visible = False
        # Pending hold (OFF → mode, or fist → OFF)
        self._hold_target: Mode | str | None = None
        self._hold_since = 0.0
        self._hold_needed = 0.0
        self._hold_origin: tuple[float, float] | None = None
        self._hold_progress = 0.0
        # OFF: a fist "primes" mode selection for MODE_SELECT_WINDOW_S after it opens
        self._fist_closed = False
        self._primed_until: float | None = None
        self._fist_since = 0.0
        self._lost_since: float | None = None
        self._released_on_loss = False

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def status(self) -> ModalStatus:
        if isinstance(self._hold_target, Mode):
            pending: str | None = self._hold_target.value
        else:
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
        logger.info("Off")
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
            self._process_off(hand, pose, now)
            return

        if pose == Pose.FIST and not hand.any_pinch:
            if not self.paused:
                self.paused = True
                self._fist_since = now
                self.handler.pause(now)
                self._on_event("pause", self.mode)
            self._hold_target = "disarm"
            self._hold_progress = min(1.0, (now - self._fist_since) / self._disarm_hold_s)
            if now - self._fist_since >= self._disarm_hold_s:
                self.disarm()
                # The fist is still closed: opening it into 1–4 fingers picks the next mode.
                self._fist_closed = True
            return

        if self.paused:
            self.paused = False
            self._clear_hold()
            self.handler.resume(hand, now)
            self._on_event("resume", self.mode)

        # Locked: whatever the hand shape, it belongs to the current mode.
        self.handler.process(hand, pose, now)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _clear_hold(self) -> None:
        self._hold_target = None
        self._hold_origin = None
        self._hold_progress = 0.0

    def _process_off(self, hand: HandPose, pose: Pose, now: float) -> None:
        if pose == Pose.FIST:
            self._fist_closed = True
            self._primed_until = None
            self._clear_hold()
            return
        if self._fist_closed:  # the fist just opened
            self._fist_closed = False
            self._primed_until = now + self._select_window_s

        primed = self._primed_until is not None and now <= self._primed_until
        target = MODE_FOR_FINGERS.get(POSE_FINGER_COUNT.get(pose, 0))
        if target not in self._enabled or hand.any_pinch:
            target = None
        already_holding = target is not None and self._hold_target == target
        if (
            self._start_needs_fist
            and target is not None
            and target is not Mode.MOVE
            and not primed
            and not already_holding
        ):
            target = None  # 2–5 fingers only count right after a fist

        if target is None:
            self._clear_hold()
            if primed:
                self._hold_target = "choose"
            return

        moved = (
            self._hold_origin is not None
            and math.dist(hand.wrist, self._hold_origin) / hand.scale > self._arm_stillness
        )
        if self._hold_target != target or moved:
            self._hold_target = target
            self._hold_since = now
            self._hold_needed = self._select_hold_s if primed else self._arm_hold_s
            self._hold_origin = hand.wrist
            self._hold_progress = 0.0
            return

        self._hold_progress = min(1.0, (now - self._hold_since) / self._hold_needed)
        if now - self._hold_since >= self._hold_needed:
            self._clear_hold()
            self._primed_until = None
            self.mode = target
            self.paused = False
            self.handler.enter(hand, now)
            logger.info("Mode → %s", self.mode.name)
            self._on_event("arm", self.mode)

    def _no_hand(self, now: float) -> None:
        self._hand_visible = False
        self._clear_hold()
        self._fist_closed = False
        self._primed_until = None
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
