# AirMouse AI — Modal Interaction Mode, Precision Layer & Left Hand v2 — Design

**Date:** 2026-10-18
**Status:** Proposed (pending maintainer review)
**Goal:** Make AirMouse reliable enough for everyday use — including from a reclined posture — by (1) adding an opt-in *modal* interaction mode with an explicit armed/disarmed state, (2) adding a precision layer (scale-invariant gestures, hysteresis, pose debouncing, trackpad-style cursor), and (3) redesigning the left-hand shortcut layer so shortcuts are deliberate, configurable and never leave keys stuck. The current behaviour is preserved as `classic` mode.

---

## Problem Statement

Observed while using the current build (Windows 11, Logitech webcam, 70–80 FPS):

1. **"Midas touch" — everything the hand does becomes a command.** Scratching your face, reaching for a mug or resting the hand moves the cursor and fires clicks or shortcuts. There is no state in which the system is visible to the camera but inert.
2. **Gesture thresholds are absolute.** Pinch distances are fixed normalized values (`0.060`, `0.065`), so they change meaning with distance to the camera. Sitting back (hand farther away, smaller in frame) breaks clicks. Distances are also computed in normalized space, which is distorted by the 16:9 aspect ratio.
3. **Pose checks assume an upright hand.** `is_extended()` compares `y` coordinates, so a tilted hand (very common when reclined or resting the arm) is misclassified.
4. **No debouncing / hysteresis.** A single threshold and single-frame pose checks make states flicker near their boundaries ("cursor bugs out").
5. **Cursor feel.** Absolute mapping over a small zone requires large arm movements; the cursor follows the index *tip*, which moves during a pinch, so clicks land off-target; `ONE_EURO_BETA = 0.007` causes noticeable lag on fast motion.
6. **Bugs in the current gesture logic:**
   - **Double click can never fire.** In `right_hand.py`, a click requires `now - last_gesture ≥ GESTURE_COOLDOWN_SECONDS (0.4)` while a double click requires `now - last_click ≤ DOUBLE_CLICK_WINDOW_S (0.4)`. Both timestamps are equal after a click, so the window is effectively zero.
   - **Right click auto-repeats** every 0.4 s while thumb+middle stay together (level-triggered instead of edge-triggered).
   - **`MP_MAX_HANDS` is ignored** — `tracker.py` hardcodes `num_hands=2`.
   - **Left V-sign does a one-shot `Alt+Tab`**, while the original spec (2026-05-15) says "hold V = keep switcher open". Only the two most recent windows are reachable.
   - **Left fist can leave `Ctrl` held** whenever the left hand rests closed in frame (scroll turns into zoom, clicks into Ctrl+click).
   - **Tracker runs in `RunningMode.IMAGE`**: full palm detection every frame, no temporal tracking → more jitter, unstable handedness labels, wasted CPU.
7. **No feedback.** The user cannot see what the system thinks the hand is doing.

---

## Design Overview

```
config.INTERACTION_MODE = "classic"  → existing processors (bug-fixed), unchanged UX
config.INTERACTION_MODE = "modal"    → new pipeline below

HandTracker (VIDEO mode, handedness stabilized)
      │  HandsResult(dominant, support)
      ▼
PoseClassifier (scale- & rotation-invariant, per hand)  →  HandPose
      ▼
PoseStabilizer (pose must persist POSE_STABLE_MS)
      ▼
ModeManager  ── DISARMED / MOVE / SCROLL / SHORTCUTS / MEDIA
      │            │
      │            └─ active Mode handler (move.py, scroll.py, shortcuts.py, media.py)
      ▼
SupportHandProcessor (left hand v2, only while armed)
      ▼
Actions registry  →  MouseActuator (SendInput / pynput)
      ▼
HUD overlay + sound cues
```

"Dominant" is the right hand by default; `DOMINANT_HAND = "left"` swaps roles for left-handed users.

---

## 1. Global Rules (modal mode)

| Rule | Trigger | Effect |
|------|---------|--------|
| Start state | App launch | `DISARMED` — no cursor movement, no clicks, no shortcuts, from either hand |
| Arm | Dominant hand shows **ONE** (index only) held **still** for `ARM_HOLD_S` (0.6 s) | → `MOVE` |
| Switch mode | Dominant hand shows **N fingers** (1–4) held for `MODE_SWITCH_HOLD_S` (0.6 s) | → mode N (if enabled) |
| Pause | Dominant **FIST** | Current mode suspended while closed; reopening resumes the same mode (in relative cursor mode this is the "clutch" — lift the mouse) |
| Disarm | Dominant **FIST** held `DISARM_HOLD_S` (1.5 s) | → `DISARMED` |
| Auto-disarm | Dominant hand not detected for `AUTO_DISARM_S` (2.0 s) | → `DISARMED` |

Details:
- **Finger counting uses index → pinky only.** Thumb extension is unreliable in MediaPipe, so it never distinguishes poses. Consequently there is no "open palm vs four fingers" distinction.
- **"Still" when arming** = wrist displacement during the hold window < `ARM_STILLNESS` × hand scale. Face-scratching involves motion, so it does not arm.
- Mode-switch timers are **paused while any pinch is active**, so in-mode pinches never trigger a switch.
- The HUD shows hold progress (arming / switching / disarming) so the user can abort by changing pose.

### Safety invariants (enforced in code and unit-tested)
1. No mouse button or key (Alt, Ctrl, Shift, Win) remains pressed after: a mode exit, disarming, the hand being lost for > `HAND_LOST_RELEASE_S` (0.3 s), or application exit.
2. `DISARMED` emits no input events.
3. Every discrete action is **edge-triggered**: it fires once per gesture and requires the gesture to be released before firing again.

---

## 2. Dominant Hand Modes

### Mode 1 · MOVE — pose ONE (☝️)

| Gesture | Action | Notes |
|---------|--------|-------|
| Index pointing, hand moves | Move cursor | Anchor = index MCP (landmark 5), stable during pinches |
| Thumb taps index (pinch < release) | Left click | Release before `DRAG_HOLD_SECONDS` |
| Two taps within `DOUBLE_CLICK_WINDOW_S` | Double click | Fixed: window measured independently from the cooldown |
| Pinch held ≥ `DRAG_HOLD_SECONDS` (0.4 s) | Drag; release to drop | Cursor tracks during drag |
| Thumb taps middle | Right click | Edge-triggered, no auto-repeat |
| Fist | Clutch / pause | Relative mode: reposition the hand without moving the cursor |

**Click stability:** while a pinch is pending (before drag), the cursor is frozen and rolled back to its position `CLICK_ROLLBACK_MS` (80 ms) before the pinch was detected — the approach of the thumb no longer drags the cursor off target.

**Cursor mapping** (`CURSOR_MAPPING`):
- `"relative"` (default in modal mode): trackpad-like. Cursor delta = filtered anchor delta (pixel space) × `POINTER_SPEED` × acceleration curve `1 + POINTER_ACCEL × speed`, capped at `POINTER_MAX_GAIN`. Small, slow hand motions are precise; fast flicks cross the screen.
- `"absolute"`: current behaviour (anchor position inside `TRACKPAD_MARGIN` zone mapped to the virtual desktop).

### Mode 2 · SCROLL — pose TWO (✌️)

| Gesture | Action |
|---------|--------|
| Enter mode | Current anchor position becomes the **center**; cursor frozen |
| Hand above / below center | Continuous scroll up / down; speed ∝ distance beyond dead zone (`SCROLL_DEADZONE`) |
| Hand left / right of center | Horizontal scroll |
| Pinch held + vertical displacement | Zoom (Ctrl + wheel) |
| Fist → reopen | Re-centers |

Scroll output uses a fractional accumulator so slow speeds produce smooth, occasional ticks instead of bursts. Replaces wrist-flick scrolling, which is tiring and erratic from a reclined posture (still available in `classic`).

### Mode 3 · SHORTCUTS — pose THREE (index + middle + ring)

| Gesture | Default action | Binding key |
|---------|----------------|-------------|
| Swipe right | Next tab (`Ctrl+Tab`) | `swipe_right` |
| Swipe left | Previous tab (`Ctrl+Shift+Tab`) | `swipe_left` |
| Swipe up | Previous window (`Alt+Tab`) | `swipe_up` |
| Swipe down | Show desktop (`Win+D`) | `swipe_down` |
| Thumb taps index | `Enter` | `pinch_index` |
| Thumb taps middle | `Esc` | `pinch_middle` |

Intended for one-handed use (e.g. reclined with the other hand resting). All bindings live in `SHORTCUT_BINDINGS` and refer to names in the actions registry.

**Swipe detection:** anchor velocity (pixel space, normalized by hand scale) > `SWIPE_VELOCITY`; direction = dominant axis; fires once, re-arms when speed falls below `SWIPE_REARM_VELOCITY`. Directions are computed in *user space* (image x mirrored), so "right" is always the user's right.

### Mode 4 · MEDIA — pose FOUR (index → pinky), optional

| Gesture | Default action |
|---------|----------------|
| Hand above / below center | Volume up / down (rate ∝ displacement) |
| Thumb taps index | Play / pause |
| Thumb taps middle | Mute |
| Swipe left / right | Previous / next track |

Disable with `MODES_ENABLED = ("move", "scroll", "shortcuts")`.

---

## 3. Support Hand (Left Hand v2)

Keeps the spirit of the current left-hand layer — system shortcuts with the non-dominant hand while the dominant hand drives the mouse — but makes every gesture deliberate and safe.

**General behaviour**
- Active only while the system is **armed** (any mode) and `LEFT_HAND_ENABLED = True`. In `DISARMED` the left hand is ignored too.
- Never moves the cursor.
- A pose must be stable for `LEFT_HOLD_S` (0.35 s) before it fires (`LEFT_PALM_HOLD_S` = 0.8 s for the open hand, which occurs naturally at rest).
- Each action fires once; the hand must return to neutral (another pose, or out of frame) before the same action can fire again.
- The HUD shows the support-hand state (`CTRL`, `ALT+TAB`, or a 1 s toast with the last action).

| Pose (held) | Action | vs. current |
|-------------|--------|-------------|
| ✌️ **TWO (V)** | **Window switcher:** presses `Alt+Tab` and *keeps Alt held* while the V is held. Thumb taps index → `Tab` (next window), thumb taps middle → `Shift+Tab` (previous). Dropping the V releases Alt → the highlighted window is selected. The dominant hand can also click a window in the switcher. | Current: one-shot `Alt+Tab` (only the last two windows). Implements the original "hold V = keep switcher open" intent. |
| **THREE** | Task View (`Win+Tab`) | Current: four fingers |
| 🖐️ **FOUR / open hand** held 0.8 s | Show desktop (`Win+D`) | Current: open palm, instant |
| 👌 **OK** (thumb–index pinch, middle/ring/pinky extended) | Start menu (`Win`) | Current: any thumb–index pinch |
| ✊ **FIST** | Hold `Ctrl` — **only while the dominant hand is visible**; released immediately otherwise | Current: Ctrl held whenever the left fist is visible |
| ☝️ **ONE + swipe** toward user's left / right | Back / Forward (`Alt+Left` / `Alt+Right`) | Current: back only |
| ☝️ **ONE + swipe** up / down | *Unbound by default* (user slots, e.g. copy / paste) | New |

**Window-switcher safety:** Alt is released on any of: V released, hand lost > 0.3 s, disarm, mode change of the support hand, or `ALT_SWITCHER_MAX_S` (10 s).

All bindings are configurable through `LEFT_HAND_BINDINGS` (pose/gesture → action name).

### Two-hand gestures in modal mode
`TWO_HAND_GESTURES_ENABLED = False` by default in modal mode: zoom moved to SCROLL mode, and the "both fists → lock screen" gesture conflicts with the dominant-hand disarm (fist) and the support-hand Ctrl (fist). `lock_screen`, `snap_left` and `snap_right` remain available as bindable actions. Classic mode keeps the current two-hand gestures.

---

## 4. Precision Layer (shared)

### Tracker
- Switch to `RunningMode.VIDEO` with `detect_for_video(image, timestamp_ms)` — temporal tracking reduces jitter and CPU; palm detection only runs when tracking is lost.
- `num_hands = 2 if LEFT_HAND_ENABLED else 1` (respecting `MP_MAX_HANDS`).
- **Handedness stabilization:** a hand's label must persist for `HANDEDNESS_STABLE_FRAMES` (5) before it changes; if both hands receive the same label, they are disambiguated by x-position.
- `HandsResult` gains `dominant` / `support` accessors driven by `DOMINANT_HAND`.

### PoseClassifier (`core/gestures/poses.py`)
- All geometry in **pixel space** (`x × CAMERA_WIDTH`, `y × CAMERA_HEIGHT`) to remove aspect-ratio distortion; z is ignored.
- **Hand scale** `s` = distance wrist (0) → middle MCP (9). Every distance threshold is a ratio of `s`, so gestures work at any distance from the camera.
- **Rotation-invariant finger extension:** a finger is extended when `dist(wrist, tip) > dist(wrist, pip) × FINGER_EXTEND_RATIO`. Works with tilted hands.
- **Pinch hysteresis:** pinch starts below `PINCH_ENTER_RATIO` and ends above `PINCH_EXIT_RATIO` (separate thresholds for thumb–index and thumb–middle).
- Output: `HandPose(pose: Pose, finger_count, pinch_index, pinch_middle, scale, anchor, wrist)` where `Pose ∈ {NONE, FIST, ONE, TWO, THREE, FOUR, OK}`.

### PoseStabilizer
A pose is reported only after it has been observed continuously for `POSE_STABLE_MS` (80 ms). Pinch flags are not debounced (they already have hysteresis) to keep clicks responsive.

### Pointer (`core/pointer.py`)
Absolute / relative mapping, acceleration, click freeze + rollback, clutch handling, re-tuned 1€ filter. Extracted from `right_hand.py` / `display.py` so both modes can share it.

---

## 5. Feedback

**HUD (`core/hud.py`)** — small always-on-top, click-through, no-taskbar overlay (tkinter + Win32 extended styles `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW`). Runs its own Tk thread fed through a queue.
- Pill with mode name and color: `DISARMED` (grey), `MOVE` (blue), `SCROLL` (green), `SHORTCUTS` (amber), `MEDIA` (purple).
- Progress bar while arming / switching / disarming.
- Hand-detected dot; support-hand badge (`CTRL`, `ALT+TAB`) and last-action toast.
- `HUD_ENABLED`, `HUD_POSITION` (`"bottom-right"` default).

**Sounds (`core/feedback.py`)** — short asynchronous `winsound` cues on arm, disarm and mode change. `SOUNDS_ENABLED`.

No new third-party dependencies (tkinter and winsound are stdlib).

---

## 6. Actions Registry (`core/actions.py`)

Named actions used by SHORTCUTS, MEDIA and the support hand, so bindings are plain config data:

`next_tab`, `prev_tab`, `alt_tab`, `window_switcher` (stateful), `task_view`, `show_desktop`, `start_menu`, `back`, `forward`, `enter`, `escape`, `copy`, `paste`, `cut`, `undo`, `redo`, `save`, `new_tab`, `close_tab`, `command_palette`, `play_pause`, `next_track`, `prev_track`, `volume_up`, `volume_down`, `mute`, `zoom_in`, `zoom_out`, `lock_screen`, `snap_left`, `snap_right`.

`MouseActuator` gains generic `press_combo(*keys)`, `key_down(key)`, `key_up(key)`, `hscroll(ticks)` and `release_all()`; existing named methods stay for compatibility.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `config.py` | New "Interaction mode", "Precision", "Modal", "Support hand", "HUD" sections |
| Modify | `core/tracker.py` | VIDEO mode, `num_hands` from config, handedness stabilization, dominant/support |
| Modify | `core/actuator.py` | Generic key helpers, horizontal scroll, `release_all()` |
| Modify | `core/gestures/right_hand.py` | Classic: fix double click and right-click repeat |
| Modify | `core/gestures/orchestrator.py` | Select classic vs modal pipeline; honour hand flags |
| Create | `core/gestures/poses.py` | `PoseClassifier`, `HandPose`, `Pose` |
| Create | `core/gestures/stabilizer.py` | `PoseStabilizer`, hold timers |
| Create | `core/gestures/mode_manager.py` | Global state machine (arm / switch / pause / disarm) |
| Create | `core/gestures/modes/{move,scroll,shortcuts,media}.py` | One handler per mode (`enter` / `process` / `exit`) |
| Create | `core/gestures/support_hand.py` | Left hand v2 |
| Create | `core/pointer.py` | Cursor mapping, acceleration, click freeze |
| Create | `core/actions.py` | Actions registry |
| Create | `core/hud.py`, `core/feedback.py` | Overlay and sounds |
| Modify | `main.py` | Start/stop HUD; `release_all()` on exit |
| Create | `tests/` | Unit tests (see Testing) |
| Create | `requirements-dev.txt` | `pytest` |
| Create | `LICENSE` | MIT text (README already declares MIT) |
| Modify | `README.md` | "Modal mode" section, gesture tables, calibration |

---

## New Config Constants (initial values, tuned during testing)

```python
# ── Interaction mode ──────────────────────────────────────────────────────────
INTERACTION_MODE = "classic"          # "classic" (current UX) | "modal"
DOMINANT_HAND = "right"               # "right" | "left"
LEFT_HAND_ENABLED = True              # support hand shortcuts
TWO_HAND_GESTURES_ENABLED = True      # forced False in modal mode unless set explicitly
MODES_ENABLED = ("move", "scroll", "shortcuts", "media")

# ── Precision ─────────────────────────────────────────────────────────────────
FINGER_EXTEND_RATIO = 1.15            # tip/pip distance-from-wrist ratio
PINCH_INDEX_ENTER_RATIO = 0.30        # × hand scale
PINCH_INDEX_EXIT_RATIO = 0.45
PINCH_MIDDLE_ENTER_RATIO = 0.30
PINCH_MIDDLE_EXIT_RATIO = 0.45
POSE_STABLE_MS = 80
HANDEDNESS_STABLE_FRAMES = 5

# ── Cursor ────────────────────────────────────────────────────────────────────
CURSOR_MAPPING = "absolute"           # "absolute" | "relative" (modal default: relative)
CURSOR_ANCHOR_LANDMARK = 5            # index MCP
POINTER_SPEED = 2.2                   # screen px per camera px (relative mode)
POINTER_ACCEL = 0.004
POINTER_MAX_GAIN = 6.0
CLICK_ROLLBACK_MS = 80

# ── Modal ─────────────────────────────────────────────────────────────────────
ARM_HOLD_S = 0.6
ARM_STILLNESS = 0.15                  # × hand scale
MODE_SWITCH_HOLD_S = 0.6
DISARM_HOLD_S = 1.5
AUTO_DISARM_S = 2.0
HAND_LOST_RELEASE_S = 0.3
SCROLL_DEADZONE = 0.25                # × hand scale
SCROLL_SPEED = 12.0                   # ticks/s per hand-scale unit beyond dead zone
SCROLL_MAX_RATE = 25.0                # ticks/s
SWIPE_VELOCITY = 4.0                  # hand-scales per second
SWIPE_REARM_VELOCITY = 1.0
SHORTCUT_BINDINGS = {
    "swipe_right": "next_tab", "swipe_left": "prev_tab",
    "swipe_up": "alt_tab", "swipe_down": "show_desktop",
    "pinch_index": "enter", "pinch_middle": "escape",
}

# ── Support hand (left hand v2) ───────────────────────────────────────────────
LEFT_HOLD_S = 0.35
LEFT_PALM_HOLD_S = 0.8
ALT_SWITCHER_MAX_S = 10.0
LEFT_HAND_BINDINGS = {
    "two": "window_switcher", "three": "task_view", "four": "show_desktop",
    "ok": "start_menu", "fist": "hold_ctrl",
    "one_swipe_left": "back", "one_swipe_right": "forward",
    "one_swipe_up": None, "one_swipe_down": None,
}

# ── Feedback ──────────────────────────────────────────────────────────────────
HUD_ENABLED = True
HUD_POSITION = "bottom-right"
SOUNDS_ENABLED = True
```

---

## Testing

### Automated (new — `pytest`, no camera required)
- `tests/fixtures/hands.py`: synthetic 21-landmark generator for each pose at arbitrary scale, rotation and position.
- **Poses:** every pose classified correctly at 3 scales × 3 rotations; pinch hysteresis.
- **Stabilizer / timers:** injected clock (processors accept `now`), so timing tests are deterministic.
- **ModeManager:** arm (still vs moving), switch, pause, disarm, auto-disarm; switch suppressed during pinch.
- **Modes:** `FakeActuator` records calls — click / double click / drag / right click (edge-triggered), scroll accumulator, swipes, media.
- **Support hand:** window-switcher Alt lifecycle, Ctrl only with dominant hand visible, edge triggering.
- **Safety invariants:** after every transition / hand loss / exit, `FakeActuator` has nothing pressed.
- **Classic regressions:** double click fires; right click does not repeat.

Pure-logic tests do not import `ctypes.windll`, so they also run on Linux CI if the maintainer wants a GitHub Actions workflow.

### Manual checklist (app live)
- [ ] Starts DISARMED; waving / scratching face does nothing
- [ ] Hold ☝️ still 0.6 s → MOVE (HUD + sound); moving ☝️ does not arm
- [ ] Click, double click, drag, right click land on target
- [ ] Fist → clutch; reopen continues without jump (relative)
- [ ] Hold ✌️ → SCROLL; vertical / horizontal / zoom; re-center with fist
- [ ] Hold 3 fingers → SHORTCUTS; four swipes + Enter + Esc
- [ ] Hold 4 fingers → MEDIA; volume, play/pause, tracks
- [ ] Fist 1.5 s → DISARMED; hand out of frame 2 s → DISARMED
- [ ] Left ✌️ → switcher stays open; taps cycle; release selects; Alt never stuck
- [ ] Left fist + right click → Ctrl+click; left fist with right hand absent → no Ctrl
- [ ] Left 3 → Task View; left open hand 0.8 s → Win+D; left 👌 → Start
- [ ] Left ☝️ swipe → back / forward
- [ ] `DOMINANT_HAND = "left"` swaps roles
- [ ] Ctrl+C on exit leaves no key or button pressed
- [ ] `INTERACTION_MODE = "classic"` behaves as before (plus bug fixes)

---

## Delivery (separate PRs, stacked branches)

1. **fix** — double click, right-click repeat, `MP_MAX_HANDS` / `LEFT_HAND_ENABLED` / `TWO_HAND_GESTURES_ENABLED` honoured, `LICENSE`, test scaffolding.
2. **feat(precision)** — VIDEO tracking, handedness stabilization, `PoseClassifier`, `PoseStabilizer`, `pointer.py` (opt-in for classic via `CURSOR_MAPPING`).
3. **feat(modal)** — `ModeManager`, four modes, actions registry, HUD, sounds, README.
4. **feat(left-hand-v2)** — support hand processor, bindings, dominant-hand swap.

Each PR is independently reviewable and keeps `classic` as the default.

---

## Out of Scope (possible follow-ups)

- Face guard (ignore hands overlapping a detected face)
- Settings panel with live-reloading JSON settings
- Per-app binding profiles
- Packaged `.exe` and release workflow
- macOS / Linux input backends

## Open Questions for the Maintainer

1. Keep `classic` as the default, or switch to `modal` once it is stable?
2. OK to add `pytest` as a dev dependency and a `tests/` folder? Interested in a CI workflow?
3. OK to add the `LICENSE` file (MIT, © Rcidshacker) that the README already references?
