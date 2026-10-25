"""The phone as a camera: frames, pairing token, certificate, HTTPS server."""

import json
import ssl
import threading
import urllib.error
import urllib.request

import cv2
import numpy as np
import pytest

from core.phone_camera import PhoneCamera, PhoneServer, ensure_certificate, lan_addresses, pairing_token


def jpeg(width=640, height=480) -> bytes:
    ok, buf = cv2.imencode(".jpg", np.full((height, width, 3), 128, np.uint8))
    assert ok
    return buf.tobytes()


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


# ── Frames ────────────────────────────────────────────────────────────────────

def test_each_frame_is_taken_once():
    camera = PhoneCamera()
    assert camera.wait_frame(0.01) is None
    assert camera.feed(jpeg(1280, 720))
    frame = camera.wait_frame(0.01)
    assert frame.shape == (720, 1280, 3)
    assert camera.wait_frame(0.01) is None  # no new frame yet


def test_four_by_three_phone_frames_get_side_borders():
    camera = PhoneCamera()
    camera.feed(jpeg(640, 480))
    assert camera.wait_frame(0.01).shape == (480, 853, 3)


def test_portrait_frames_keep_their_shape_inside_borders():
    camera = PhoneCamera()
    camera.feed(jpeg(360, 640))
    height, width = camera.wait_frame(0.01).shape[:2]
    assert height == 640 and abs(width / height - 16 / 9) < 0.01


def test_garbage_is_refused():
    camera = PhoneCamera()
    assert not camera.feed(b"not a picture")
    assert camera.wait_frame(0.01) is None


def test_waiting_wakes_up_when_a_frame_arrives():
    camera = PhoneCamera()
    threading.Timer(0.05, camera.feed, args=(jpeg(),)).start()
    assert camera.wait_frame(2.0) is not None


def test_connected_and_fps():
    clock = Clock()
    camera = PhoneCamera(clock=clock)
    assert not camera.connected and camera.fps == 0.0
    for _ in range(11):
        camera.feed(jpeg(160, 90))
        clock.now += 0.05
    assert camera.connected
    assert camera.fps == pytest.approx(20.0, rel=0.05)
    clock.now += 5.0
    assert not camera.connected and camera.fps == 0.0


# ── Pairing token and certificate ─────────────────────────────────────────────

def test_pairing_token_survives_restarts(tmp_path):
    first = pairing_token(tmp_path / "phone-token.txt")
    assert len(first) >= 16
    assert pairing_token(tmp_path / "phone-token.txt") == first


def test_certificate_is_made_once_and_again_when_the_address_changes(tmp_path):
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    ensure_certificate(cert, key, ["192.168.0.10"])
    made = cert.read_bytes()
    ensure_certificate(cert, key, ["192.168.0.10"])
    assert cert.read_bytes() == made
    ensure_certificate(cert, key, ["192.168.0.22"])
    assert cert.read_bytes() != made


def test_lan_addresses_are_ipv4_and_not_loopback():
    for address in lan_addresses():
        assert address.count(".") == 3 and not address.startswith("127.")


# ── HTTPS server ──────────────────────────────────────────────────────────────

@pytest.fixture
def server(tmp_path):
    camera = PhoneCamera()
    srv = PhoneServer(camera, 0, status=lambda: {"mode": "move", "hand": True}, data_dir=tmp_path, host="127.0.0.1")
    assert srv.start()
    yield srv
    srv.stop()


def _unverified():
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def request(server, path, body=None, token=None):
    req = urllib.request.Request(f"https://127.0.0.1:{server.port}{path}", data=body, method="POST" if body else "GET")
    if token:
        req.add_header("X-AirMouse-Token", token)
    if body:
        req.add_header("Content-Type", "image/jpeg")
    try:
        with urllib.request.urlopen(req, context=_unverified(), timeout=5) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_the_phone_page_needs_the_pairing_token(server):
    assert request(server, "/")[0] == 403
    code, body = request(server, f"/?t={server.token}")
    assert code == 200
    assert server.token.encode() in body and b"__AIRMOUSE_TOKEN__" not in body


def test_frames_need_the_token_and_reach_the_camera(server):
    assert request(server, "/frame", body=jpeg(), token="wrong")[0] == 403
    assert server.camera.wait_frame(0.01) is None
    code, body = request(server, "/frame", body=jpeg(), token=server.token)
    assert code == 200
    assert json.loads(body) == {"mode": "move", "hand": True}
    assert server.camera.wait_frame(0.5) is not None


def test_a_bad_frame_is_refused(server):
    assert request(server, "/frame", body=b"xx", token=server.token)[0] == 400


def test_info_has_a_qr_code_for_the_address(server):
    info = server.info()
    if info["url"]:  # machines with no network have no address to show
        assert info["url"].startswith("https://") and f"t={server.token}" in info["url"]
        assert info["qr"].startswith("data:image/svg+xml")
    assert info["connected"] is False
