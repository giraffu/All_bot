from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from scripts import prompt_optimizer_worker_ops as operator

EXACT_IMAGE = "registry.example/prompt-optimizer@sha256:" + "a" * 64


def _args(tmp_path):
    env_file = tmp_path / "prompt.env"
    env_file.write_text("AGENT_SECRET_TOKEN=test\n")
    return argparse.Namespace(
        image=EXACT_IMAGE,
        env_file=str(env_file),
        model="vision-model",
        slot=operator.DEFAULT_SLOT,
        physical_slot=operator.DEFAULT_PHYSICAL_SLOT,
        operation_id="test-operation",
    )


def test_preflight_requires_exact_image_trusted_model_and_healthy_fleet(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(operator, "_model_available", lambda model: model == "vision-model")
    monkeypatch.setattr(operator, "_fleet", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        operator, "_container_state", lambda: {"Status": "running", "Running": True}
    )

    result = operator._preflight(_args(tmp_path))

    assert result["ok"] is True
    assert result["image"] == EXACT_IMAGE
    assert result["model_alias"] == "ltx-prompt-optimizer"


def test_physical_slot_uses_fleet_key_format():
    assert operator.DEFAULT_PHYSICAL_SLOT == "gpu-115:gpu0"


def test_wait_lanes_authenticates_system_workers(monkeypatch):
    observed = {}

    def fake_json_url(url, *, method="GET", headers=None):
        observed.update(url=url, method=method, headers=headers)
        return {
            "workers": [
                {
                    "agent_id": agent_id,
                    "status": "idle",
                    "current_task_id": None,
                    "provider": "lmstudio",
                }
                for agent_id in operator.LANE_IDS
            ]
        }

    monkeypatch.setattr(operator, "_json_url", fake_json_url)

    lanes = operator._wait_lanes(agent_token="test-agent-token", deadline_seconds=1)

    assert len(lanes) == 4
    assert observed["headers"]["Authorization"] == "Bearer test-agent-token"


def test_stop_optimizer_does_not_remove_other_compose_services(monkeypatch):
    compose_calls = []
    monkeypatch.setattr(
        operator,
        "_compose",
        lambda image, env_file, *args: compose_calls.append(args),
    )
    monkeypatch.setattr(operator, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator, "_model_alias_loaded", lambda alias: False)

    operator._stop_optimizer(EXACT_IMAGE, "/tmp/prompt.env", stop_server=False)

    assert compose_calls == [("down",)]


def test_prompt_optimizer_compose_has_an_isolated_project_name():
    compose = (
        Path(operator.__file__).resolve().parents[1]
        / "deploy/docker-compose-prompt-optimizer-test.yml"
    ).read_text(encoding="utf-8")

    assert compose.startswith("name: allbot-prompt-optimizer-test\n")


def test_takeover_failure_after_fleet_stop_restores_original_slot(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(
        operator,
        "_preflight",
        lambda _args: {
            "ok": True,
            "image": EXACT_IMAGE,
            "env_file": str(tmp_path / "prompt.env"),
        },
    )
    monkeypatch.setattr(operator, "_server_running", lambda: False)
    events = []

    def fake_fleet(action, **kwargs):
        events.append((action, kwargs.get("physical_slot")))
        return {"ok": True, "action": action}

    monkeypatch.setattr(operator, "_fleet", fake_fleet)
    monkeypatch.setattr(operator, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator, "_compose", lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(operator, "_stop_optimizer", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator, "_write_state", lambda payload: None)

    with pytest.raises(RuntimeError, match="recovery=succeeded"):
        operator._takeover(args)

    assert events == [
        ("canary-stop-disabled", None),
        ("recover", operator.DEFAULT_PHYSICAL_SLOT),
    ]


def test_takeover_skips_canary_stop_when_fleet_reports_slot_already_stopped(
    tmp_path, monkeypatch
):
    args = _args(tmp_path)
    monkeypatch.setattr(
        operator,
        "_preflight",
        lambda _args: {
            "ok": True,
            "image": EXACT_IMAGE,
            "env_file": str(tmp_path / "prompt.env"),
            "fleet": {
                "state": {
                    "live_observations": {
                        operator.DEFAULT_PHYSICAL_SLOT: [
                            {
                                "slot_id": operator.DEFAULT_SLOT,
                                "exists": True,
                                "running": False,
                            }
                        ]
                    }
                }
            },
        },
    )
    monkeypatch.setattr(operator, "_server_running", lambda: True)
    fleet_actions = []
    monkeypatch.setattr(
        operator,
        "_fleet",
        lambda action, **kwargs: fleet_actions.append(action)
        or {"ok": True, "action": action},
    )
    monkeypatch.setattr(operator, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(operator, "_compose", lambda *args: None)
    monkeypatch.setattr(operator, "_wait_ready", lambda: {"ready": True})
    monkeypatch.setattr(operator, "_wait_lanes", lambda **kwargs: [])
    monkeypatch.setattr(operator, "_env_value", lambda *args: "test-token")
    monkeypatch.setattr(operator, "_write_state", lambda payload: None)

    result = operator._takeover(args)

    assert result["ok"] is True
    assert fleet_actions == []
    assert result["steps"][1] == {
        "action": "stop-image-worker",
        "payload": {
            "ok": True,
            "action": "canary-stop-disabled",
            "slot": operator.DEFAULT_SLOT,
            "already_stopped": True,
        },
    }


def test_recover_drains_optimizer_before_stopping_and_restoring_fleet(monkeypatch):
    events = []
    monkeypatch.setattr(
        operator,
        "_read_state",
        lambda: {
            "status": "optimizer_active",
            "image": EXACT_IMAGE,
            "env_file": "/tmp/prompt.env",
            "server_was_running": False,
            "slot": operator.DEFAULT_SLOT,
            "physical_slot": operator.DEFAULT_PHYSICAL_SLOT,
        },
    )
    monkeypatch.setattr(
        operator, "_wait_drained", lambda: events.append("drained") or {"active_lanes": 0}
    )
    monkeypatch.setattr(
        operator,
        "_stop_optimizer",
        lambda *args, **kwargs: events.append("optimizer-stopped"),
    )
    monkeypatch.setattr(
        operator,
        "_fleet",
        lambda *args, **kwargs: events.append("fleet-restored") or {"ok": True},
    )
    monkeypatch.setattr(operator, "_write_state", lambda payload: None)
    args = argparse.Namespace(operation_id="recover-operation")

    result = operator._recover(args)

    assert result["ok"] is True
    assert events == ["drained", "optimizer-stopped", "fleet-restored"]


def test_retire_stops_optimizer_without_restoring_intentionally_empty_fleet(
    monkeypatch,
):
    events = []
    written = []
    monkeypatch.setattr(
        operator,
        "_read_state",
        lambda: {
            "status": "optimizer_active",
            "image": EXACT_IMAGE,
            "env_file": "/tmp/prompt.env",
            "server_was_running": True,
            "slot": operator.DEFAULT_SLOT,
            "physical_slot": operator.DEFAULT_PHYSICAL_SLOT,
        },
    )
    monkeypatch.setattr(
        operator,
        "_fleet",
        lambda *args, **kwargs: {
            "ok": True,
            "state": {
                "live_current": {operator.DEFAULT_PHYSICAL_SLOT: None},
                "ledger_current": {operator.DEFAULT_PHYSICAL_SLOT: None},
                "live_observations": {
                    operator.DEFAULT_PHYSICAL_SLOT: [
                        {
                            "slot_id": operator.DEFAULT_SLOT,
                            "exists": True,
                            "running": False,
                        }
                    ]
                },
            },
        },
    )
    monkeypatch.setattr(
        operator,
        "_wait_drained",
        lambda: events.append("drained") or {"active_lanes": 0},
    )
    monkeypatch.setattr(
        operator,
        "_stop_optimizer",
        lambda *args, **kwargs: events.append(
            ("optimizer-stopped", kwargs["stop_server"])
        ),
    )
    monkeypatch.setattr(operator, "_write_state", written.append)

    result = operator._retire(argparse.Namespace(operation_id="retire-operation"))

    assert result["ok"] is True
    assert result["action"] == "retire"
    assert events == ["drained", ("optimizer-stopped", False)]
    assert written[0]["status"] == "optimizer_retired"
    assert written[0]["retirement_operation_id"] == "retire-operation"


def test_retire_refuses_to_change_optimizer_when_fleet_is_not_empty(monkeypatch):
    monkeypatch.setattr(
        operator,
        "_read_state",
        lambda: {
            "status": "optimizer_active",
            "slot": operator.DEFAULT_SLOT,
            "physical_slot": operator.DEFAULT_PHYSICAL_SLOT,
        },
    )
    monkeypatch.setattr(
        operator,
        "_fleet",
        lambda *args, **kwargs: {
            "ok": True,
            "state": {
                "live_current": {operator.DEFAULT_PHYSICAL_SLOT: operator.DEFAULT_SLOT},
                "ledger_current": {operator.DEFAULT_PHYSICAL_SLOT: None},
                "live_observations": {},
            },
        },
    )

    with pytest.raises(RuntimeError, match="not intentionally empty"):
        operator._retire(argparse.Namespace(operation_id="retire-operation"))
