from __future__ import annotations

import io
import urllib.error

import pytest

from ops.gpu_pool_controller.runpod_http import (
    RunPodHttpClient,
    RunPodHttpError,
    safe_url,
)


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args) -> None:
        return None


def test_http_json_posts_json_with_query_params():
    captured: dict[str, object] = {}

    def urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["data"] = request.data
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse(200, b'{"ok": true}')

    client = RunPodHttpClient(urlopen_func=urlopen)

    payload = client.json(
        "POST",
        "https://api.example/tasks",
        params={"q": ["a", "b"]},
        json_body={"x": 1},
        headers={"Authorization": "Bearer hidden"},
    )

    assert payload == {"ok": True, "_status": 200}
    assert captured["url"] == "https://api.example/tasks?q=a&q=b"
    assert captured["method"] == "POST"
    assert captured["data"] == b'{"x": 1}'
    assert captured["timeout"] == 30
    assert captured["headers"]["Authorization"] == "Bearer hidden"
    assert captured["headers"]["Content-type"] == "application/json"


def test_http_request_returns_raw_response():
    def urlopen(request, *, timeout):
        assert request.get_method() == "GET"
        assert request.get_header("User-agent") == "AllBot-RunPod-Operator/1"
        assert timeout == 30
        return FakeResponse(200, b"raw-bytes")

    payload = RunPodHttpClient(urlopen_func=urlopen).request(
        "GET",
        "https://api.example/raw",
    )

    assert payload == {"status": 200, "text": "raw-bytes", "raw": b"raw-bytes"}


def test_http_request_preserves_explicit_user_agent():
    def urlopen(request, *, timeout):
        assert request.get_header("User-agent") == "Custom-Canary/2"
        assert timeout == 30
        return FakeResponse(200, b"ok")

    payload = RunPodHttpClient(urlopen_func=urlopen).request(
        "GET",
        "https://api.example/raw",
        headers={"User-Agent": "Custom-Canary/2"},
    )

    assert payload["status"] == 200


def test_http_json_returns_allowlisted_error_payload():
    def urlopen(request, *, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "not found",
            {},
            io.BytesIO(b'{"missing": true}'),
        )

    payload = RunPodHttpClient(urlopen_func=urlopen).json(
        "GET",
        "https://api.example/tasks/missing?token=secret",
        allow_statuses=(404,),
    )

    assert payload == {"missing": True, "_status": 404}


def test_http_request_exposes_rejected_status_without_parsing_message():
    def urlopen(request, *, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            502,
            "bad gateway",
            {},
            io.BytesIO(b""),
        )

    client = RunPodHttpClient(urlopen_func=urlopen)

    with pytest.raises(RunPodHttpError) as exc_info:
        client.request("GET", "https://api.example/system/workers")

    assert exc_info.value.http_status == 502


def test_http_json_rejects_invalid_json_without_leaking_query():
    def urlopen(request, *, timeout):
        return FakeResponse(200, b"not-json")

    client = RunPodHttpClient(urlopen_func=urlopen)

    with pytest.raises(RunPodHttpError) as exc_info:
        client.json("GET", "https://api.example/tasks?token=secret")

    assert "https://api.example/tasks" in str(exc_info.value)
    assert "token=secret" not in str(exc_info.value)


def test_http_request_wraps_network_error_with_safe_url():
    def urlopen(request, *, timeout):
        raise urllib.error.URLError("connection refused")

    client = RunPodHttpClient(urlopen_func=urlopen)

    with pytest.raises(RunPodHttpError) as exc_info:
        client.request("GET", "https://api.example/raw?token=secret")

    assert "GET https://api.example/raw network error" in str(exc_info.value)
    assert "token=secret" not in str(exc_info.value)


def test_safe_url_strips_query_and_fragment():
    assert (
        safe_url("https://api.example/path?token=secret#frag")
        == "https://api.example/path"
    )
