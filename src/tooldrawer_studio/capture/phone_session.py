from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable

from .pending import CaptureSessionService, PendingCapture


IDLE_TIMEOUT_SECONDS = 30 * 60


class PhoneSession:
    def __init__(
        self,
        captures: CaptureSessionService,
        *,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._captures = captures
        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._lock = threading.RLock()
        self._active = False
        self._token: str | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._last_activity: float | None = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def token(self) -> str | None:
        with self._lock:
            return self._token

    @property
    def host(self) -> str | None:
        with self._lock:
            return self._host

    @property
    def port(self) -> int | None:
        with self._lock:
            return self._port

    @property
    def last_activity(self) -> float | None:
        with self._lock:
            return self._last_activity

    @property
    def url(self) -> str:
        with self._lock:
            if not self._active or self._token is None or self._host is None or self._port is None:
                raise RuntimeError("Phone session is not active")
            return f"http://{self._host}:{self._port}/upload?token={self._token}"

    def start(self, host: str, port: int) -> None:
        if not host:
            raise ValueError("Phone session host is required")
        if port < 0 or port > 65535:
            raise ValueError("Phone session port is invalid")
        with self._lock:
            self._token = self._token_factory()
            if not self._token:
                raise ValueError("Phone session token must not be empty")
            self._host = host
            self._port = port
            self._last_activity = self._clock()
            self._active = True

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._token = None
            self._host = None
            self._port = None
            self._last_activity = None

    def authorize(self, token: str | None) -> bool:
        with self._lock:
            if not self._active or self._token is None or token is None:
                return False
            return secrets.compare_digest(self._token, token)

    def record_page_activity(self, token: str | None) -> bool:
        with self._lock:
            if not self.authorize(token):
                return False
            self._last_activity = self._clock()
            return True

    def accept_upload(
        self,
        token: str | None,
        raw: bytes,
        filename: str,
    ) -> PendingCapture:
        with self._lock:
            if not self.authorize(token):
                raise PermissionError("Invalid or expired phone session")
            item = self._captures.add_bytes("phone", raw, filename)
            self._last_activity = self._clock()
            return item

    def expire_if_idle(self) -> bool:
        with self._lock:
            if not self._active or self._last_activity is None:
                return False
            if self._clock() - self._last_activity < IDLE_TIMEOUT_SECONDS:
                return False
            self._active = False
            self._token = None
            self._host = None
            self._port = None
            self._last_activity = None
            return True
