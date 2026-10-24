# main.py
"""
AI Air Mouse — Entry point.

Startup sequence (ORDER MATTERS):
  1. Configure logging
  2. Set Windows timer resolution to 1ms
  3. Elevate process to HIGH_PRIORITY_CLASS
  4. Register main thread with MMCSS ("Games" profile)
  5. Build virtual desktop + trackpad zone (DPI awareness already set at display.py import)
  6. Disable Windows pointer acceleration (restore on exit)
  7. Start async camera
  8. Start MediaPipe hand tracker
  9. Instantiate gesture processor + actuator
  10. Run inference loop
  11. On exit: restore timer resolution, restore pointer precision, release all resources

Exit handling:
  - "Quit AirMouse" in the tray icon menu -> clean shutdown
  - Ctrl+C (KeyboardInterrupt) -> clean shutdown
  - Any unhandled exception -> log traceback, then clean shutdown
  - atexit handler as final safety net to ensure pointer precision is restored
"""

import atexit
import ctypes
import logging
import os
import time
import traceback
import webbrowser

import sys

# Relative paths (models/, the log file) must work however AirMouse is started:
# a shortcut, "Start with Windows" or a terminal in another folder. From source
# that is this folder; the installed AirMouse.exe writes to %LOCALAPPDATA%\AirMouse.
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from core import paths  # noqa: E402

paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(paths.DATA_DIR)

import psutil

import cv2

from config import (
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    DEBUG_GESTURES,
    LOG_FILE,
    PROCESS_PRIORITY,
    SETTINGS_PORT,
    SETTINGS_UI_ENABLED,
    TIMER_RESOLUTION_MS,
    TRAY_ENABLED,
)
from core import settings_store, single_instance
from core.app_control import AppControl
from core.tracker import HandsResult
from core.camera import AsyncCamera
from core.tracker import HandTracker
from core.gestures import build_orchestrator
from core.actuator import MouseActuator
from core.display import build_virtual_desktop, build_trackpad_zone
from core.version import __version__

if DEBUG_GESTURES:
    from core.debug_overlay import draw_debug_frame

# ── Logging ───────────────────────────────────────────────────────────────────

_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
_handlers: list[logging.Handler] = []
if sys.stderr is not None:  # pythonw.exe (shortcut / start with Windows) has no console
    _console = logging.StreamHandler()
    _console.setLevel(logging.INFO)
    _console.setFormatter(_formatter)
    _handlers.append(_console)
if LOG_FILE:
    _file = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    _file.setLevel(logging.DEBUG)
    _file.setFormatter(_formatter)
    _handlers.append(_file)
logging.basicConfig(level=logging.DEBUG if LOG_FILE else logging.INFO, handlers=_handlers)
for _noisy in ("PIL", "matplotlib", "absl"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logging.getLogger("core.tracker").setLevel(logging.INFO)  # per-frame handedness debug lines
logger = logging.getLogger("airmouse.main")


# ── Windows OS Setup ──────────────────────────────────────────────────────────

def _apply_windows_performance() -> dict:
    """
    Apply all Windows OS performance settings.
    Returns a dict of original values so they can be restored on exit.
    """
    original = {}

    # 1. Timer resolution: set to 1ms floor (default is 15.6ms)
    try:
        winmm = ctypes.windll.winmm
        winmm.timeBeginPeriod(TIMER_RESOLUTION_MS)
        original["timer_period"] = TIMER_RESOLUTION_MS
        logger.info("Windows timer resolution set to %dms", TIMER_RESOLUTION_MS)
    except Exception as e:
        logger.warning("Failed to set timer resolution: %s", e)

    # 2. Process priority: HIGH_PRIORITY_CLASS
    try:
        proc = psutil.Process(os.getpid())
        proc.nice(PROCESS_PRIORITY)
        logger.info("Process priority set to HIGH_PRIORITY_CLASS (0x%X)", PROCESS_PRIORITY)
    except psutil.AccessDenied:
        logger.warning("Could not elevate process priority — run as administrator for best performance")

    # 3. MMCSS: register main thread as "Games" workload class
    # This tells the Windows scheduler to give us CPU time more aggressively
    # and deprioritize background tasks (Defender, Windows Update, etc.) relative to us.
    try:
        avrt = ctypes.windll.avrt
        task_index = ctypes.c_ulong(0)
        avrt.AvSetMmThreadCharacteristicsW.restype = ctypes.c_void_p
        handle = avrt.AvSetMmThreadCharacteristicsW("Games", ctypes.byref(task_index))
        if handle:
            original["mmcss_handle"] = handle
            logger.info("MMCSS thread registered as 'Games' (handle=%d)", handle)
        else:
            logger.warning("MMCSS registration returned NULL handle")
    except Exception as e:
        logger.warning("MMCSS registration failed: %s", e)

    # 4. Disable "Enhance Pointer Precision" (Windows mouse acceleration)
    # This ballistic curve applied by Windows corrupts the 1€ Filter output.
    # SPI_GETMOUSE = 3, SPI_SETMOUSE = 4
    # The parameter is [threshold1, threshold2, acceleration]
    # acceleration=0 disables enhance pointer precision
    original_mouse_params = (ctypes.c_int * 3)(0, 0, 0)
    get_result = ctypes.windll.user32.SystemParametersInfoW(3, 0, original_mouse_params, 0)
    if not get_result:
        logger.warning("SystemParametersInfoW(SPI_GETMOUSE) failed — cannot save/restore mouse settings")
    else:
        original["mouse_params"] = list(original_mouse_params)
        no_accel = (ctypes.c_int * 3)(0, 0, 0)
        set_result = ctypes.windll.user32.SystemParametersInfoW(4, 0, no_accel, 2)
        if not set_result:
            logger.warning("SystemParametersInfoW(SPI_SETMOUSE) failed — pointer acceleration may not be disabled")
        else:
            logger.info("Windows pointer acceleration disabled")

    return original


def _restore_windows_settings(original: dict) -> None:
    """Restore all Windows settings mutated during startup."""

    # Restore timer resolution
    if "timer_period" in original:
        ctypes.windll.winmm.timeEndPeriod(original["timer_period"])
        logger.info("Windows timer resolution restored")

    # Unregister MMCSS
    if "mmcss_handle" in original:
        try:
            ctypes.windll.avrt.AvRevertMmThreadCharacteristics(original["mmcss_handle"])
            logger.info("MMCSS thread unregistered")
        except Exception as e:
            logger.warning("MMCSS revert failed: %s", e)

    # Restore pointer precision
    if "mouse_params" in original:
        restored = (ctypes.c_int * 3)(*original["mouse_params"])
        ctypes.windll.user32.SystemParametersInfoW(4, 0, restored, 2)
        logger.info("Windows pointer acceleration restored")


# ── Main Loop ─────────────────────────────────────────────────────────────────

RESTARTED_ENV = "AIRMOUSE_RESTARTED"


def _start_settings_page(control: AppControl, restarted: bool):
    """The settings page server, or None (disabled, or no free local port)."""
    if not SETTINGS_UI_ENABLED:
        return None
    import config
    from core import preview, startup
    from core.icon import MODE_COLORS
    from core.settings_server import PORT_ENV, TOKEN_ENV, SettingsServer

    port, token = SETTINGS_PORT, None
    if restarted:  # same address as before, so the page that asked for the restart reconnects
        port = int(os.environ.get(PORT_ENV) or SETTINGS_PORT)
        token = os.environ.get(TOKEN_ENV) or None
    server = SettingsServer(
        control,
        running=settings_store.snapshot(config),
        port=port,
        token=token,
        render_preview=preview.render_preview,
        probe_cameras=preview.probe_cameras,
        startup=startup,
        mode_colors=MODE_COLORS,
        bind_wait_s=5.0 if restarted else 0.0,
        interaction_mode=config.INTERACTION_MODE,
    )
    if not server.start():
        return None
    control.settings_url = server.url
    return server


def _start_tray(control: AppControl, message: str):
    if not TRAY_ENABLED:
        return None
    from core.tray import Tray

    tray = Tray(control, LOG_FILE)
    if not tray.start():
        return None
    tray.notify(message)
    return tray


def _restart(server) -> None:
    """Start a fresh AirMouse (it reads the saved settings) once this one has let go of everything."""
    import subprocess

    from core import startup
    from core.settings_server import PORT_ENV, TOKEN_ENV

    env = dict(os.environ)
    env[RESTARTED_ENV] = "1"
    if server is not None and server.port:
        env[TOKEN_ENV] = server.token
        env[PORT_ENV] = str(server.port)
    single_instance.release()
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    try:
        subprocess.Popen(startup.launch_command(), env=env, cwd=str(paths.DATA_DIR), close_fds=True, creationflags=flags)
        logger.info("Restarting AirMouse to apply the new settings")
    except OSError as exc:
        logger.error("Could not restart AirMouse: %s", exc)


def run() -> None:
    restarted = os.environ.get(RESTARTED_ENV) == "1"
    if not single_instance.acquire(wait_s=15.0 if restarted else 0.0):
        single_instance.show_already_running()
        return

    original_settings: dict = {}

    def _emergency_restore():
        """atexit safety net — runs even on unhandled exceptions."""
        if original_settings:
            _restore_windows_settings(original_settings)

    atexit.register(_emergency_restore)

    logger.info("=== AI Air Mouse %s starting ===", __version__)
    for problem in settings_store.problems:
        logger.warning("Settings file: %s", problem)
    first_run = not settings_store.setup_done()

    # Apply OS settings before anything else
    original_settings.update(_apply_windows_performance())

    # Build display geometry
    desktop = build_virtual_desktop()
    trackpad = build_trackpad_zone()

    # Instantiate subsystems
    actuator = MouseActuator(desktop.total_width, desktop.total_height)

    frame_count = 0
    fps_clock = time.perf_counter()
    fps_logged = fps_clock
    tray_clock = 0.0
    none_count = 0
    control = AppControl()
    control.actuator = actuator
    if single_instance.watch_quit_requests(control.stop.set):  # installer / uninstaller asking us to close
        logger.debug("Listening for quit requests from the installer")
    tray = None
    processor = None
    server = _start_settings_page(control, restarted)

    if restarted:
        hello = "Settings applied."
    elif first_run and server is not None:
        hello = "Welcome! Finish setting up AirMouse in your browser."
    else:
        hello = "AirMouse is running — right-click the icon for options."

    camera = AsyncCamera()
    try:
        camera.start()
    except RuntimeError as exc:
        logger.error("%s", exc)
        control.camera_error = str(exc)
        camera = None

    try:
        if camera is None:
            # No camera: keep the tray and the settings page up so another camera can be chosen
            tray = _start_tray(control, "AirMouse can't open the camera — choose another one in Settings.")
            if server is None:
                return
            webbrowser.open(server.url + "#settings/camera")
            while not control.stop.wait(0.3):
                if tray is not None:
                    tray.refresh()
            return

        with HandTracker() as tracker:
            processor = build_orchestrator(actuator, desktop, trackpad)
            control.processor = processor
            tray = _start_tray(control, hello)
            if server is not None and first_run and not restarted:
                webbrowser.open(server.url + "#setup")

            logger.info("Running. Quit from the tray icon (or Ctrl+C in a terminal).")

            while not control.stop.is_set():
                if tray is not None and time.perf_counter() - tray_clock > 0.3:
                    tray_clock = time.perf_counter()
                    tray.refresh()

                if control.paused:
                    # Gestures paused from the tray: no tracking (saves CPU); an empty
                    # frame lets the pipeline release keys and turn itself off.
                    control.latest_hands = None
                    processor.process(HandsResult(), None)
                    time.sleep(0.03)
                    continue

                frame = camera.read()

                if frame is None:
                    # First frames haven't arrived yet — yield briefly
                    none_count += 1
                    if none_count > 5000:  # ~5 seconds of no frames
                        logger.error("Camera produced no frames for ~5 seconds — camera may be disconnected")
                        break
                    time.sleep(0.001)
                    continue

                none_count = 0

                hands = tracker.process(frame)
                processor.process(hands, frame)
                control.latest_frame = frame
                control.latest_hands = hands

                if DEBUG_GESTURES:
                    annotated = draw_debug_frame(frame, hands, processor.right_state)
                    cv2.imshow("AirMouse Debug", annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                # FPS: shown live in the settings page, logged once per 5 seconds
                frame_count += 1
                now = time.perf_counter()
                if now - fps_clock >= 1.0:
                    control.fps = frame_count / (now - fps_clock)
                    frame_count = 0
                    fps_clock = now
                    if now - fps_logged >= 5.0:
                        fps_logged = now
                        logger.info("FPS: %.1f", control.fps)

    except KeyboardInterrupt:
        logger.info("Ctrl+C received — shutting down cleanly")
    except Exception:
        logger.error("Unhandled exception:\n%s", traceback.format_exc())
    finally:
        if tray is not None:
            tray.stop()
        if server is not None:
            server.stop()
        if DEBUG_GESTURES:
            cv2.destroyAllWindows()
        # Never leave a mouse button or key pressed on exit
        if processor is not None:
            processor.shutdown()
        actuator.release_all()
        if camera is not None:
            camera.stop()
        _restore_windows_settings(original_settings)
        original_settings.clear()  # prevent atexit double-restore
        logger.info("=== AI Air Mouse stopped ===")
        if control.restart_requested:
            _restart(server)


def self_test() -> int:
    """
    ``AirMouse.exe --self-test``: loads every piece without a camera or a mouse.
    The installer build runs it, so a library missing from the package fails the
    build instead of the user's first start. Result in the log; exit code 0 = ok.
    """
    import numpy as np

    logger.info("Self-test: AirMouse %s, installed=%s, data in %s", __version__, paths.FROZEN, paths.DATA_DIR)
    try:
        # Modules loaded by name at run time (easy for the packager to miss)
        import pynput.keyboard  # noqa: F401
        import pynput.mouse  # noqa: F401
        import pystray  # noqa: F401
        import tkinter  # noqa: F401
        import winsound  # noqa: F401
        from screeninfo.enumerators import windows  # noqa: F401

        from core import preview
        from core.face_tracker import FaceTracker
        from core.icon import draw_icon
        from core.settings_server import PAGE_PATH
        from core.tray import Tray  # noqa: F401

        assert PAGE_PATH.exists(), f"settings page missing: {PAGE_PATH}"
        draw_icon()
        frame = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH, 3), np.uint8)
        with HandTracker() as tracker:
            tracker.process(frame)
        face = FaceTracker()
        face.process(frame)
        face.close()
        assert preview.render_preview(frame), "preview encoding failed"
        try:
            desktop = build_virtual_desktop()
            logger.info("Self-test: desktop %dx%d", desktop.total_width, desktop.total_height)
        except Exception as exc:  # build machines may have no monitor
            logger.warning("Self-test: no monitor information (%s)", exc)
    except Exception:
        logger.error("Self-test FAILED:\n%s", traceback.format_exc())
        return 1
    logger.info("Self-test passed")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    run()
