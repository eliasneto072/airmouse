# core/settings_server.py
"""
The settings page: a small web server on 127.0.0.1 (this computer only).

Every request must carry the per-run token that is part of the address the
tray opens (…/?t=TOKEN), so other web pages open in the browser can't see the
camera or change settings. Changes also need the token in a header, which a
plain cross-site form can't send. The page is core/web/settings.html.

GET  /?t=…              the page
GET  /api/state         saved values, schema, defaults, setup flag, "start with Windows"
GET  /api/status        live state: mode, hand, pose, look check, fps, clicks (polled ~6×/s)
GET  /api/preview       MJPEG stream: the camera, mirrored, with the hands drawn
GET  /api/cameras       one snapshot per camera (?refresh=1 probes again)
POST /api/settings      {"values": {...}} → validated and saved (applied on restart)
POST /api/setup-done    the first-run guide was finished or skipped
POST /api/startup       {"enabled": bool}
POST /api/restart       restart AirMouse so the saved settings take effect
"""

from __future__ import annotations

import http.server
import json
import logging
import secrets
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable

from core import settings_store

logger = logging.getLogger(__name__)

PAGE_PATH = Path(__file__).with_name("web") / "settings.html"
TOKEN_ENV = "AIRMOUSE_UI_TOKEN"  # passed on to the restarted AirMouse so the open page keeps working
PORT_ENV = "AIRMOUSE_UI_PORT"
PREVIEW_FPS = 12
MAX_BODY = 64 * 1024
_BROKEN = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # Linux needs it to re-bind the port right after a restart (TIME_WAIT); on
    # Windows it isn't needed and would let two servers share one port.
    allow_reuse_address = sys.platform != "win32"


class SettingsServer:
    """
    Args:
        control:       AppControl (processor, actuator, latest_frame/hands, fps, request_restart)
        running:       the settings this AirMouse started with (settings_store.snapshot(config))
        port:          preferred port; the next free one is used if it is taken (0 = any)
        bind_wait_s:   keep trying the preferred port this long (a restart: the old one is closing)
        render_preview(frame, hands, dominant, color) -> JPEG bytes
        probe_cameras(active_index, active_frame) -> [{"index", "active", "thumb"}]
        startup:       object with is_enabled() / enable() / disable() (core.startup)
    """

    def __init__(
        self,
        control,
        running: dict,
        port: int = 0,
        token: str | None = None,
        settings_path: Path | None = None,
        render_preview: Callable | None = None,
        probe_cameras: Callable | None = None,
        startup=None,
        mode_colors: dict | None = None,
        page_path: Path = PAGE_PATH,
        bind_wait_s: float = 0.0,
        interaction_mode: str = "modal",
    ) -> None:
        self.control = control
        self.interaction_mode = interaction_mode
        self.running = dict(running)
        self.token = token or secrets.token_urlsafe(18)
        self.boot_id = secrets.token_hex(4)
        self.settings_path = settings_path
        self._preferred_port = port
        self._bind_wait_s = bind_wait_s
        self._render = render_preview
        self._probe = probe_cameras
        self._startup = startup
        self._colors = mode_colors or {}
        self._page_path = page_path
        self._server: _HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._camera_lock = threading.Lock()
        self._cameras: list | None = None
        self.port: int | None = None

    # ── Life cycle ────────────────────────────────────────────────────────────

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self) -> bool:
        handler = self._handler_class()
        deadline = time.monotonic() + self._bind_wait_s
        server = self._bind(self._preferred_port, handler)
        while server is None and time.monotonic() < deadline:
            time.sleep(0.25)
            server = self._bind(self._preferred_port, handler)
        if server is None and self._preferred_port:
            for port in [*range(self._preferred_port + 1, self._preferred_port + 10), 0]:
                server = self._bind(port, handler)
                if server is not None:
                    break
        if server is None:
            logger.warning("Settings page unavailable: could not open a local port")
            return False
        self._server = server
        self.port = server.server_address[1]
        self._thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True, name="settings-page"
        )
        self._thread.start()
        logger.info("Settings page: http://127.0.0.1:%d/", self.port)
        return True

    @staticmethod
    def _bind(port: int, handler):
        try:
            return _HTTPServer(("127.0.0.1", port), handler)
        except OSError:
            return None

    def stop(self) -> None:
        self._stopping.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # ── Data ──────────────────────────────────────────────────────────────────

    def _dominant(self) -> str:
        return self.running.get("DOMINANT_HAND", "right")

    def state(self) -> dict:
        saved = settings_store.load(self.settings_path)
        values = dict(self.running)
        values.update({k: v for k, v in saved.items() if not k.startswith("_")})
        return {
            "boot": self.boot_id,
            "interaction_mode": self.interaction_mode,
            "values": settings_store.to_json(values),
            "running": settings_store.to_json(self.running),
            "defaults": settings_store.to_json(settings_store.DEFAULTS),
            "schema": [s.to_json() for s in settings_store.SCHEMA],
            "setup_done": saved.get(settings_store.SETUP_DONE_KEY) is True,
            "startup": self._startup_state(),
            "settings_file": str(self.settings_path or settings_store.default_path()),
            "problems": list(settings_store.problems),
        }

    def _startup_state(self) -> dict:
        if self._startup is None:
            return {"available": False, "enabled": False}
        try:
            return {"available": True, "enabled": bool(self._startup.is_enabled())}
        except Exception:  # not Windows
            return {"available": False, "enabled": False}

    def status(self) -> dict:
        c = self.control
        proc = c.processor
        dominant = self._dominant()
        hands = c.latest_hands

        def hand_of(side):
            return None if hands is None else getattr(hands, side)

        support_side = "left" if dominant == "right" else "right"
        data = {
            "boot": self.boot_id,
            "fps": round(float(c.fps or 0.0), 1),
            "camera": c.latest_frame is not None,
            "camera_error": getattr(c, "camera_error", None),
            "user_paused": bool(c.paused),
            "interaction_mode": self.interaction_mode,
            "dominant": dominant,
            "support_hand": hand_of(support_side) is not None,
        }
        status = getattr(proc, "status", None)
        if status is not None:
            data.update(
                mode=status.mode.value,
                paused=bool(status.paused),
                hand=bool(status.hand_visible),
                pending=status.pending,
                progress=round(float(status.progress), 3),
                support=status.support,
            )
        else:
            data.update(mode="classic", paused=False, hand=hand_of(dominant) is not None, pending=None, progress=0.0, support=None)
        hand = getattr(proc, "last_hand", None)
        data["pose"] = hand.pose.value if hand is not None and data["hand"] else None
        data["pinch"] = bool(hand is not None and data["hand"] and hand.pinch_index)
        look = getattr(proc, "last_attention", None)
        if getattr(proc, "attention_on", False) and look is not None:
            data["look"] = {
                "face": bool(look.face),
                "angle": None if look.angle is None else round(float(look.angle)),
                "looking": bool(look.looking),
            }
        else:
            data["look"] = None
        counts = getattr(c.actuator, "counts", None) or {}
        data["clicks"] = int(counts.get("click", 0))
        data["scrolls"] = int(counts.get("scroll", 0))
        return data

    def _mode_color(self) -> str:
        try:
            key = self.control.status_key()
        except Exception:
            key = "classic"
        return self._colors.get(key, "#4c8dff")

    def cameras(self, refresh: bool = False) -> list:
        with self._camera_lock:  # probing takes seconds: never twice at once
            if self._cameras is None or refresh:
                if self._probe is None:
                    self._cameras = []
                else:
                    # A camera that failed to open is probed like the others
                    active = -1 if getattr(self.control, "camera_error", None) else self.running.get("CAMERA_INDEX", 0)
                    self._cameras = self._probe(active, self.control.latest_frame)
            return self._cameras

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _handler_class(self):
        app = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "AirMouse"
            sys_version = ""

            def log_message(self, fmt, *args):
                logger.debug("settings page: " + fmt, *args)

            def do_GET(self):
                app._dispatch(self, "GET")

            def do_POST(self):
                app._dispatch(self, "POST")

        return Handler

    def _dispatch(self, h, method: str) -> None:
        parsed = urllib.parse.urlsplit(h.path)
        query = urllib.parse.parse_qs(parsed.query)
        route = parsed.path
        try:
            if h.headers.get("Host", "") not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
                return self._send(h, 403, b"Forbidden", "text/plain")
            if method == "GET" and route in ("/", "/index.html"):
                if not self._token_ok((query.get("t") or [""])[0]):
                    return self._send(h, 403, _NO_TOKEN_PAGE, "text/html; charset=utf-8")
                return self._send_page(h)
            if method == "GET":
                if not self._token_ok(h.headers.get("X-AirMouse-Token") or (query.get("t") or [""])[0]):
                    return self._json(h, 403, {"error": "missing or wrong token"})
                if route == "/api/state":
                    return self._json(h, 200, self.state())
                if route == "/api/status":
                    return self._json(h, 200, self.status())
                if route == "/api/cameras":
                    return self._json(h, 200, {"cameras": self.cameras(refresh=bool(query.get("refresh")))})
                if route == "/api/preview":
                    return self._stream_preview(h)
                return self._json(h, 404, {"error": "not found"})
            if method == "POST":
                # Header only: a cross-site <form> can't set it, and JSON forces a CORS preflight
                if not self._token_ok(h.headers.get("X-AirMouse-Token", "")):
                    return self._json(h, 403, {"error": "missing or wrong token"})
                body = self._read_json(h)
                if body is None:
                    return self._json(h, 400, {"error": "expected a JSON object"})
                return self._post(h, route, body)
            return self._json(h, 405, {"error": "method not allowed"})
        except _BROKEN:
            pass
        except Exception:
            logger.exception("Settings page request failed: %s %s", method, route)
            try:
                self._json(h, 500, {"error": "internal error, see airmouse.log"})
            except Exception:
                pass

    def _post(self, h, route: str, body: dict) -> None:
        if route == "/api/settings":
            values = body.get("values")
            if not isinstance(values, dict) or any(k.startswith("_") for k in values):
                return self._json(h, 400, {"error": "expected {\"values\": {...}}"})
            try:
                settings_store.update(values, self.settings_path)
            except ValueError as exc:
                errors = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {"_": str(exc)}
                return self._json(h, 400, {"errors": errors})
            logger.info("Settings saved: %s", ", ".join(f"{k}={v}" for k, v in sorted(values.items())))
            return self._json(h, 200, self.state())
        if route == "/api/setup-done":
            settings_store.update({settings_store.SETUP_DONE_KEY: True}, self.settings_path)
            return self._json(h, 200, self.state())
        if route == "/api/startup":
            enabled = body.get("enabled")
            if not isinstance(enabled, bool) or self._startup is None:
                return self._json(h, 400, {"error": "expected {\"enabled\": true|false}"})
            try:
                self._startup.enable() if enabled else self._startup.disable()
            except Exception as exc:
                return self._json(h, 500, {"error": f"could not change it: {exc}"})
            return self._json(h, 200, {"startup": self._startup_state()})
        if route == "/api/restart":
            logger.info("Restart requested from the settings page")
            self._json(h, 200, {"ok": True})
            threading.Timer(0.3, self.control.request_restart).start()
            return None
        return self._json(h, 404, {"error": "not found"})

    def _token_ok(self, token: str) -> bool:
        return secrets.compare_digest(token.encode("utf-8"), self.token.encode("utf-8"))

    @staticmethod
    def _read_json(h):
        try:
            length = int(h.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY or "application/json" not in h.headers.get("Content-Type", ""):
            return None
        try:
            body = json.loads(h.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return body if isinstance(body, dict) else None

    @staticmethod
    def _send(h, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        h.send_response(code)
        h.send_header("Content-Type", content_type)
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-store")
        h.send_header("Referrer-Policy", "no-referrer")
        h.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            h.send_header(key, value)
        h.end_headers()
        h.wfile.write(body)

    def _json(self, h, code: int, data) -> None:
        self._send(h, code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send_page(self, h) -> None:
        html = self._page_path.read_text(encoding="utf-8").replace("__AIRMOUSE_TOKEN__", self.token)
        self._send(
            h,
            200,
            html.encode("utf-8"),
            "text/html; charset=utf-8",
            {
                "Content-Security-Policy": (
                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
                ),
                "X-Frame-Options": "DENY",
            },
        )

    def _stream_preview(self, h) -> None:
        if self._render is None:
            return self._json(h, 404, {"error": "preview unavailable"})
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(b"--frame\r\n")
        period = 1.0 / PREVIEW_FPS
        last, sent_at = None, 0.0
        while not self._stopping.is_set():
            started = time.monotonic()
            frame = self.control.latest_frame
            # A browser shows a part once the next one starts: when the camera loop
            # stalls (paused), the last picture is sent again every second.
            if frame is not None and (frame is not last or started - sent_at > 1.0):
                last, sent_at = frame, started
                jpeg = self._render(frame, self.control.latest_hands, self._dominant(), self._mode_color())
                if jpeg:
                    h.wfile.write(
                        b"Content-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n--frame\r\n"
                    )
                    h.wfile.flush()
            self._stopping.wait(max(0.0, period - (time.monotonic() - started)))
        return None


_NO_TOKEN_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AirMouse</title>
<body style="font:16px/1.5 'Segoe UI',system-ui,sans-serif;max-width:34rem;margin:15vh auto;padding:0 16px;color:#1d1f24;background:#f2f3f5">
<h1 style="font-size:1.4rem">Open the settings from AirMouse</h1>
<p>This address only works when it comes from AirMouse itself. Right-click the AirMouse icon next to the clock and choose <b>Settings</b>.</p>
<p lang="pt">Abra as configurações pelo AirMouse: clique com o botão direito no ícone ao lado do relógio e escolha <b>Settings</b>.</p>
</body></html>""".encode("utf-8")
