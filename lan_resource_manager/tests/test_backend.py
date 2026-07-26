from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from lan_resource_manager.backend.config import Settings
from lan_resource_manager.backend.main import create_app
from lan_resource_manager.backend.operator import parse_last_json
from lan_resource_manager.backend.operator import CliLanAioOperator


SLOT = {
    "id": "gpu-002-gpu1-image_to_video",
    "physical_slot_key": "gpu-002:gpu1",
    "node_id": "gpu-002",
    "gpu_index": 1,
    "host_port": 8191,
    "target_profile_id": "image_to_video",
    "target_task_types": ["image_to_video"],
    "enabled": True,
    "retargetable": True,
    "phase": "catalog_ready",
}
BLOCKED = {
    **SLOT,
    "id": "gpu-002-gpu1-wan22",
    "target_profile_id": "wan22",
    "enabled": False,
    "retargetable": False,
    "phase": "blocked_oom_32gb",
}


class FakeOperator:
    def __init__(
        self,
        *,
        current: str | None = SLOT["id"],
        state="passed",
        status_delay: float = 0,
    ):
        self.current = current
        self.state = state
        self.status_delay = status_delay
        self.executions = []
        self.status_calls = []

    async def list_slots(self):
        return {"ok": True, "slots": [SLOT, BLOCKED]}

    async def read_ledger(self):
        physical = {
            "current": (
                {
                    "slot_id": self.current,
                    "profile": "image_to_video",
                    "host_port": 8191,
                }
                if self.current
                else {}
            ),
            "cached_profiles": [
                {"profile": "image_to_video", "cache_state": "ready"}
            ],
            "blocked_observations": [],
        }
        if not self.current:
            physical["intentionally_empty"] = {"reason": "planned"}
        return {"physical_slots": {"gpu-002:gpu1": physical}}

    async def status(self, slot_id=None):
        if self.status_delay:
            await asyncio.sleep(self.status_delay)
        self.status_calls.append(slot_id)
        return {
            "ok": self.state == "passed",
            "slots": [],
            "state": {
                "status": self.state,
                "drift": [] if self.state == "passed" else [{"kind": "drift"}],
            },
        }

    async def execute_switch(self, **kwargs):
        self.executions.append(kwargs)
        await kwargs["progress"]("preflight")
        return {"ok": True}


def settings(tmp_path: Path):
    return Settings(
        allbot_root=tmp_path,
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        prod_env_file=tmp_path / "prod",
        aio_env_file=tmp_path / "aio",
        model_env_file=tmp_path / "model",
        allowed_networks=("127.0.0.0/8",),
        allowed_hosts=("testserver",),
        allowed_origins=("http://testserver",),
    )


def client(tmp_path: Path, operator: FakeOperator):
    app = create_app(settings(tmp_path), operator)
    result = TestClient(app, client=("127.0.0.1", 50000))
    result.__enter__()
    csrf = result.get("/api/v1/security/csrf").json()["csrf_token"]
    return result, {"origin": "http://testserver", "x-csrf-token": csrf}


def wait_operation(client: TestClient, operation_id: str):
    for _ in range(100):
        value = client.get(f"/api/v1/operations/{operation_id}").json()
        if value["status"] in {
            "succeeded",
            "failed",
            "rolled_back",
            "interrupted",
            "recovery_required",
        }:
            return value
        import time

        time.sleep(0.01)
    raise AssertionError("operation did not finish")


def test_fleet_merges_ledger_and_marks_only_stable_candidates_switchable(tmp_path):
    http, _ = client(tmp_path, FakeOperator())
    response = http.get("/api/v1/fleet")
    assert response.status_code == 200
    card = response.json()["physical_slots"][0]
    assert card["current"]["slot_id"] == SLOT["id"]
    assert card["candidates"][0]["cache"]["cache_state"] == "ready"
    assert card["candidates"][0]["switchable"] is False
    assert card["candidates"][1]["switchable"] is False


def test_mutations_require_origin_csrf_and_json(tmp_path):
    http, _ = client(tmp_path, FakeOperator())
    url = "/api/v1/fleet/refresh"
    assert http.post(url).status_code == 415
    assert http.post(url, json={}).status_code == 403
    assert (
        http.post(
            url,
            json={},
            headers={"origin": "http://testserver", "x-csrf-token": "wrong"},
        ).status_code
        == 403
    )


def test_requests_outside_configured_lan_are_rejected(tmp_path):
    app = create_app(settings(tmp_path), FakeOperator())
    external = TestClient(app, client=("10.20.30.40", 50000))
    assert external.get("/api/health").status_code == 403


def test_refresh_is_idempotent_and_persists_snapshot(tmp_path):
    fake = FakeOperator(status_delay=0.05)
    http, headers = client(tmp_path, fake)
    first = http.post("/api/v1/fleet/refresh", json={}, headers=headers).json()
    second = http.post("/api/v1/fleet/refresh", json={}, headers=headers).json()
    assert second["operation_id"] == first["operation_id"]
    assert wait_operation(http, first["operation_id"])["status"] == "succeeded"


def test_switch_rejects_blocked_candidate_before_background_work(tmp_path):
    fake = FakeOperator()
    http, headers = client(tmp_path, fake)
    response = http.post(
        "/api/v1/physical-slots/gpu-002/1/switches",
        json={
            "target_slot_id": BLOCKED["id"],
            "expected_current_slot_id": SLOT["id"],
            "confirmation_profile": "wan22",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_switch_blocks_when_live_state_has_drift(tmp_path):
    fake = FakeOperator(state="blocked")
    http, headers = client(tmp_path, fake)
    response = http.post(
        "/api/v1/physical-slots/gpu-002/1/switches",
        json={
            "target_slot_id": SLOT["id"],
            "expected_current_slot_id": None,
            "confirmation_profile": "image_to_video",
        },
        headers=headers,
    )
    operation = wait_operation(http, response.json()["operation_id"])
    assert operation["error_code"] == "fleet_state_blocked"
    assert fake.executions == []


def test_empty_reconciled_slot_uses_recover_shape(tmp_path):
    fake = FakeOperator(current=None)
    http, headers = client(tmp_path, fake)
    response = http.post(
        "/api/v1/physical-slots/gpu-002/1/switches",
        json={
            "target_slot_id": SLOT["id"],
            "expected_current_slot_id": None,
            "confirmation_profile": "image_to_video",
        },
        headers=headers,
    )
    assert wait_operation(http, response.json()["operation_id"])["status"] == "succeeded"
    assert fake.executions[0]["current_slot_id"] is None
    assert fake.executions[0]["physical_slot"] == "gpu-002:gpu1"


def test_operator_parser_returns_outer_final_payload_after_progress():
    payload = parse_last_json(
        '[lan-aio] step {"nested": true}\n{"ok": true, "slots": [{"id": "one"}]}\n'
    )
    assert payload == {"ok": True, "slots": [{"id": "one"}]}


def test_cli_adapter_constructs_only_transactional_switch_commands(tmp_path):
    captured = []

    class CapturingOperator(CliLanAioOperator):
        async def _run(self, action_args, **kwargs):
            captured.append(action_args)
            return {"ok": True}

    operator = CapturingOperator(settings(tmp_path))

    async def progress(stage):
        return None

    asyncio.run(
        operator.execute_switch(
            physical_slot="gpu-002:gpu1",
            target_slot_id="target",
            current_slot_id="current",
            operation_id="web-switch-one",
            progress=progress,
        )
    )
    asyncio.run(
        operator.execute_switch(
            physical_slot="gpu-002:gpu1",
            target_slot_id="target",
            current_slot_id=None,
            operation_id="web-switch-two",
            progress=progress,
        )
    )
    assert captured[0][0] == "takeover"
    assert "--failure-policy" in captured[0]
    assert "auto_rollback" in captured[0]
    assert captured[1][0] == "recover"
    assert "--physical-slot" in captured[1]
    assert "state-reconcile" not in " ".join(captured[0] + captured[1])
