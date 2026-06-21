from __future__ import annotations

import pytest

from ops.gpu_pool_controller.runpod_control import (
    RunPodControlClient,
    RunPodControlConfig,
    RunPodControlError,
    join_url,
    select_cloud_test_worker_ids_to_disable,
)


def _config(**overrides) -> RunPodControlConfig:
    values = {
        "central_url": "https://central.example/",
        "web_user_id": 3,
        "web_pwd_ver": 1,
        "web_bearer_token": "web-token",
        "agent_token": "agent-token",
        "jwt_channel": "runpod_canary",
    }
    values.update(overrides)
    return RunPodControlConfig(**values)


def test_web_bearer_token_takes_priority():
    client = RunPodControlClient(
        _config(web_bearer_token="explicit-token"),
        http_json_func=lambda *args, **kwargs: {},
    )

    assert client.web_token() == "explicit-token"
    assert client.web_auth_headers() == {"Authorization": "Bearer explicit-token"}


def test_web_token_falls_back_to_configured_jwt_channel(monkeypatch):
    from src.web_api.core import security

    calls: list[dict[str, object]] = []

    def fake_create_access_token(**kwargs):
        calls.append(kwargs)
        return "jwt-token"

    monkeypatch.setattr(security, "create_access_token", fake_create_access_token)
    client = RunPodControlClient(
        _config(
            web_bearer_token="",
            web_user_id=42,
            web_pwd_ver=7,
            jwt_channel="runpod_cloud_test_canary",
        ),
        http_json_func=lambda *args, **kwargs: {},
    )

    assert client.web_token() == "jwt-token"
    assert calls == [
        {"subject": "42", "pwd_ver": 7, "channel": "runpod_cloud_test_canary"}
    ]


def test_agent_control_get_and_set_use_agent_headers_and_ttl():
    calls: list[tuple[str, str, dict[str, object]]] = []

    def http_json(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"ok": True, "state": "disabled"}

    client = RunPodControlClient(_config(), http_json_func=http_json)

    assert client.get_agent_control("agent-1") == {"ok": True, "state": "disabled"}
    assert client.set_agent_control(
        "agent-1",
        "disabled",
        reason="canary",
        ttl_seconds=3600,
    ) == {"ok": True, "state": "disabled"}
    assert client.set_agent_control(
        "agent-1",
        "enabled",
        reason="restore",
        ttl_seconds=3600,
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
            "json_body": {
                "state": "disabled",
                "reason": "canary",
                "ttl_seconds": 3600,
            },
            "headers": {"Authorization": "Bearer agent-token"},
        },
    )
    assert calls[2][2]["json_body"] == {"state": "enabled", "reason": "restore"}


def test_agent_token_is_required_for_control():
    client = RunPodControlClient(
        _config(
            agent_token="",
            agent_token_required_message="AGENT_SECRET_TOKEN is required",
        ),
        http_json_func=lambda *args, **kwargs: {},
    )

    with pytest.raises(RunPodControlError, match="AGENT_SECRET_TOKEN"):
        client.get_agent_control("agent-1")


def test_fetch_workers_filters_non_dict_entries_and_rejects_non_list():
    def http_json(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://central.example/system/workers"
        assert kwargs == {}
        return {"workers": [{"agent_id": "agent-1"}, "bad", None]}

    client = RunPodControlClient(_config(), http_json_func=http_json)

    assert client.fetch_workers() == [{"agent_id": "agent-1"}]

    bad_client = RunPodControlClient(
        _config(),
        http_json_func=lambda *args, **kwargs: {"workers": {"agent_id": "agent-1"}},
    )

    with pytest.raises(RunPodControlError, match="non-list workers"):
        bad_client.fetch_workers()


def test_select_cloud_test_worker_ids_to_disable_filters_provider_and_types():
    workers = [
        {
            "agent_id": "cloud_worker_test_img",
            "provider": "local",
            "types": "img2img,img2img_lora",
        },
        {
            "agent_id": "cloud_worker_test_runpod",
            "provider": "runpod",
            "types": "img2img_lora",
        },
        {
            "agent_id": "prod_worker",
            "provider": "local",
            "types": "img2img_lora",
        },
        {
            "agent_id": "cloud_worker_test_video",
            "provider": "local",
            "types": "image_to_video",
        },
    ]

    assert select_cloud_test_worker_ids_to_disable(
        workers,
        expected_types=("img2img_lora",),
    ) == ("cloud_worker_test_img",)


def test_join_url_trims_slashes():
    assert join_url("https://central.example/", "/api/", "agent") == (
        "https://central.example/api/agent"
    )
