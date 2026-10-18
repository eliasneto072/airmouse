# config.py
# All tunable parameters for the AI Air Mouse system.
# Adjust these to calibrate for different environments; never scatter constants across modules.

# ── Camera ─────────────────────────────────────────────────────────────────────
CAMERA_INDEX = 0                  # Webcam device index
CAMERA_WIDTH = 1280               # Capture resolution width
CAMERA_HEIGHT = 720               # Capture resolution height
CAMERA_FPS = 60                   # Target capture FPS; webcam must support this
CAMERA_BUFFER_SIZE = 1            # DirectShow buffer: 1 = always freshest frame

# ── MediaPipe ──────────────────────────────────────────────────────────────────
MP_MODEL_PATH = "models/hand_landmarker.task"  # float16 Tasks API bundle
MP_MAX_HANDS = 2                  # hands tracked; forced to 1 when both hand layers below are off
MP_DETECTION_CONFIDENCE = 0.7
MP_TRACKING_CONFIDENCE = 0.5
MP_VIDEO_MODE = True              # track landmarks across frames; set False to detect from scratch every frame

# ── Hand layers ────────────────────────────────────────────────────────────────
# The right hand always drives the mouse. Turning both layers off tracks a single
# hand, which is cheaper and stops a resting left hand from triggering shortcuts.
LEFT_HAND_ENABLED = True          # left-hand system shortcuts (classic, and modal LEFT_HAND_BINDINGS)
TWO_HAND_GESTURES_ENABLED = True  # zoom / window snap / lock screen (needs both hands)

# ── Virtual Trackpad ───────────────────────────────────────────────────────────
# Shrink the active tracking zone inward from webcam edges by this many pixels.
# Prevents the user needing to stretch their hand to screen corners.
TRACKPAD_MARGIN = 100             # pixels, applied to all four edges

# ── 1€ Filter ─────────────────────────────────────────────────────────────────
# Casiez et al. 2012 — adaptive low-pass filter for cursor smoothing.
# mincutoff: lower = more smoothing at rest (reduce jitter)
# beta: higher = less lag at high speed (reduce lag during fast motion)
# dcutoff: derivative smoothing; usually leave at 1.0
ONE_EURO_MINCUTOFF = 0.5           # lower = more smoothing at rest (less jitter)
ONE_EURO_BETA = 0.007
ONE_EURO_DCUTOFF = 1.0

# ── Gesture Thresholds ────────────────────────────────────────────────────────
# All distances are Euclidean norms of normalized MediaPipe coordinates [0.0–1.0].

# Thumb-pinch thresholds
THUMB_INDEX_CLICK_DIST  = 0.060   # thumb tip ↔ index tip → left click
THUMB_MIDDLE_CLICK_DIST = 0.065   # thumb tip ↔ middle tip → right click

# Legacy (kept for reference during migration — unused after Task 5)
CLICK_DISTANCE_THRESHOLD = 0.03
RIGHT_CLICK_DISTANCE_THRESHOLD = 0.06

DRAG_HOLD_SECONDS = 0.4           # thumb+index pinch held → drag activates
GESTURE_COOLDOWN_SECONDS = 0.4    # min gap between discrete gesture events

DOUBLE_CLICK_WINDOW_S = 0.4       # second pinch within this window = double click
                                  # keep below the Windows double-click time (500 ms default)
PINCH_DEBOUNCE_S = 0.1            # a release this soon after a click is pinch jitter, not a tap

# Fist detection — all finger tips must be below their PIP joints
FIST_CURL_THRESHOLD = 0.0         # unused numerically; fist = all 5 curled (boolean)

# Wrist scroll (peace-sign posture)
WRIST_VELOCITY_THRESHOLD = 0.008  # normalized units/s — minimum wrist flick to register
SCROLL_TICK_SCALE        = 0.003  # velocity / scale = tick count (clamped 1–5)
SCROLL_COOLDOWN_S        = 0.12   # minimum gap between scroll emissions

# Scroll: number of OS scroll ticks per gesture detection cycle (legacy fallback)
SCROLL_TICKS = 3

# Two-hand gestures
ZOOM_WRIST_DELTA    = 0.05        # normalized wrist-to-wrist distance change per zoom tick
LOCK_SCREEN_HOLD_S  = 1.0         # both fists held this long → Win+L

# ── Interaction mode ──────────────────────────────────────────────────────────
# "classic": the original always-on gesture set (README → Gesture Guide).
# "modal":   starts OFF and ignores the hands until you pick a mode by holding
#            1–5 fingers still: MOVE, SCROLL, SHORTCUTS, MEDIA, WINDOWS (5 only
#            right after a fist — see MODE_START_NEEDS_FIST). Once in a
#            mode it stays locked — any hand shape works — until you hold a fist
#            to turn it off. While a mode is on, the left hand fires system
#            shortcuts (LEFT_HAND_BINDINGS). README → Modal Mode.
INTERACTION_MODE = "classic"
MODES_ENABLED = ("move", "scroll", "shortcuts", "media", "windows")

# ── Modal: turning on, choosing a mode, turning off ───────────────────────────
ARM_HOLD_S = 0.6                  # OFF: hold 1–5 fingers still this long → that mode
ARM_STILLNESS = 0.25              # holds are restarted if the wrist moves more than this (hand lengths)
MODE_SELECT_WINDOW_S = 1.5        # OFF: right after a fist, 1–5 fingers start a mode faster:
MODE_SELECT_HOLD_S = 0.4          # …held still this long
# Modes that only start right after a fist. An open hand (5) is how a resting
# hand looks, so WINDOWS needs the fist by default. Add "media", "shortcuts",
# "scroll" for a stricter setup, or use () to start every mode directly.
MODE_START_NEEDS_FIST = ("windows",)
DISARM_HOLD_S = 1.2               # in a mode: hold a fist this long → OFF (a shorter fist = pause)
AUTO_DISARM_S = 2.0               # hand out of frame this long → disarm
HAND_LOST_RELEASE_S = 0.3         # hand out of frame this long → release drag/keys

# ── Modal: gesture strokes (SCROLL and MEDIA) ─────────────────────────────────
# A quick move of the hand is a "stroke": up/down (or left/right) by a hand
# length scrolls / changes the volume by a fixed amount. Slow movements — such as
# bringing the hand back afterwards — are ignored, so you can flick repeatedly.
STROKE_START_VELOCITY = 1.5       # hand lengths/s for a movement to count as a stroke
STROKE_END_VELOCITY = 0.6         # the stroke ends when the hand slows below this
STROKE_RETURN_IGNORE_S = 0.4      # an opposite stroke this soon after one is the hand coming back

# ── Modal: SCROLL mode (2 fingers to start) ───────────────────────────────────
SCROLL_STYLE = "stroke"           # "stroke": flick up/down to scroll | "joystick": hand above/below a center
SCROLL_TICKS_PER_HAND_LENGTH = 6.0  # stroke: wheel ticks per hand length of movement (min 1 per stroke)
HSCROLL_ENABLED = True            # left/right strokes scroll horizontally
ZOOM_STEPS_PER_HAND_LENGTH = 3.0  # pinch + up/down stroke: zoom in/out steps
SCROLL_DEADZONE = 0.25            # joystick: hand lengths around the center that do nothing
SCROLL_SPEED = 15.0               # joystick: wheel ticks/s per hand length beyond the dead zone
SCROLL_MAX_RATE = 30.0            # joystick: wheel ticks/s
ZOOM_SPEED = 3.0                  # joystick: pinch + up/down zoom steps/s per hand length
ZOOM_MAX_RATE = 6.0

# ── Modal: SHORTCUTS (3), MEDIA (4) and WINDOWS (5) modes ─────────────────────
# Values are action names from core/actions.py; None leaves a gesture unbound.
SWIPE_VELOCITY = 3.0              # hand lengths/s for a flick to count as a swipe
SWIPE_REARM_VELOCITY = 0.8        # the hand must slow below this before the next swipe
SHORTCUT_BINDINGS = {
    "swipe_right": "next_tab",
    "swipe_left": "prev_tab",
    "swipe_up": "alt_tab",
    "swipe_down": "show_desktop",
    "pinch_index": "enter",
    "pinch_middle": "escape",
}
MEDIA_BINDINGS = {                # up/down strokes always change the volume
    "swipe_right": "next_track",
    "swipe_left": "prev_track",
    "pinch_index": "play_pause",
    "pinch_middle": "mute",
}
VOLUME_STEPS_PER_HAND_LENGTH = 8.0  # MEDIA: volume steps (2 % each) per hand length of stroke
WINDOW_BINDINGS = {
    "swipe_right": "snap_right",
    "swipe_left": "snap_left",
    "swipe_up": "maximize",
    "swipe_down": "minimize",
    "pinch_index": "task_view",
    "pinch_middle": "voice_typing",
}

# ── Modal: left hand (support hand) ───────────────────────────────────────────
# Active while the right hand has a mode on (and LEFT_HAND_ENABLED); the
# gestures in LEFT_WHEN_OFF also work with the system OFF (no right hand needed).
# A pose must be held LEFT_HOLD_S and fires once; change pose to fire again.
# Values are action names from core/actions.py, None (unbound), or the special
# "window_switcher" (held Alt+Tab) and "hold_ctrl" (Ctrl held while the pose is).
LEFT_HOLD_S = 0.35
LEFT_PALM_HOLD_S = 0.9            # the open hand (5) is also a resting hand: needs a longer hold…
LEFT_NEEDS_FIST = ("five",)       # …and only fires right after a fist (✊ → 🖐️)
ALT_SWITCHER_MAX_S = 10.0         # the window switcher lets go of Alt after this long
LEFT_WHEN_OFF = ("two", "one_swipe_up")  # window switching works without the right hand
LEFT_HAND_BINDINGS = {
    "two": "window_switcher",     # ✌️: Alt+Tab stays open — flick right / thumb taps index → next,
                                  # flick left / thumb taps middle → previous; drop the ✌️ to pick
    "three": "task_view",
    "four": None,                 # four fingers, thumb folded: free slot
    "five": "show_desktop",       # open hand, right after a fist (LEFT_NEEDS_FIST)
    "ok": "start_menu",           # 👌
    "fist": "hold_ctrl",          # Ctrl held while the fist is closed and the right hand is in view;
                                  # only when you close the hand in view (a resting fist never holds Ctrl)
    "one_swipe_left": "back",     # ☝️ + flick to your left
    "one_swipe_right": "forward",
    "one_swipe_up": "alt_tab",    # ☝️ + flick up: jump back to the previous window
    "one_swipe_down": "escape",   # ☝️ + flick down: close menus / dialogs / full screen
}

# ── Modal: feedback ───────────────────────────────────────────────────────────
HUD_ENABLED = True                # small always-on-top label with the current mode
HUD_POSITION = "bottom-right"     # bottom-right | bottom-left | top-right | top-left
SOUNDS_ENABLED = True             # short beeps on arm / disarm / mode switch

# ── Pose classification (precision layer) ─────────────────────────────────────
# Geometry is measured in pixels and divided by the hand's own size (wrist →
# middle-finger knuckle, "hand length"), so thresholds hold at any distance from
# the camera and with a tilted hand.
FINGER_EXTEND_RATIO = 1.15        # extended: wrist→tip > wrist→PIP × this
FIST_TIP_RADIUS = 1.15            # fist: all fingertips within this many hand lengths of the wrist
THUMB_OUT_RATIO = 0.75            # 5 vs 4: thumb tip further than this from the pinky knuckle = thumb out
PINCH_INDEX_ENTER_RATIO = 0.30    # thumb tip ↔ index tip, in hand lengths — pinch starts below…
PINCH_INDEX_EXIT_RATIO = 0.45     # …and ends above this (hysteresis: no flicker at the edge)
PINCH_MIDDLE_ENTER_RATIO = 0.30   # thumb tip ↔ middle tip
PINCH_MIDDLE_EXIT_RATIO = 0.45
POSE_STABLE_S = 0.08              # a pose must persist this long before it counts
POSE_NONE_STABLE_S = 0.30         # "unrecognized" must persist longer (motion blur mid-gesture)
HANDEDNESS_STABLE_FRAMES = 5      # frames a single hand's left/right label must disagree to flip
DOMINANT_HAND = "right"           # "right" | "left" — the hand that drives the mouse

# ── Cursor (precision layer) ──────────────────────────────────────────────────
CURSOR_MAPPING = "relative"       # "relative" (trackpad-like) | "absolute" (hand position = screen position)
CURSOR_ANCHOR_LANDMARK = 5        # index knuckle: stays put while the thumb pinches the index tip
POINTER_SPEED = 450               # relative: screen px per hand length of slow movement
POINTER_ACCEL = 0.5               # relative: extra gain per hand length/s of speed
POINTER_MAX_GAIN = 3.0            # relative: cap on the acceleration multiplier
POINTER_MIN_SPEED = 0.06          # relative: slower movement (hand lengths/s) is treated as jitter
POINTER_FILTER_MINCUTOFF = 1.0    # 1€ filter on the anchor (pixel space)
POINTER_FILTER_BETA = 0.01
CLICK_ROLLBACK_S = 0.08           # on pinch, move the cursor back to where it was this long ago
CLICK_CONFIRM_S = 0.12            # a click waits this long and is cancelled if the hand closes into a fist

# ── Handedness ────────────────────────────────────────────────────────────────
# MediaPipe Tasks API reports handedness assuming a mirrored (selfie-camera) input,
# meaning "Right" = user's right hand and "Left" = user's left hand.
# OpenCV VideoCapture on Windows returns the raw (unmirrored) frame, so MediaPipe
# already compensates — set FLIP_HANDEDNESS = False.
# If your cursor tracks the WRONG hand (cursor moves when you raise your LEFT hand),
# toggle this to True.
FLIP_HANDEDNESS = False

# ── Debug ─────────────────────────────────────────────────────────────────────
# Set True to open a debug window showing detected landmarks, hand labels (L/R),
# gesture state, and pinch distances. Press Q in the window to quit.
DEBUG_GESTURES = False

# ── Windows OS ────────────────────────────────────────────────────────────────
# Do not change these unless you understand the Windows scheduler implications.
TIMER_RESOLUTION_MS = 1          # Sets Windows multimedia timer floor to 1ms
# psutil priority constant: HIGH_PRIORITY_CLASS = 0x80
# Do NOT use REALTIME_PRIORITY_CLASS (0x100) — it can starve system threads.
PROCESS_PRIORITY = 0x80

# ── Local overrides ───────────────────────────────────────────────────────────
# Put personal settings (camera index, thresholds, INTERACTION_MODE, …) in a
# config_local.py next to this file, e.g.:
#     CAMERA_INDEX = 1
# It is git-ignored, so your values survive `git pull` and never end up in a commit.
# The unit tests set AIRMOUSE_IGNORE_LOCAL_CONFIG=1 so they always see the defaults.
import os as _os

if _os.environ.get("AIRMOUSE_IGNORE_LOCAL_CONFIG") != "1":
    try:
        from config_local import *  # noqa: F401,F403
    except ImportError:
        pass
