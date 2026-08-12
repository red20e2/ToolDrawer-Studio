from __future__ import annotations

import http.client
import importlib
import socket
from contextlib import closing
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import cv2
import numpy as np
import pytest

from tooldrawer_studio.capture.image_loader import MAX_IMAGE_BYTES
from tooldrawer_studio.capture.pending import CaptureSessionService
from tooldrawer_studio.capture.phone_session import PhoneSession


def _server_module():
    return importlib.import_module("tooldrawer_studio.capture.phone_server")


def _png_bytes() -> bytes:
    pixels = np.zeros((20, 30, 3), dtype=np.uint8)
    pixels[4:16, 6:24] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _status_and_body(url: str) -> tuple[int, bytes]:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


@pytest.fixture
def running_server():
    module = _server_module()
    captures = CaptureSessionService()
    session = PhoneSession(captures, token_factory=lambda: "test-token")
    server = module.PhoneUploadServer(
        session,
        allow_test_loopback=True,
        address_supplier=lambda: ("127.0.0.1",),
        watcher_interval=0.05,
    )
    endpoint = server.start("127.0.0.1")
    try:
        yield server, session, captures, endpoint
    finally:
        server.stop()


def test_upload_page_requires_correct_token_and_has_no_external_resources(running_server):
    server, session, captures, endpoint = running_server

    status, _ = _status_and_body(f"http://{endpoint.host}:{endpoint.port}/upload")
    assert status == 403

    status, body = _status_and_body(endpoint.upload_url)
    text = body.decode("utf-8")
    assert status == 200
    assert "Take Photo" in text
    assert "Choose Existing Photo" in text
    assert 'capture="environment"' in text
    assert "https://" not in text
    assert "<script src=" not in text
    assert "<link" not in text
    assert "<img src=http" not in text


def test_only_upload_route_is_available(running_server):
    server, session, captures, endpoint = running_server

    status, _ = _status_and_body(
        f"http://{endpoint.host}:{endpoint.port}/anything?token=test-token"
    )

    assert status == 404


def test_valid_upload_adds_multiple_phone_pending_captures(running_server):
    server, session, captures, endpoint = running_server

    for name in ("one.png", "two.png"):
        request = Request(
            endpoint.upload_url,
            data=_png_bytes(),
            method="POST",
            headers={"Content-Type": "image/png", "X-Filename": name},
        )
        with urlopen(request, timeout=3) as response:
            assert response.status == 201

    assert [item.filename for item in captures.items()] == ["one.png", "two.png"]
    assert [item.source for item in captures.items()] == ["phone", "phone"]


def test_invalid_token_and_non_image_payloads_are_rejected(running_server):
    server, session, captures, endpoint = running_server
    wrong_url = f"http://{endpoint.host}:{endpoint.port}/upload?token=wrong"
    wrong = Request(
        wrong_url,
        data=_png_bytes(),
        method="POST",
        headers={"Content-Type": "image/png", "X-Filename": "photo.png"},
    )
    with pytest.raises(HTTPError) as exc_info:
        urlopen(wrong, timeout=3)
    assert exc_info.value.code == 403

    non_image = Request(
        endpoint.upload_url,
        data=b"plain text",
        method="POST",
        headers={"Content-Type": "text/plain", "X-Filename": "note.txt"},
    )
    with pytest.raises(HTTPError) as exc_info:
        urlopen(non_image, timeout=3)
    assert exc_info.value.code == 415
    assert captures.items() == ()


def test_oversized_declared_body_is_rejected_before_body_read(running_server):
    server, session, captures, endpoint = running_server
    connection = http.client.HTTPConnection(endpoint.host, endpoint.port, timeout=3)
    connection.putrequest("POST", "/upload?token=test-token")
    connection.putheader("Content-Type", "image/png")
    connection.putheader("X-Filename", "huge.png")
    connection.putheader("Content-Length", str(MAX_IMAGE_BYTES + 1))
    connection.endheaders()
    response = connection.getresponse()
    try:
        assert response.status == 413
    finally:
        response.read()
        connection.close()
    assert captures.items() == ()


def test_missing_length_and_oversized_filename_are_rejected(running_server):
    server, session, captures, endpoint = running_server

    connection = http.client.HTTPConnection(endpoint.host, endpoint.port, timeout=3)
    connection.putrequest("POST", "/upload?token=test-token")
    connection.putheader("Content-Type", "image/png")
    connection.putheader("X-Filename", "photo.png")
    connection.endheaders()
    response = connection.getresponse()
    try:
        assert response.status == 411
    finally:
        response.read()
        connection.close()

    too_long = Request(
        endpoint.upload_url,
        data=_png_bytes(),
        method="POST",
        headers={"Content-Type": "image/png", "X-Filename": "x" * 256},
    )
    with pytest.raises(HTTPError) as exc_info:
        urlopen(too_long, timeout=3)
    assert exc_info.value.code == 400
    assert captures.items() == ()


def test_filename_is_reduced_to_basename(running_server):
    server, session, captures, endpoint = running_server
    request = Request(
        endpoint.upload_url,
        data=_png_bytes(),
        method="POST",
        headers={"Content-Type": "image/png", "X-Filename": "../photo.png"},
    )
    with urlopen(request, timeout=3) as response:
        assert response.status == 201

    assert captures.items()[0].filename == "photo.png"


def test_network_address_loss_stops_session_without_deleting_pending_items():
    module = _server_module()
    captures = CaptureSessionService()
    session = PhoneSession(captures, token_factory=lambda: "test-token")
    addresses = ["127.0.0.1"]
    server = module.PhoneUploadServer(
        session,
        allow_test_loopback=True,
        address_supplier=lambda: tuple(addresses),
        watcher_interval=60,
    )
    endpoint = server.start("127.0.0.1")
    try:
        request = Request(
            endpoint.upload_url,
            data=_png_bytes(),
            method="POST",
            headers={"Content-Type": "image/png", "X-Filename": "kept.png"},
        )
        with urlopen(request, timeout=3) as response:
            assert response.status == 201
        addresses.clear()

        assert server.check_health() is False
        assert session.is_active is False
        assert [item.filename for item in captures.items()] == ["kept.png"]
    finally:
        server.stop()


def test_production_start_rejects_explicit_loopback():
    module = _server_module()
    session = PhoneSession(CaptureSessionService(), token_factory=lambda: "test-token")
    server = module.PhoneUploadServer(
        session,
        address_supplier=lambda: ("192.168.1.20",),
    )

    with pytest.raises(RuntimeError, match="private/local IPv4"):
        server.start("127.0.0.1")
