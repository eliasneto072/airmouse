# core/feedback.py
"""Short sound cues for modal state changes (Windows only; silent elsewhere)."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

try:
    import winsound
except ImportError:  # not Windows
    winsound = None


class Sounds:
    """play(event) beeps asynchronously so the camera loop never waits."""

    PATTERNS: dict[str, tuple[tuple[int, int], ...]] = {
        "arm": ((880, 70), (1320, 90)),       # rising
        "disarm": ((660, 70), (440, 110)),    # falling
        "switch": ((1100, 60),),
    }

    def __init__(self) -> None:
        self.available = winsound is not None

    def play(self, event: str) -> None:
        pattern = self.PATTERNS.get(event)
        if not pattern or not self.available:
            return
        threading.Thread(target=self._beep, args=(pattern,), daemon=True, name="sound").start()

    @staticmethod
    def _beep(pattern: tuple[tuple[int, int], ...]) -> None:
        for frequency, duration_ms in pattern:
            try:
                winsound.Beep(frequency, duration_ms)
            except RuntimeError:  # no audio device
                return
