from __future__ import annotations

import pytest

from ops.gpu_pool_controller.runpod_prod_worker_control import (
    RunPodProdWorkerControlClient,
    RunPodProdWorkerControlConfig,
    RunPodProdWorkerControlError,
)


def _config(**overrides) -> RunPodProdWorkerControlConfig:
    values = {
        "central_url": "https://central.example/",
        "web_api_url": "https://web.example/",
        "web_user_id": 3,
        "web_pwd_ver": 1,
        "web_bearer_token": "web-token",
        "agent_token": "agent-token",
    }
    values.update(overrides)
    return RunPodProdWorkerControlConfig(**values)


def test_web_bearer_token_takes_priority():
    client = RunPodProdWorkerControlClient(
        _config(web_bearer_token="explicit-token"),
        http_json_func=lambda *args, **kwargs: {},
    )

    assert client.web_token() == "explicit-token"
    assert client.web_auth_headers() == {"Authorization": "Bearer explicit-token"}


def test_web_token_falls_back_to_jwt(monkeypatch):
    from src.web_api.core import security

    calls: list[dict[str, object]] = []

    def fake_create_access_token(**kwargs):
        calls.append(kwargs)
        return "jwt-token"

    monkeypatch.setattr(security, "create_access_token", fake_create_access_token)
    client = RunPodProdWorkerControlClient(
        _config(web_bearer_token="", web_user_id=42, web_pwd_ver=7),
        http_json_func=lambda *args, **kwargs: {},
    )

    assert client.web_token() == "jwt-token"
    assert calls == [
        {"subject": "42", "pwd_ver": 7, "channel": "runpod_prod_worker"}
    ]


def test_agent_control_get_and_set_use_agent_headers():
    calls: list[tuple[str, str, dict[str, object]]] = []

    def http_json(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"ok": True, "state": "disabled"}

    client = RunPodProdWorkerControlClient(_config(), http_json_func=http_json)

    assert client.get_agent_control("agent-1") == {"ok": True, "state": "disabled"}
    assert client.set_agent_control(
        "agent-1",
        "enabled",
        reason="canary",
    ) == {"ok": True, "state": "disabled"}

    assert calls[0] == (
        "GET",
        "https://central.example/api/agent/task/control/agent-1",
        {"headers": {"Authorization": "Bearer agent-token"}},
    )
    assert calls[1] == (
        "POST",
        "https://central.example/api/agent/task/control/agent-1",
        {
            "json_body": {"state": "enabled", "reason": "canary"},
            "headers": {"Authorization": "Bearer agent-token"},
        },
    )


def test_agent_token_is_required_for_control():
    client = RunPodProdWorkerControlClient(
        _config(agent_token=""),
        http_json_func=lambda *args, **kwargs: {},
    )

    with pytest.raises(RunPodProdWorkerControlError, match="AGENT_SECRET_TOKEN"):
        client.get_agent_control("agent-1")


def test_fetch_workers_filters_non_dict_entries():
    def http_json(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://central.example/system/workers"
        assert kwargs == {}
        return {"workers": [{"agent_id": "agent-1"}, "bad", None]}

    client = RunPodProdWorkerControlClient(_config(), http_json_func=http_json)

    assert client.fetch_workers() == [{"agent_id": "agent-1"}]


def test_fetch_workers_rejects_non_list_payload():
    client = RunPodProdWorkerControlClient(
        _config(),
        http_json_func=lambda *args, **kwargs: {"workers": {"agent_id": "agent-1"}},
    )

    with pytest.raises(RunPodProdWorkerControlError, match="non-list workers"):
        client.fetch_workers()
