# core/gestures/modes/move.py
"""MOVE mode (☝️): cursor, left / double / right click, drag."""

from __future__ import annotations

import logging

from config import DOUBLE_CLICK_WINDOW_S, DRAG_HOLD_SECONDS, PINCH_DEBOUNCE_S
from core.gestures.modes.base import ModeHandler
from core.gestures.poses import HandPose, Pose
from core.pointer import Pointer

logger = logging.getLogger(__name__)


class MoveMode(ModeHandler):
    """
    - Hand movement moves the cursor (Pointer: relative or absolute).
    - Thumb taps index → left click; the cursor freezes (and rolls back) for the
      duration of the pinch so the click lands where you aimed.
    - Two taps within DOUBLE_CLICK_WINDOW_S → double click (second click at the
      first one's position so Windows pairs them).
    - Pinch held DRAG_HOLD_SECONDS → drag until released.
    - Thumb taps middle → right click (once per pinch).
    - Fist (pause) → clutch: reopen the hand anywhere, the cursor does not jump.
    """

    name = "move"

    def __init__(
        self,
        actuator,
        pointer: Pointer,
        drag_hold_s: float = DRAG_HOLD_SECONDS,
        double_click_window_s: float = DOUBLE_CLICK_WINDOW_S,
        debounce_s: float = PINCH_DEBOUNCE_S,
    ) -> None:
        self._actuator = actuator
        self._pointer = pointer
        self._drag_hold_s = drag_hold_s
        self._double_click_window_s = double_click_window_s
        self._debounce_s = debounce_s
        self._last_click_time: float | None = None
        self._last_click_pos: tuple[float, float] | None = None
        self._reset_gesture()

    def _reset_gesture(self) -> None:
        self._pinch_since: float | None = None
        self._dragging = False
        self._right_active = False

    # ── Life cycle ────────────────────────────────────────────────────────────

    def enter(self, hand: HandPose, now: float) -> None:
        self._reset_gesture()
        self._pointer.unfreeze()
        self._pointer.reset(sync=True)

    def exit(self) -> None:
        if self._dragging:
            self._actuator.drag_end()
        self._reset_gesture()
        self._pointer.unfreeze()

    def resume(self, hand: HandPose, now: float) -> None:
        self._reset_gesture()
        self._pointer.unfreeze()
        self._pointer.reset(sync=False)  # clutch: re-anchor, no jump

    def hand_lost(self) -> None:
        self.exit()
        self._pointer.reset(sync=False)

    @property
    def busy(self) -> bool:
        return self._pinch_since is not None or self._dragging

    # ── Per frame ─────────────────────────────────────────────────────────────

    def process(self, hand: HandPose, pose: Pose, now: float) -> None:
        if hand.pinch_index:
            if self._pinch_since is None:
                self._pinch_since = now
                self._pointer.freeze(now)
            elif not self._dragging and now - self._pinch_since >= self._drag_hold_s:
                self._dragging = True
                self._pointer.unfreeze()
                self._actuator.drag_start()
        elif self._pinch_since is not None:
            if self._dragging:
                self._actuator.drag_end()
                self._dragging = False
            else:
                self._click(now)
            self._pinch_since = None
            self._pointer.unfreeze()

        if hand.pinch_middle and not self._right_active and self._pinch_since is None:
            self._right_active = True
            self._pointer.freeze(now)
            self._actuator.right_click()
            self._pointer.unfreeze()
        elif not hand.pinch_middle:
            self._right_active = False

        self._pointer.update(hand, now)

    def _click(self, now: float) -> None:
        since = None if self._last_click_time is None else now - self._last_click_time
        if since is not None and since < self._debounce_s:
            logger.debug("Pinch jitter ignored")
            return
        if since is not None and since <= self._double_click_window_s and self._last_click_pos is not None:
            self._pointer.warp(self._last_click_pos, now)
            self._actuator.left_click()
            self._last_click_time = None
            self._last_click_pos = None
            logger.debug("Double click")
            return
        self._actuator.left_click()
        self._last_click_time = now
        self._last_click_pos = self._pointer.position
        logger.debug("Left click")
