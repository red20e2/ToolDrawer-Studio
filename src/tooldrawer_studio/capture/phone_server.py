from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from .image_loader import MAX_IMAGE_BYTES
from .network import is_private_lan_ipv4, private_ipv4_candidates, select_private_ipv4
from .phone_session import PhoneSession


MAX_FILENAME_HEADER_CHARS = 255


_UPLOAD_PAGE = b"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ToolDrawer Studio Photo Upload</title>
<style>
body{font-family:system-ui,sans-serif;max-width:32rem;margin:2rem auto;padding:0 1rem;background:#f6f6f6;color:#111}
.card{background:white;border:1px solid #ccc;border-radius:12px;padding:1.25rem}
label{display:block;margin:1rem 0;padding:1rem;border:1px solid #aaa;border-radius:8px;text-align:center;font-weight:600}
input{display:none}#status{min-height:1.5rem;margin-top:1rem}
</style>
</head>
<body><div class="card">
<h1>ToolDrawer Studio</h1>
<p>Send photos directly to the pending capture tray on this PC.</p>
<label>Take Photo<input id="camera" type="file" accept="image/*" capture="environment"></label>
<label>Choose Existing Photo<input id="existing" type="file" accept="image/*"></label>
<div id="status" aria-live="polite"></div>
</div>
<script>
const statusBox=document.getElementById('status');
const token=new URLSearchParams(window.location.search).get('token')||'';
async function sendFile(file){
  if(!file){return;}
  statusBox.textContent='Uploading...';
  try{
    const response=await fetch('/upload?token='+encodeURIComponent(token),{
      method:'POST',body:file,
      headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':file.name||'phone-upload'}
    });
    statusBox.textContent=response.ok?'Uploaded. You can send another photo.':'Upload failed: '+response.status;
  }catch(error){statusBox.textContent='Upload failed. Check that the phone is still on the same network.';}
}
document.getElementById('camera').addEventListener('change',event=>sendFile(event.target.files[0]));
document.getElementById('existing').addEventListener('change',event=>sendFile(event.target.files[0]));
</script></body></html>"""


@dataclass(frozen=True, slots=True)
class ServerEndpoint:
    host: str
    port: int
    upload_url: str


class _CaptureHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


class _UploadHandler(BaseHTTPRequestHandler):
    server: _CaptureHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        # Request URLs contain the temporary token. Never emit them to stderr.
        return

    @property
    def owner(self) -> "PhoneUploadServer":
        return self.server.capture_owner  # type: ignore[attr-defined]

    def _request_parts(self) -> tuple[str, str | None]:
        parsed = urlsplit(self.path)
        token = parse_qs(parsed.query, keep_blank_values=True).get("token", [None])[0]
        return parsed.path, token

    def _send(
        self,
        status: int,
        body: bytes = b"",
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:
        path, token = self._request_parts()
        if path != "/upload":
            self._send(404, b"Not found")
            return
        if not self.owner.session.record_page_activity(token):
            self._send(403, b"Invalid or expired phone session")
            return
        self._send(200, _UPLOAD_PAGE, "text/html; charset=utf-8")

    def do_POST(self) -> None:
        path, token = self._request_parts()
        if path != "/upload":
            self._send(404, b"Not found")
            return
        if not self.owner.session.authorize(token):
            self._send(403, b"Invalid or expired phone session")
            return

        content_type = (
            self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if not content_type.startswith("image/"):
            self._send(415, b"Only image uploads are accepted")
            return

        filename_header = self.headers.get("X-Filename", "")
        if len(filename_header) > MAX_FILENAME_HEADER_CHARS:
            self._send(400, b"Filename is too long")
            return

        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self._send(411, b"Content-Length is required")
            return
        try:
            content_length = int(length_header)
        except ValueError:
            self._send(400, b"Invalid Content-Length")
            return
        if content_length <= 0:
            self._send(400, b"Image body is empty")
            return
        if content_length > MAX_IMAGE_BYTES:
            self._send(413, b"Image exceeds the 50 MB limit")
            return

        raw = self.rfile.read(content_length)
        if len(raw) != content_length:
            self._send(400, b"Incomplete upload")
            return

        filename = Path(filename_header).name if filename_header else ""
        if not filename:
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/bmp": ".bmp",
                "image/tiff": ".tiff",
            }.get(content_type, ".img")
            filename = f"phone-upload{extension}"

        try:
            self.owner.session.accept_upload(token, raw, filename)
        except PermissionError:
            self._send(403, b"Invalid or expired phone session")
            return
        except ValueError:
            self._send(415, b"Unsupported or invalid image")
            return
        self._send(201, b"Uploaded")

    def do_HEAD(self) -> None:
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()


class PhoneUploadServer:
    def __init__(
        self,
        session: PhoneSession,
        *,
        allow_test_loopback: bool = False,
        address_supplier: Callable[[], tuple[str, ...]] = private_ipv4_candidates,
        watcher_interval: float = 1.0,
    ) -> None:
        if watcher_interval <= 0:
            raise ValueError("Watcher interval must be positive")
        self.session = session
        self._allow_test_loopback = allow_test_loopback
        self._address_supplier = address_supplier
        self._watcher_interval = watcher_interval
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._httpd: _CaptureHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._watcher_thread: threading.Thread | None = None
        self._bound_host: str | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._httpd is not None and self.session.is_active

    @property
    def bound_host(self) -> str | None:
        with self._lock:
            return self._bound_host

    def _validate_host(self, host: str | None) -> str:
        if host is None:
            return select_private_ipv4(self._address_supplier())
        if self._allow_test_loopback and host == "127.0.0.1":
            return host
        if not is_private_lan_ipv4(host):
            raise RuntimeError(
                "No private/local IPv4 address is available for phone capture"
            )
        return host

    def start(self, host: str | None = None) -> ServerEndpoint:
        bind_host = self._validate_host(host)
        with self._lock:
            if self._httpd is not None:
                raise RuntimeError("Phone upload server is already running")

            httpd = _CaptureHTTPServer((bind_host, 0), _UploadHandler)
            httpd.capture_owner = self  # type: ignore[attr-defined]
            port = int(httpd.server_address[1])
            self.session.start(bind_host, port)
            self._httpd = httpd
            self._bound_host = bind_host
            self._stop_event.clear()

            self._server_thread = threading.Thread(
                target=httpd.serve_forever,
                name="ToolDrawerPhoneUpload",
                daemon=True,
            )
            self._watcher_thread = threading.Thread(
                target=self._watch_loop,
                name="ToolDrawerPhoneUploadWatch",
                daemon=True,
            )
            self._server_thread.start()
            self._watcher_thread.start()
            return ServerEndpoint(bind_host, port, self.session.url)

    def _watch_loop(self) -> None:
        while not self._stop_event.wait(self._watcher_interval):
            if not self.check_health():
                return

    def check_health(self) -> bool:
        with self._lock:
            if self._httpd is None or self._bound_host is None:
                return False
            bound_host = self._bound_host

        if self.session.expire_if_idle():
            self.stop()
            return False
        if not self.session.is_active:
            self.stop()
            return False
        if bound_host not in self._address_supplier():
            self.stop()
            return False
        return True

    def stop(self) -> None:
        current = threading.current_thread()
        with self._lock:
            httpd = self._httpd
            server_thread = self._server_thread
            watcher_thread = self._watcher_thread
            self._httpd = None
            self._server_thread = None
            self._watcher_thread = None
            self._bound_host = None
            self._stop_event.set()
            self.session.stop()

        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if server_thread is not None and server_thread is not current:
            server_thread.join(timeout=2.0)
        if watcher_thread is not None and watcher_thread is not current:
            watcher_thread.join(timeout=2.0)
