from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from lan_resource_manager.backend.config import Settings
from lan_resource_manager.backend.main import create_app
from lan_resource_manager.backend.operator import (
    CliLanAioOperator,
    parse_last_json,
    redact_error,
)


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
    def __init__(self, *, current=SLOT["id"], state="passed"):
        self.current = current
        self.state = state
        self.executions = []

    async def list_slots(self):
        return {"ok": True, "slots": [SLOT, BLOCKED]}

    async def read_ledger(self):
        value = {
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
            value["intentionally_empty"] = {"reason": "planned"}
        return {"physical_slots": {"gpu-002:gpu1": value}}

    async def status(self, slot_id=None):
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


class MinimalReleaseOperator:
    async def catalog(self):
        return {"modules": {}}

    async def integration_status(self):
        return {
            "main_sha": "a" * 40,
            "slots": [],
            "queue": {
                "pending": [],
                "integrating": [],
                "needs-rebase": [],
                "completed": [],
            },
        }


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
    app = create_app(settings(tmp_path), operator, MinimalReleaseOperator())
    result = TestClient(app, client=("127.0.0.1", 50000))
    result.__enter__()
    csrf = result.get("/api/v1/security/csrf").json()["csrf_token"]
    return result, {"origin": "http://testserver", "x-csrf-token": csrf}


def test_redact_error_prioritizes_final_diagnostic_and_scrubs_secrets():
    rendered = '{"artifacts":"' + ("x" * 2400) + '"}\nERROR: token=secret'
    result = redact_error(rendered)
    assert result.startswith("ERROR: token=[redacted]\n")
    assert "secret" not in result


def test_fleet_merges_ledger_and_marks_only_stable_candidates_switchable(tmp_path):
    http, _ = client(tmp_path, FakeOperator())
    card = http.get("/api/v1/fleet").json()["physical_slots"][0]
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
    app = create_app(settings(tmp_path), FakeOperator(), MinimalReleaseOperator())
    external = TestClient(app, client=("10.20.30.40", 50000))
    assert external.get("/api/health").status_code == 403


def test_switch_rejects_blocked_candidate_before_background_work(tmp_path):
    http, headers = client(tmp_path, FakeOperator())
    response = http.post(
        "/api/v1/physical-slots/gpu-002/1/switches",
        headers=headers,
        json={
            "target_slot_id": BLOCKED["id"],
            "expected_current_slot_id": SLOT["id"],
            "confirmation_profile": "wan22",
        },
    )
    assert response.status_code == 422


def test_operator_parser_returns_outer_final_payload_after_progress():
    output = (
        '{"event":"progress","stage":"preflight"}\n'
        '{"ok":true,"operation":{"id":"one"}}\n'
    )
    assert parse_last_json(output)["operation"]["id"] == "one"
