from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from ops.gpu_pool_controller.runpod_prod_worker_http import (
    RunPodProdWorkerHttpClient,
    RunPodProdWorkerHttpError,
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

    client = RunPodProdWorkerHttpClient(urlopen_func=urlopen)

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


def test_prod_worker_http_ignores_environment_proxies_by_default(monkeypatch):
    captured: dict[str, object] = {}

    class DirectOpener:
        def open(self, request, *, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse(200, b'{"ok": true}')

    def build_opener(*handlers):
        captured["handlers"] = handlers
        return DirectOpener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("environment-aware urlopen must not be used")
        ),
    )

    payload = RunPodProdWorkerHttpClient().json(
        "GET",
        "http://100.107.220.127:8003/system/workers",
    )

    assert payload == {"ok": True, "_status": 200}
    assert captured["url"] == "http://100.107.220.127:8003/system/workers"
    assert captured["timeout"] == 30
    handlers = captured["handlers"]
    assert len(handlers) == 1
    assert isinstance(handlers[0], urllib.request.ProxyHandler)
    assert handlers[0].proxies == {}


def test_http_json_returns_allowlisted_error_payload():
    def urlopen(request, *, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "not found",
            {},
            io.BytesIO(b'{"missing": true}'),
        )

    client = RunPodProdWorkerHttpClient(urlopen_func=urlopen)

    payload = client.json(
        "GET",
        "https://api.example/tasks/missing?token=secret",
        allow_statuses=(404,),
    )

    assert payload == {"missing": True, "_status": 404}


def test_http_json_rejects_invalid_json_without_leaking_query():
    def urlopen(request, *, timeout):
        return FakeResponse(200, b"not-json")

    client = RunPodProdWorkerHttpClient(urlopen_func=urlopen)

    with pytest.raises(RunPodProdWorkerHttpError) as exc_info:
        client.json("GET", "https://api.example/tasks?token=secret")

    assert "https://api.example/tasks" in str(exc_info.value)
    assert "token=secret" not in str(exc_info.value)


def test_http_request_wraps_network_error_with_safe_url():
    def urlopen(request, *, timeout):
        raise urllib.error.URLError("connection refused")

    client = RunPodProdWorkerHttpClient(urlopen_func=urlopen)

    with pytest.raises(RunPodProdWorkerHttpError) as exc_info:
        client.request("GET", "https://api.example/raw?token=secret")

    assert "GET https://api.example/raw network error" in str(exc_info.value)
    assert "token=secret" not in str(exc_info.value)


def test_safe_url_strips_query_and_fragment():
    assert (
        safe_url("https://api.example/path?token=secret#frag")
        == "https://api.example/path"
    )
