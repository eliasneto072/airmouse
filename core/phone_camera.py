# core/phone_camera.py
"""
A phone's camera as AirMouse's camera, over Wi-Fi, with no app on the phone.

The phone opens https://<this PC>:PHONE_PORT/?t=<token> — the settings page
shows it as a QR code — allows the camera, and posts JPEG frames back.
PhoneCamera hands them to the camera loop the way a webcam would.

- HTTPS, because browsers only give a page the camera on a secure origin. The
  certificate is self-signed and made here once, so the phone warns the first
  time ("connection is not private" → Advanced → Continue).
- The server listens on the local network (unlike the settings page), so every
  request needs the pairing token in the QR code. The token is kept in
  DATA_DIR: a phone page left open reconnects by itself after a restart.
"""

from __future__ import annotations

import collections
import datetime
import http.server
import ipaddress
import json
import logging
import secrets
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import cv2
import numpy as np

from core import paths
from core.camera import letterbox_padding

logger = logging.getLogger(__name__)

PAGE_PATH = paths.resource("core/web/phone.html")
MAX_FRAME_BYTES = 4 * 1024 * 1024
CONNECTED_S = 2.0  # a phone that sent nothing for this long counts as gone


# ── Network address, pairing token, certificate ───────────────────────────────

def lan_addresses() -> list[str]:
    """This PC's IPv4 addresses on the local network, the most likely one first."""
    found: list[str] = []
    try:  # the address of the interface that would reach the internet (nothing is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    result = []
    for addr in found:
        ip = ipaddress.ip_address(addr)
        if ip.is_loopback or ip.is_link_local or addr in result:
            continue
        result.append(addr)
    # private ranges (home Wi-Fi) before anything else
    return sorted(result, key=lambda a: not ipaddress.ip_address(a).is_private)


def pairing_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="ascii").strip()
        if len(token) >= 16:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="ascii")
    return token


def _certificate_ok(cert_path: Path, addresses: list[str]) -> bool:
    from cryptography import x509

    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except (OSError, ValueError):
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    if cert.not_valid_after_utc - now < datetime.timedelta(days=30):
        return False
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    listed = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    return set(addresses) <= listed


def ensure_certificate(cert_path: Path, key_path: Path, addresses: list[str]) -> None:
    """A self-signed certificate for this PC's addresses (made again when they change)."""
    if key_path.exists() and _certificate_ok(cert_path, addresses):
        return
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AirMouse on this PC")])
    now = datetime.datetime.now(datetime.timezone.utc)
    alt_names = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(a)) for a in addresses]
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=800))  # Apple refuses TLS certificates over 825 days
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Phone camera: made a certificate for %s", ", ".join(addresses) or "localhost")


def qr_data_uri(text: str) -> str:
    import segno

    return segno.make(text, error="m").svg_data_uri(scale=5, border=2, dark="#1d1f24", light="#ffffff")


# ── Frames ────────────────────────────────────────────────────────────────────

class PhoneCamera:
    """Latest frame from the phone; the camera loop waits for each new one."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._cond = threading.Condition()
        self._frame = None
        self._seq = 0
        self._taken = 0
        self._last = 0.0
        self._times: collections.deque = collections.deque(maxlen=30)
        self._shape = None
        self._padding = None

    # AsyncCamera-compatible life cycle (the server is started separately)
    def start(self) -> "PhoneCamera":
        return self

    def stop(self) -> None:
        pass

    def feed(self, jpeg: bytes) -> bool:
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return False
        if frame.shape[:2] != self._shape:
            self._shape = frame.shape[:2]
            self._padding = letterbox_padding(self._shape[1], self._shape[0])
            logger.info("Phone camera: %dx%d frames", self._shape[1], self._shape[0])
        if self._padding is not None:
            top, bottom, left, right = self._padding
            frame = cv2.copyMakeBorder(frame, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        now = self._clock()
        with self._cond:
            self._frame = frame
            self._seq += 1
            self._last = now
            self._times.append(now)
            self._cond.notify_all()
        return True

    def wait_frame(self, timeout: float):
        """The next frame not yet taken, or None after ``timeout`` seconds."""
        with self._cond:
            if self._seq == self._taken:
                self._cond.wait(timeout)
            if self._seq == self._taken:
                return None
            self._taken = self._seq
            return self._frame

    def read(self):
        with self._cond:
            return self._frame

    @property
    def connected(self) -> bool:
        return self._seq > 0 and self._clock() - self._last < CONNECTED_S

    @property
    def fps(self) -> float:
        with self._cond:
            times = list(self._times)
        if len(times) < 2 or not self.connected:
            return 0.0
        return (len(times) - 1) / max(times[-1] - times[0], 1e-6)


# ── HTTPS server for the phone ────────────────────────────────────────────────

class _TLSServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # see settings_server

    def __init__(self, address, handler, context: ssl.SSLContext) -> None:
        self.context = context
        super().__init__(address, handler)

    def finish_request(self, request, client_address) -> None:
        # TLS handshake here, in the request's own thread, so a slow phone never blocks the others
        request.settimeout(30)
        try:
            tls = self.context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # e.g. the phone still deciding about the certificate warning
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            tls.close()


class PhoneServer:
    """
    Args:
        camera:   PhoneCamera that receives the frames
        port:     preferred port (the next free one is used if taken; 0 = any)
        status:   callable → small dict sent back with every frame (what AirMouse sees)
        host:     "0.0.0.0" for the local network (tests use 127.0.0.1)
    """

    def __init__(self, camera: PhoneCamera, port: int, status=None, data_dir: Path | None = None,
                 page_path: Path = PAGE_PATH, host: str = "0.0.0.0") -> None:
        self.camera = camera
        self._preferred = port
        self._status = status
        self._data_dir = Path(data_dir or paths.DATA_DIR)
        self._page_path = page_path
        self._host = host
        self._server: _TLSServer | None = None
        self.port: int | None = None
        self.token: str | None = None
        self.addresses: list[str] = []
        self._qr: tuple[str, str] | None = None

    def start(self) -> bool:
        try:
            self.token = pairing_token(self._data_dir / "phone-token.txt")
            self.addresses = lan_addresses()
            cert, key = self._data_dir / "phone-cert.pem", self._data_dir / "phone-key.pem"
            ensure_certificate(cert, key, self.addresses)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
        except Exception as exc:
            logger.error("Phone camera unavailable: %s", exc)
            return False
        handler = self._handler_class()
        ports = [self._preferred, *range(self._preferred + 1, self._preferred + 10)] if self._preferred else [0]
        for port in ports:
            try:
                self._server = _TLSServer((self._host, port), handler, context)
                break
            except OSError:
                continue
        if self._server is None:
            logger.error("Phone camera unavailable: no free port from %d", self._preferred)
            return False
        self.port = self._server.server_address[1]
        threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True, name="phone-camera"
        ).start()
        logger.info("Phone camera: open %s on the phone (same Wi-Fi)", self.url or f"port {self.port}")
        return True

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # ── What the settings page shows ──────────────────────────────────────────

    def urls(self) -> list[str]:
        if not self.port:
            return []
        return [f"https://{a}:{self.port}/?t={self.token}" for a in self.addresses]

    @property
    def url(self) -> str | None:
        urls = self.urls()
        return urls[0] if urls else None

    def info(self) -> dict:
        url = self.url
        if url and (self._qr is None or self._qr[0] != url):
            try:
                self._qr = (url, qr_data_uri(url))
            except Exception as exc:
                logger.warning("QR code unavailable: %s", exc)
                self._qr = (url, "")
        return {
            "url": url,
            "urls": self.urls(),
            "qr": self._qr[1] if self._qr and url else "",
            "connected": self.camera.connected,
            "fps": round(self.camera.fps, 1),
        }

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _handler_class(self):
        app = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keep-alive: one connection for all the frames
            server_version = "AirMouse"
            sys_version = ""

            def log_message(self, fmt, *args):
                logger.debug("phone: " + fmt, *args)

            def do_GET(self):
                app._get(self)

            def do_POST(self):
                app._post(self)

        return Handler

    def _token_ok(self, value: str) -> bool:
        return bool(self.token) and secrets.compare_digest(value.encode(), self.token.encode())

    @staticmethod
    def _send(h, code: int, body: bytes = b"", content_type: str = "application/json") -> None:
        h.send_response(code)
        h.send_header("Content-Type", content_type)
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-store")
        h.send_header("Referrer-Policy", "no-referrer")
        h.end_headers()
        if body:
            h.wfile.write(body)

    def _get(self, h) -> None:
        parsed = urllib.parse.urlsplit(h.path)
        token = (urllib.parse.parse_qs(parsed.query).get("t") or [""])[0]
        if parsed.path in ("/", "/index.html"):
            if not self._token_ok(token):
                return self._send(h, 403, _NO_TOKEN_PAGE, "text/html; charset=utf-8")
            page = self._page_path.read_text(encoding="utf-8").replace("__AIRMOUSE_TOKEN__", self.token)
            return self._send(h, 200, page.encode("utf-8"), "text/html; charset=utf-8")
        if parsed.path == "/hello":
            if not self._token_ok(h.headers.get("X-AirMouse-Token", "")):
                return self._send(h, 403, b'{"error":"wrong token"}')
            return self._send(h, 200, json.dumps(self._status_dict()).encode())
        return self._send(h, 404, b'{"error":"not found"}')

    def _post(self, h) -> None:
        try:
            length = int(h.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_FRAME_BYTES:
            h.close_connection = True
            return self._send(h, 400, b'{"error":"bad size"}')
        body = h.rfile.read(length)  # read it even when refusing, so keep-alive stays in sync
        if urllib.parse.urlsplit(h.path).path != "/frame":
            return self._send(h, 404, b'{"error":"not found"}')
        if not self._token_ok(h.headers.get("X-AirMouse-Token", "")):
            return self._send(h, 403, b'{"error":"wrong token"}')
        if not self.camera.feed(body):
            return self._send(h, 400, b'{"error":"not a JPEG"}')
        return self._send(h, 200, json.dumps(self._status_dict()).encode())

    def _status_dict(self) -> dict:
        if self._status is None:
            return {}
        try:
            return self._status()
        except Exception:
            return {}


_NO_TOKEN_PAGE = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AirMouse</title>
<body style="font:17px/1.5 system-ui,sans-serif;max-width:30rem;margin:12vh auto;padding:0 16px;color:#f1f2f4;background:#1d1f24">
<h1 style="font-size:1.4rem">Abra pelo código do AirMouse</h1>
<p>Este endereço precisa do código que aparece nos ajustes do AirMouse, no PC: escolha a câmera <b>Celular</b> e aponte a câmera do celular para o QR code.</p>
<p lang="en">Open this from the QR code in AirMouse's settings on the PC (camera: Phone).</p>
</body></html>""".encode("utf-8")
