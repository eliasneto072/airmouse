"""The settings page server: token, validation, live status, preview, restart."""

import http.client
import json
import re
import socket
import threading
import time
import types
import urllib.error
import urllib.request
from enum import Enum

import pytest

import config
from core import settings_store
from core.app_control import AppControl
from core.settings_server import PAGE_PATH, SettingsServer
from core.tracker import HandsResult
from tests.fixtures.hands import make_hand

TOKEN = "test-token"


class _Mode(Enum):
    MOVE = "move"


class FakeStartup:
    def __init__(self):
        self.enabled = False

    def is_enabled(self):
        return self.enabled

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False


@pytest.fixture
def rig(tmp_path):
    control = AppControl()
    control.restart_requested_event = threading.Event()
    original = control.request_restart

    def request_restart():
        original()
        control.restart_requested_event.set()

    control.request_restart = request_restart
    probes = []

    def probe(active, frame):
        probes.append(active)
        return [{"index": active, "active": True, "thumb": None}]

    startup = FakeStartup()
    server = SettingsServer(
        control,
        running=settings_store.snapshot(config),
        port=0,
        token=TOKEN,
        settings_path=tmp_path / "settings.json",
        render_preview=lambda frame, hands, dominant, color: b"JPEG" + color.encode(),
        probe_cameras=probe,
        startup=startup,
        mode_colors={"classic": "#111111", "move": "#4c8dff"},
    )
    assert server.start()
    yield types.SimpleNamespace(server=server, control=control, probes=probes, startup=startup, path=tmp_path / "settings.json")
    server.stop()


def get(rig, path, token=TOKEN):
    req = urllib.request.Request(f"http://127.0.0.1:{rig.server.port}{path}")
    if token:
        req.add_header("X-AirMouse-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers


def post(rig, path, body, token=TOKEN, content_type="application/json"):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{rig.server.port}{path}", data=data, method="POST")
    req.add_header("Content-Type", content_type)
    if token:
        req.add_header("X-AirMouse-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


# ── Access ────────────────────────────────────────────────────────────────────

def test_page_needs_the_token_in_the_address(rig):
    code, body, _ = get(rig, "/", token=None)
    assert code == 403 and b"Settings" in body
    code, body, headers = get(rig, f"/?t={TOKEN}", token=None)
    assert code == 200
    assert TOKEN.encode() in body and b"__AIRMOUSE_TOKEN__" not in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_api_rejects_a_wrong_token(rig):
    assert get(rig, "/api/state", token="nope")[0] == 403
    assert get(rig, "/api/state", token=None)[0] == 403


def test_api_rejects_another_host_name(rig):
    conn = http.client.HTTPConnection("127.0.0.1", rig.server.port, timeout=5)
    conn.request("GET", f"/api/state?t={TOKEN}", headers={"Host": f"evil.example:{rig.server.port}"})
    assert conn.getresponse().status == 403
    conn.close()


def test_changes_need_the_token_in_a_header_not_the_address(rig):
    code, _ = post(rig, f"/api/settings?t={TOKEN}", {"values": {"HUD_ENABLED": False}}, token=None)
    assert code == 403
    assert not rig.path.exists()


def test_changes_must_be_json(rig):
    code, _ = post(rig, "/api/settings", {"values": {"HUD_ENABLED": False}}, content_type="text/plain")
    assert code == 400


# ── Settings ──────────────────────────────────────────────────────────────────

def test_state_lists_values_schema_and_defaults(rig):
    code, body, _ = get(rig, "/api/state")
    state = json.loads(body)
    assert code == 200
    assert state["values"]["ATTENTION_GATE"] == config.ATTENTION_GATE
    assert state["interaction_mode"] == "modal" and "INTERACTION_MODE" not in state["values"]
    assert {s["key"] for s in state["schema"]} == set(settings_store.BY_KEY)
    assert state["defaults"]["POINTER_SPEED"] == settings_store.DEFAULTS["POINTER_SPEED"]
    assert state["setup_done"] is False
    assert state["startup"] == {"available": True, "enabled": False}


def test_saving_writes_the_file_and_reports_the_new_values(rig):
    code, state = post(rig, "/api/settings", {"values": {"POINTER_SPEED": 600, "MODES_ENABLED": ["move", "scroll"]}})
    assert code == 200
    assert state["values"]["POINTER_SPEED"] == 600.0
    assert state["running"]["POINTER_SPEED"] == config.POINTER_SPEED  # applied on restart
    assert settings_store.load(rig.path) == {"POINTER_SPEED": 600.0, "MODES_ENABLED": ("move", "scroll")}


def test_invalid_values_are_refused_with_reasons(rig):
    code, body = post(rig, "/api/settings", {"values": {"POINTER_SPEED": 9999, "HUD_ENABLED": True}})
    assert code == 400 and "POINTER_SPEED" in body["errors"]
    assert not rig.path.exists()


def test_metadata_cannot_be_written_as_a_setting(rig):
    assert post(rig, "/api/settings", {"values": {"_setup_done": True}})[0] == 400


def test_finishing_the_guide_is_remembered(rig):
    code, state = post(rig, "/api/setup-done", {})
    assert code == 200 and state["setup_done"] is True
    assert settings_store.setup_done(rig.path)


def test_start_with_windows_toggle(rig):
    code, body = post(rig, "/api/startup", {"enabled": True})
    assert code == 200 and body["startup"]["enabled"] and rig.startup.enabled
    assert post(rig, "/api/startup", {"enabled": "yes"})[0] == 400


def test_restart_stops_the_camera_loop(rig):
    code, body = post(rig, "/api/restart", {})
    assert code == 200
    assert rig.control.restart_requested_event.wait(2)
    assert rig.control.restart_requested and rig.control.stop.is_set()


# ── Live data ─────────────────────────────────────────────────────────────────

def test_status_without_a_gesture_pipeline(rig):
    rig.control.latest_hands = HandsResult(right=make_hand("point"))
    status = json.loads(get(rig, "/api/status")[1])
    assert status["mode"] == "classic" and status["hand"] is True
    assert status["camera"] is False and status["look"] is None


def test_status_of_the_modal_pipeline(rig):
    rig.control.processor = types.SimpleNamespace(
        status=types.SimpleNamespace(mode=_Mode.MOVE, paused=False, hand_visible=True, pending=None, progress=0.0, support="CTRL"),
        last_hand=types.SimpleNamespace(pose=types.SimpleNamespace(value="one"), pinch_index=True),
        attention_on=True,
        last_attention=types.SimpleNamespace(face=True, angle=12.4, looking=True),
    )
    rig.control.actuator = types.SimpleNamespace(counts={"click": 3})
    rig.control.latest_frame = object()
    rig.control.fps = 61.27
    status = json.loads(get(rig, "/api/status")[1])
    assert status["mode"] == "move" and status["pose"] == "one" and status["pinch"] is True
    assert status["support"] == "CTRL" and status["clicks"] == 3 and status["fps"] == 61.3
    assert status["look"] == {"face": True, "angle": 12, "looking": True}
    assert status["camera"] is True


def test_cameras_are_probed_once_until_asked_again(rig):
    get(rig, "/api/cameras")
    get(rig, "/api/cameras")
    assert len(rig.probes) == 1
    cameras = json.loads(get(rig, "/api/cameras?refresh=1")[1])["cameras"]
    assert len(rig.probes) == 2 and cameras[0]["active"]


def test_a_camera_that_failed_to_open_is_probed_like_the_others(rig):
    rig.control.camera_error = "Cannot open camera index 0"
    get(rig, "/api/cameras")
    assert rig.probes == [-1]


def test_preview_streams_jpeg_parts_in_the_mode_colour(rig):
    rig.control.latest_frame = object()
    conn = http.client.HTTPConnection("127.0.0.1", rig.server.port, timeout=5)
    conn.request("GET", f"/api/preview?t={TOKEN}")
    res = conn.getresponse()
    assert res.status == 200 and "multipart/x-mixed-replace" in res.getheader("Content-Type")
    data = b""
    deadline = time.monotonic() + 3
    while b"#111111" not in data and time.monotonic() < deadline:
        data += res.read1(4096)
    assert data.startswith(b"--frame\r\n") and b"JPEG#111111" in data
    conn.close()


# ── Port ──────────────────────────────────────────────────────────────────────

def test_a_taken_port_falls_back_to_the_next_one(tmp_path):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        server = SettingsServer(AppControl(), running={}, port=taken, settings_path=tmp_path / "s.json")
        try:
            assert server.start()
            assert server.port != taken
            assert server.url.startswith(f"http://127.0.0.1:{server.port}/?t=")
        finally:
            server.stop()


# ── The page ──────────────────────────────────────────────────────────────────

def test_the_page_has_words_for_every_setting_in_both_languages():
    page = PAGE_PATH.read_text(encoding="utf-8")
    for setting in settings_store.SCHEMA:
        if setting.key == "CAMERA_INDEX":  # the camera picker has its own words
            continue
        assert len(re.findall(rf'(?<![A-Z_]){setting.key}: "', page)) >= 2, setting.key  # pt + en
