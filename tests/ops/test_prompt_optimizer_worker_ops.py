from __future__ import annotations

import argparse

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
