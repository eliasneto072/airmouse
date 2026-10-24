<div align="center">

# AI Air Mouse

### Control your PC with nothing but your hands.

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://microsoft.com/windows)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.35-00897B?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/edge/mediapipe)
[![License](https://img.shields.io/badge/License-MIT-F7CA18?style=for-the-badge)](LICENSE)

**No mouse. No touchpad. No hardware. Just a webcam.**

[Getting Started](#-quick-start) · [Gesture Guide](#-gesture-guide) · [Calibration](#-calibration) · [Architecture](#-architecture) · [Troubleshooting](#-troubleshooting)

</div>

---

## What is this?

AI Air Mouse uses your webcam and [MediaPipe's hand landmark model](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) to track your hands in real time and translate gestures into mouse and keyboard actions — entirely on your device, with zero cloud calls.

The interaction model is inspired by **Apple Vision Pro**: your thumb is always the trigger, your index finger is always the pointer, and there are no ambiguous multi-finger combinations. The right hand owns the mouse; the left hand optionally controls Windows system shortcuts. Together they support clicks, drag, scroll, zoom, window snapping, and more.

```
Webcam → MediaPipe (21 landmarks per hand) → Gesture State Machines → SendInput / pynput → Windows
```

Everything runs in a tight async loop. Frame capture never blocks inference. Cursor smoothing uses the [1-euro filter](https://cristal.univ-lille.fr/~casiez/1euro/) — zero perceptible lag at high speed, zero jitter at rest.

---

## Requirements

| | Minimum | Recommended |
|---|---|---|
| **Python** | 3.12 | 3.13 |
| **Windows** | 10 | 11 |
| **Webcam** | Any DirectShow camera | 60 FPS capable |
| **RAM** | 2 GB | 4 GB+ |
| **Privileges** | Standard user | Administrator (for priority tuning) |

---

## Quick Start

```powershell
git clone https://github.com/Rcidshacker/airmouse.git
cd airmouse

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Download the MediaPipe hand model (~7.5 MB, git-ignored)
mkdir models
curl.exe -L -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task

# Verify all subsystems are healthy
.\.venv\Scripts\python test_startup.py

# Launch
.\.venv\Scripts\python main.py

# Optional: Desktop + Start-menu shortcuts that start AirMouse without a terminal
.\.venv\Scripts\python tools\create_shortcuts.py
```

While running, AirMouse shows an icon next to the clock (its colour follows the current mode). Click it to open the **settings page**; right-click it to pause gestures, turn the look check on/off, **start AirMouse with Windows**, open the log, and quit.

### Settings page and first-run guide

The first time AirMouse starts it opens a short guide in your browser: pick the camera (a snapshot of each one), choose classic or modal mode, then **practise with your own hand** — each step turns green as AirMouse recognises it (show your hand, turn on, click, pause, turn off). Later, click the tray icon for the same page with every user-facing setting: camera, mode, mouse hand, cursor speed, pinch sensitivity, gesture timings, look check, on-screen label and sounds, start with Windows. **Save and apply** restarts AirMouse in a few seconds; the page reconnects by itself.

- The page is served by AirMouse on `127.0.0.1` only and every request needs a token that is part of the address the tray opens, so other web pages and other computers can't reach the camera preview or your settings.
- Saved values go to `%APPDATA%\AirMouse\settings.json` and win over `config.py` and `config_local.py`. Any other setting can still be changed in `config_local.py` (tray → *Advanced*).
- If the camera can't be opened, AirMouse keeps the tray icon and opens the page on the camera picker instead of quitting.
- `SETTINGS_UI_ENABLED = False` turns the page off; `SETTINGS_PORT` picks the port (the next free one is used if it's taken).

> Press **Ctrl+C** to exit. All Windows settings (timer resolution, pointer acceleration, process priority) are automatically restored on shutdown.

On startup you'll see logs like:

```
[INFO] core.tracker:    MediaPipe HandLandmarker initialized (max_hands=2)
[INFO] core.gestures.orchestrator: GestureOrchestrator ready (left hand: on, two-hand gestures: on)
[INFO] airmouse.main:   Running. Press Ctrl+C to exit.
[INFO] airmouse.main:   FPS: 31.4
```

---

## Gesture Guide

### Right Hand — Mouse Control

The right hand is always active. Index fingertip drives the cursor.

| Gesture | How to do it | Action |
|---------|-------------|--------|
| **Point** | Index finger extended, others relaxed | Move cursor |
| **Pinch** | Touch thumb tip to index tip, release | Left click |
| **Double pinch** | Two pinches within 0.4 s | Double click |
| **Pinch + hold** | Touch thumb to index, hold 0.4 s | Start drag — release to drop |
| **Thumb + middle** | Touch thumb tip to middle tip | Right click |
| **Peace sign** | Index + middle up, thumb + ring + pinky curled | Enter scroll mode |
| **Wrist flick** | *(while in scroll mode)* flick wrist up/down | Scroll — faster flick = more ticks |
| **Fist** | Close all fingers | Freeze cursor — open hand to resume |

> **Tip:** The fist gesture is your rest state. Drop your hand, make a fist, and nothing will move or click until you extend your fingers again.

---

### Left Hand — System Shortcuts *(optional)*

The left hand adds a system shortcut layer on top of right-hand mouse control. You can ignore it entirely — right-hand behavior is unaffected.

| Gesture | Action |
|---------|--------|
| Open palm (all 5 fingers extended) | `Win+D` — Show Desktop |
| V-sign (index + middle up, others curled) | `Alt+Tab` — Cycle Windows |
| Four fingers (index–pinky up, thumb curled) | `Win+Tab` — Task View |
| Thumb + index pinch | `Win` — Start Menu |
| Fist (held) | Hold `Ctrl` — combine with right-hand click for multi-select |
| Fist (released) | Release `Ctrl` |
| Index pointing + wrist swipe right | `Alt+Left` — Go Back |

> **Ctrl + Click workflow:** Make a left-hand fist to hold Ctrl, then left-click with your right hand to multi-select items. Release the fist to drop Ctrl.

---

### Two-Hand Gestures — Power Actions

Activated only when both hands are visible.

| Gesture | Action |
|---------|--------|
| Both hands pinch + spread wrists apart | `Ctrl+=` — Zoom In |
| Both hands pinch + bring wrists together | `Ctrl+−` — Zoom Out |
| Left open palm + right fist swipe **right** | `Win+Right` — Snap window right |
| Left open palm + right fist swipe **left** | `Win+Left` — Snap window left |
| Both fists held for **1 second** | `Win+L` — Lock Screen |

---

## Modal Mode *(opt-in)*

In the classic mode every hand movement is a command, so scratching your face or reaching for a mug moves the cursor and clicks. Modal mode starts **OFF** and ignores your hands until you pick a mode. Once a mode is on it is **locked**: any hand shape belongs to that mode (an open palm in MOVE keeps moving the cursor), so nothing switches by accident.

```python
# config_local.py (git-ignored) — or edit config.py
INTERACTION_MODE = "modal"
```

### Picking a mode, pausing, turning off

| Gesture (right hand) | Effect |
|----------------------|--------|
| *(OFF)* Hold **1 / 2 / 3 / 4** fingers **still** for 0.6 s | MOVE / SCROLL / SHORTCUTS / MEDIA |
| *(OFF)* Make a fist, then show **1–5** fingers still for 0.4 s | the same, or **5 → WINDOWS** |
| Fist | Pause the current mode — open the hand to continue |
| Fist held 1.2 s, or hand out of view for 2 s | Turn off |

To change mode in one motion: hold a fist until the beep (OFF), then open straight into the new number. Fingers are counted from index to pinky; **4** is four fingers with the thumb folded into the palm, **5** is the open hand with the thumb out. Because an open hand is also how a resting hand looks, WINDOWS only starts right after a fist; `MODE_START_NEEDS_FIST` lists the modes with that rule (add others if they start by accident, or set `()` to start everything directly).

### Modes

| Mode | Gestures |
|------|----------|
| **1 · MOVE** | Move the hand → cursor (trackpad-style: small slow moves are precise, quick moves travel far) · thumb taps index → click · two taps → double click · pinch and hold 0.4 s → drag · thumb taps middle → right click · fist → lift the "mouse" and reposition your hand |
| **2 · SCROLL** | Quick move of the hand up / down → scrolls up / down a bit (bigger move = more) · left / right → sideways · bring the hand back slowly and flick again · pinch + move up / down → zoom. `SCROLL_STYLE = "joystick"` scrolls continuously while the hand is above / below where the mode started |
| **3 · SHORTCUTS** | Quick flick right / left → next / previous tab · up → `Alt+Tab` · down → show desktop · thumb taps index → `Enter` · thumb taps middle → `Esc` |
| **4 · MEDIA** | Quick move up / down → volume up / down · thumb taps index → play / pause · thumb taps middle → mute · flick left / right → previous / next track |
| **5 · WINDOWS** | Flick right / left → snap the window right / left · up → maximize · down → minimize · thumb taps index → Task View · thumb taps middle → voice typing (`Win+H`) |

Any hand shape works inside a mode. Shortcuts, media and window gestures are remappable in `SHORTCUT_BINDINGS` / `MEDIA_BINDINGS` / `WINDOW_BINDINGS` (action names in `core/actions.py`). `MODES_ENABLED` turns modes off.

A small label in the corner of the screen shows the current mode, whether your hand is visible and the progress of a hold; short beeps confirm turning on, off and switching (`HUD_ENABLED`, `HUD_POSITION`, `SOUNDS_ENABLED`).

Gestures are measured relative to your hand's size and work with a tilted hand, so they behave the same close to the camera or reclined further back.

### Only while you look at the screen

Modal mode uses MediaPipe face tracking to see where your head is pointing. Looking at your phone, out of the window or at another monitor, gestures don't count:

- a mode only starts while you face the screen — or if you keep holding the start gesture for 2 s, which also re-learns where your screen is (after a big posture change, or with the camera off to the side);
- an active mode pauses while you look away for ~1 s and resumes when you look back (the label shows "not looking");
- the left hand is ignored while you look away;
- no face found counts as not looking (looking down at a phone often hides the face from the camera). Far from the camera — e.g. lying in bed — turn the check off with 👌 (below); `ATTENTION_NO_FACE_ALLOWS = True` lets gestures through whenever no face is found;
- **turn the check off / on with a gesture:** while OFF — or while the label says "not looking" — hold 👌 (right hand) still for 1.5 s. A two-tone beep and the label confirm it, and the label keeps showing `look off` as a reminder. This lasts until you toggle again or restart. The fist still pauses / turns off while "not looking";
- the terminal logs every change ("Look check: NOT looking (head 41° from the screen direction …)") and the debug window (`DEBUG_GESTURES = True`) shows the current angle — handy to tune `ATTENTION_MAX_ANGLE`.

The "screen direction" starts as "facing the camera" and slowly follows your posture while you use a mode. Head tilt (resting your head sideways) is ignored. The face model (~3.7 MB) is downloaded to `models/` on first run; if that fails, download it manually:

```powershell
curl.exe --ssl-no-revoke -L -o models\face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
```

`ATTENTION_GATE = "start"` only gates starting a mode; `"off"` disables face tracking. `ATTENTION_MAX_ANGLE` (degrees) sets how far you may turn your head.

### Left hand

While the right hand has a mode on, the left hand fires system shortcuts. Window switching (✌️ and ☝️ + flick up) also works while OFF, without the right hand (`LEFT_WHEN_OFF`); everything else is ignored while OFF. Hold a pose for a moment; each pose fires once — change pose to fire again.

| Left hand | Action |
|-----------|--------|
| ✌️ held | `Alt+Tab` that stays open — flick right or thumb taps index → next window, flick left or thumb taps middle → previous; drop the ✌️ to pick the window |
| ☝️ + flick up | Quick `Alt+Tab`: back to the previous window |
| ☝️ + flick down | `Esc` |
| 3 fingers | Task View (`Win+Tab`) |
| ✊ then 🖐️ (open hand) | Show desktop (`Win+D`) — needs the fist first, since an open hand is also a resting hand |
| 👌 | Start menu |
| ✊ | Hold `Ctrl` while the right hand is in view (Ctrl+click, Ctrl+scroll = zoom) — only when you close the hand in view, so a resting fist never holds Ctrl |
| ☝️ + flick left / right | Back / forward (`Alt+←` / `Alt+→`) |
| 4 fingers (thumb folded) | Free slot |

Remap in `LEFT_HAND_BINDINGS`; `LEFT_HAND_ENABLED = False` turns the left hand off (and tracks a single hand). Left-handed? `DOMINANT_HAND = "left"` swaps the roles. The label in the corner shows `CTRL` / `ALT+TAB` or the last left-hand action.

---

## Calibration

All parameters live in `config.py` — never scattered across modules. Personal values (camera index, mode, thresholds) can go in a git-ignored `config_local.py` next to it, which overrides `config.py` and survives `git pull`.

<details>
<summary><b>Modal mode feel</b></summary>

| Symptom | Parameter | Fix |
|---------|-----------|-----|
| Cursor too slow / too fast | `POINTER_SPEED` | Increase / decrease (screen px per hand length) |
| Quick moves don't travel far enough | `POINTER_ACCEL`, `POINTER_MAX_GAIN` | Increase |
| Cursor creeps when the hand is still | `POINTER_MIN_SPEED` | Increase → try `0.1` |
| Prefer "hand position = screen position" | `CURSOR_MAPPING` | `"absolute"` |
| Turns on too easily / too slowly | `ARM_HOLD_S`, `MODE_SELECT_HOLD_S`, `ARM_STILLNESS` | Increase / decrease |
| A resting hand starts a mode | `MODE_START_NEEDS_FIST` | Add that mode, e.g. `("media", "windows")` |
| Turns off while repositioning with a fist | `DISARM_HOLD_S` | Increase → try `1.6` |
| 4 and 5 fingers mixed up | `THUMB_OUT_RATIO` | Lower if 5 reads as 4, raise if 4 reads as 5 |
| Clicks not registering | `PINCH_INDEX_ENTER_RATIO` | Increase → try `0.35` |
| Accidental clicks | `PINCH_INDEX_ENTER_RATIO` | Decrease → try `0.25` |
| Closing the hand still clicks | `CLICK_CONFIRM_S` | Increase → try `0.18` |
| Each flick scrolls too much / too little | `SCROLL_TICKS_PER_HAND_LENGTH` | Decrease / increase |
| Flicks not detected / slow moves scroll | `STROKE_START_VELOCITY` | Decrease / increase |
| Swipes not detected | `SWIPE_VELOCITY` | Decrease → try `2.5` |
| "MediaPipe processing error" in the log | `MP_VIDEO_MODE` | `False` |
| Pauses while you are looking at the screen | `ATTENTION_MAX_ANGLE` | Increase → try `40` — or hold a start gesture 2 s to re-learn the screen direction |
| Still reacts when looking at the phone | `ATTENTION_MAX_ANGLE` | Decrease → try `28` |
| Lower FPS with the look check on | `ATTENTION_EVERY_N_FRAMES`, `FACE_TRACKING_WIDTH` | Increase / decrease |
| Camera can't see your face / you sit far away | 👌 held 1.5 s while OFF, or `ATTENTION_GATE` | `"off"` |

</details>

<details>
<summary><b>Cursor feel</b></summary>

| Symptom | Parameter | Fix |
|---------|-----------|-----|
| Cursor shakes at rest | `ONE_EURO_MINCUTOFF` | Decrease → try `0.3` |
| Cursor lags during fast motion | `ONE_EURO_BETA` | Increase → try `0.05` |
| Cursor drifts near edges | `TRACKPAD_MARGIN` | Increase |

</details>

<details>
<summary><b>Click sensitivity</b></summary>

| Symptom | Parameter | Fix |
|---------|-----------|-----|
| Left click not triggering | `THUMB_INDEX_CLICK_DIST` | Increase → try `0.055` |
| Accidental left clicks | `THUMB_INDEX_CLICK_DIST` | Decrease → try `0.04` |
| Right click not triggering | `THUMB_MIDDLE_CLICK_DIST` | Increase |
| Drag activates too quickly | `DRAG_HOLD_SECONDS` | Increase → try `0.5` |
| Two quick taps don't double-click | `DOUBLE_CLICK_WINDOW_S` | Increase — keep it below the Windows double-click time (500 ms by default) |
| One tap registers as two clicks | `PINCH_DEBOUNCE_S` | Increase → try `0.15` |

</details>

<details>
<summary><b>Scroll & zoom</b></summary>

| Symptom | Parameter | Fix |
|---------|-----------|-----|
| Scroll too sensitive | `WRIST_VELOCITY_THRESHOLD` | Increase → try `0.012` |
| Scroll not registering | `WRIST_VELOCITY_THRESHOLD` | Decrease → try `0.005` |
| Zoom fires too easily | `ZOOM_WRIST_DELTA` | Increase → try `0.07` |

</details>

<details>
<summary><b>Hand layers</b></summary>

| Want to… | Parameter | Value |
|----------|-----------|-------|
| Stop the left hand from firing shortcuts (Win+D, Alt+Tab, Ctrl…) | `LEFT_HAND_ENABLED` | `False` |
| Disable zoom / window snap / lock screen | `TWO_HAND_GESTURES_ENABLED` | `False` |
| Track only one hand (faster) | both of the above | `False` — `MP_MAX_HANDS` is then ignored |

</details>

<details>
<summary><b>Performance</b></summary>

| Symptom | Parameter | Fix |
|---------|-----------|-----|
| Low FPS | `CAMERA_WIDTH` / `CAMERA_HEIGHT` | Reduce to `640` / `480` |
| Camera buffer delay | `CAMERA_BUFFER_SIZE` | Keep at `1` |

> MediaPipe dual-hand inference is heavier than single-hand. ~30 FPS at 1280×720 is normal.

</details>

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                            main.py                              │
│  Windows OS tuning → inference loop → cleanup on exit           │
└───────────────┬─────────────────────────────────────────────────┘
                │
    ┌───────────┼───────────────────────────────┐
    │           │                               │
    ▼           ▼                               ▼
camera.py   tracker.py                     actuator.py
Async       MediaPipe                      SendInput (move)
DirectShow  HandLandmarker    ──────────►  pynput (click/key)
daemon      → HandsResult
thread      (left, right)
                │
                ▼
        gestures/orchestrator.py
        Routes HandsResult to sub-processors
                │
    ┌───────────┼───────────────┐
    │           │               │
    ▼           ▼               ▼
right_hand  left_hand       two_hand
Cursor      Win shortcuts   Zoom / Snap
Clicks      Alt+Tab         Lock screen
Scroll      Ctrl modifier
Fist lock
    │
    ▼
filter.py + display.py
1-euro smooth   DPI-aware
cursor          coord map
```

### Why these design choices?

**Thumb as exclusive trigger** — Index stays as pointer; thumb fires everything. No ambiguous combos like "is that a peace sign or a scroll trigger?"

**Wrist velocity for scroll** — Flicking your wrist is anatomically natural and speed-proportional. Faster flick → 1–5 scroll ticks, clamped and cooldown-gated.

**Fist = rest state** — Put your hand down and make a fist. Cursor freezes, no phantom clicks. Open your fingers to resume exactly where you left off.

**`SendInput` over `mouse_event`** — `mouse_event` is a deprecated Vista-era compatibility shim. `SendInput` with `MOUSEEVENTF_VIRTUALDESK` correctly spans all monitors in a virtual desktop.

**DirectShow over MSMF** — `CAP_DSHOW` delivers lower capture latency than the default Media Foundation backend on Windows.

**1-euro filter over Kalman** — Adaptive speed-dependent low-pass filter. Strict reduction in cursor lag vs. Kalman at equivalent jitter suppression (Casiez et al., CHI 2012).

**MediaPipe handedness flip** — MediaPipe labels hands from the camera's point of view. Camera-"Left" = user's right (webcam is a mirror). The tracker flips the label before populating `HandsResult.right`.

---

## Project Structure

```
airmouse/
├── main.py              Entry point — Windows setup + inference loop
├── config.py            Every tunable constant, one file
├── requirements.txt     Dependencies
├── requirements-dev.txt Test dependencies (pytest)
├── config_local.py      Your overrides (optional, git-ignored)
├── test_startup.py      Smoke tests — run before first use
├── pytest.ini           Test collection settings
├── tests/               Unit tests — no camera needed
├── models/              hand_landmarker.task (git-ignored, ~9 MB)
└── core/
    ├── camera.py        Async frame capture via daemon thread
    ├── filter.py        1-euro filter implementation
    ├── display.py       Multi-monitor virtual desktop + DPI mapping
    ├── tracker.py       MediaPipe wrapper → HandsResult dataclass
    ├── handedness.py    Left/right label stabilization
    ├── actuator.py      Mouse + keyboard injection
    ├── actions.py       Named shortcut actions for gesture bindings
    ├── pointer.py       Relative / absolute cursor, clutch, click rollback
    ├── hud.py           Modal-mode on-screen label
    ├── attention.py     Head direction → "looking at the screen?"
    ├── face_tracker.py  MediaPipe face landmarks for the attention gate
    ├── feedback.py      Modal-mode sound cues
    └── gestures/
        ├── orchestrator.py   Classic pipeline + build_orchestrator()
        ├── modal.py          Modal pipeline
        ├── mode_manager.py   OFF / arm / switch / pause state machine
        ├── support_hand.py   Modal left-hand shortcuts
        ├── modes/            move.py, scroll.py, shortcuts.py, media.py
        ├── poses.py          Scale- and rotation-invariant pose classifier
        ├── stabilizer.py     Pose debouncing
        ├── motion.py         Swipe detector, joystick rate accumulator
        ├── right_hand.py     5-state machine: IDLE/PENDING/DRAG/SCROLL/LOCKED
        ├── left_hand.py      System shortcuts + Ctrl modifier state
        ├── two_hand.py       Zoom / snap / lock-screen
        └── utils.py          dist3d, is_fist, is_peace_sign, is_open_palm, …
```

---

## Running the Tests

Gesture logic is covered by unit tests that use synthetic hand landmarks and a fake actuator, so they need no webcam and never move your mouse.

```powershell
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```

`test_startup.py` remains the hardware smoke test (camera, model, mouse) and is run directly as shown in Quick Start.

---

## Troubleshooting

<details>
<summary><b>MediaPipe: "Unable to open file at models/hand_landmarker.task"</b></summary>

- The model is not in the repository — download it as shown in [Quick Start](#quick-start)
- Run the app from the repository root (the model path is relative)
- If `curl` fails with `CRYPT_E_REVOCATION_OFFLINE`, add `--ssl-no-revoke` (the certificate revocation server is unreachable from your network) or download the URL in a browser into `models\`

</details>

<details>
<summary><b>Camera fails to open</b></summary>

- Open Device Manager and confirm the webcam appears under **Cameras** or **Imaging devices**
- Try setting `CAMERA_INDEX = 1` or `2` in `config.py` if you have multiple cameras
- Ensure privacy shutters are open on laptops with built-in shutters
- Check that no other app (Teams, Zoom, OBS) has exclusive camera access

</details>

<details>
<summary><b>Cursor maps to wrong screen positions</b></summary>

The app sets `PROCESS_PER_MONITOR_DPI_AWARE` at startup. If you use mixed DPI scaling across monitors:
- Set all displays to the same scale (100% or 125%) for initial testing
- Ensure your primary monitor is set correctly in Windows Display Settings

</details>

<details>
<summary><b>Gestures not recognized</b></summary>

- **Lighting**: Diffuse, even lighting works best. Avoid strong backlighting.
- **Distance**: Keep your hand 40–70 cm from the camera.
- **Background**: High-contrast backgrounds help MediaPipe. Avoid skin-tone walls.
- **Thresholds**: Tweak `THUMB_INDEX_CLICK_DIST` or `WRIST_VELOCITY_THRESHOLD` in `config.py`.

</details>

<details>
<summary><b>Low FPS / stuttering</b></summary>

- Dual-hand MediaPipe inference is ~2× heavier than single-hand — 30 FPS at 1280×720 is expected
- Reduce resolution to 640×480 in `config.py` for ~50% FPS improvement
- Close other webcam-consuming applications
- Run as Administrator for `HIGH_PRIORITY_CLASS` and MMCSS "Games" scheduling

</details>

<details>
<summary><b>Permission warnings in logs</b></summary>

`HIGH_PRIORITY_CLASS` and MMCSS thread registration require Administrator privileges. The application functions normally without elevation but may drop frames under CPU load. Run the terminal as Administrator for best performance.

</details>

---

## License

[MIT License](LICENSE) — do whatever you want, just keep the attribution.
