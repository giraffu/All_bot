from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from lan_resource_manager.backend.config import Settings
from lan_resource_manager.backend.main import create_app
from lan_resource_manager.backend.operator import parse_last_json
from lan_resource_manager.backend.operator import CliLanAioOperator
from lan_resource_manager.backend.operator import redact_error
from lan_resource_manager.backend.store import OperationStore


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


def test_redact_error_prioritizes_final_diagnostic_for_long_output():
    rendered = '{"artifacts":"' + ("x" * 2400) + '"}\nERROR: remote state timed out'

    result = redact_error(rendered)

    assert result.startswith("ERROR: remote state timed out\n")
    assert len(result) <= 2000


def test_redact_error_scrubs_secrets_before_selecting_tail():
    rendered = ("x" * 2400) + "\nERROR: token=super-secret-value"

    result = redact_error(rendered)

    assert result.startswith("ERROR: token=[redacted]\n")
    assert "super-secret-value" not in result
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


class FakeReleaseOperator:
    def __init__(self):
        self.builds = []
        self.gpu_builds = []
        self.test_config_syncs = []
        self.test_rollback_repairs = []
        self.plans = []
        self.test_module_plans = []
        self.executions = []
        self.test_module_executions = []
        self.maintenance_calls = []
        self.integration_calls = []
        self.integration_retry_calls = []
        self.align_calls = []

    async def catalog(self):
        return {
            "environments": {
                "test": {"modules": ["central-api", "web-api", "main-bot"]},
                "prod": {
                    "modules": [
                        "central-api",
                        "web-api",
                        "main-bot",
                        "dashboard",
                    ]
                },
            },
            "modules": {
                "central-api": {"artifacts": ["central-api"]},
                "web-api": {"artifacts": ["web-api"]},
                "main-bot": {"artifacts": ["main-bot"]},
                "dashboard": {
                    "artifacts": ["dashboard-backend", "dashboard-frontend"]
                },
            },
        }

    async def candidate(self):
        return {
            "main_sha": "a" * 40,
            "deployable_sha": "a" * 40,
            "scope": "runtime",
            "ci": {"status": "completed", "conclusion": "success", "run_id": 41},
            "bundle": {"status": "ready"},
            "build": None,
            "blockers": [],
        }

    async def environment_status(self, environment):
        return {
            "environment": environment,
            "current_sha": "b" * 40,
            "maintenance": {
                "enabled": False,
                "owner": None,
                "can_disable": False,
            },
            "active_transaction": None,
            "config_drift": False,
        }

    async def start_build(self, expected_main_sha):
        self.builds.append(expected_main_sha)
        return {"run_id": 42, "status": "queued", "reused": False}

    async def prepare_gpu_release(self, **kwargs):
        self.gpu_builds.append(kwargs)
        return {
            "status": "ready",
            "source_sha": kwargs["expected_main_sha"],
            "production_deployed": False,
        }

    async def sync_test_config(self, **kwargs):
        self.test_config_syncs.append(kwargs)
        return {
            "status": "applied",
            "source_sha": kwargs["expected_main_sha"],
            "environment": "test",
            "production_changed": False,
        }

    async def repair_test_rollback(self, **kwargs):
        self.test_rollback_repairs.append(kwargs)
        return {
            "status": "rollback-materials-ready",
            "git_sha": kwargs["expected_current_sha"],
            "environment": "test",
            "runtime_changed": False,
        }

    async def build_status(self, sha):
        return {
            "sha": sha,
            "ci": {"status": "completed", "conclusion": "success"},
            "build": {"status": "completed", "conclusion": "success"},
            "bundle": {"status": "ready"},
        }

    async def plan(self, environment, module, sha, maintenance):
        self.plans.append((environment, module, sha, maintenance))
        return {
            "status": "passed",
            "git_sha": sha,
            "modules": [module],
            "artifacts": {module: {"digest": "sha256:" + "c" * 64}},
            "maintenance_required": module == "main-bot",
            "blockers": [],
            "plan_token": "server-secret-plan-token",
            "plan_token_expires_at": "2099-01-01T00:00:00+00:00",
        }

    async def deploy(self, **kwargs):
        self.executions.append(kwargs)
        return {"status": "succeeded"}

    async def plan_test_modules(self, modules, sha):
        self.test_module_plans.append((modules, sha))
        return {
            "status": "passed",
            "git_sha": sha,
            "modules": modules,
            "plan_token": "server-secret-plan-token",
        }

    async def deploy_test_modules(self, **kwargs):
        self.test_module_executions.append(kwargs)
        return {"status": "succeeded"}

    async def set_maintenance(self, **kwargs):
        self.maintenance_calls.append(kwargs)
        return {
            "environment": kwargs["environment"],
            "maintenance": {
                "enabled": kwargs["enabled"],
                "owner": "lan-resource-manager" if kwargs["enabled"] else None,
                "can_disable": kwargs["enabled"],
            },
        }

    async def integration_status(self):
        return {
            "main_sha": "a" * 40,
            "queue": {
                "pending": [{"head": "c" * 40, "branch": "codex/a-task"}],
                "running": [],
                "failed": [],
            },
            "slots": [
                {
                    "slot": "A",
                    "branch": None,
                    "head": "a" * 40,
                    "clean": True,
                    "at_base": True,
                }
            ],
        }

    async def integrate_all(self, **kwargs):
        self.integration_calls.append(kwargs)
        return {"status": "completed", "batches": []}

    async def retry_integration(self, **kwargs):
        self.integration_retry_calls.append(kwargs)
        return {"status": "completed", "batch": kwargs["batch"]}

    async def align_workspaces(self, **kwargs):
        self.align_calls.append(kwargs)
        return {"main_sha": kwargs["expected_main_sha"], "slots": []}


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


def client(
    tmp_path: Path,
    operator: FakeOperator,
    release_operator: FakeReleaseOperator | None = None,
):
    app = create_app(settings(tmp_path), operator, release_operator)
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


def test_operator_parser_accepts_diagnostic_after_final_payload():
    payload = parse_last_json(
        '{"status": "deployed", "details": {"sha": "abc"}}\n'
        "[ssh-retry] connection closed after command completion\n"
    )

    assert payload == {"status": "deployed", "details": {"sha": "abc"}}


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


def test_deployment_catalog_and_environment_status_are_exposed(tmp_path):
    http, _ = client(tmp_path, FakeOperator(), FakeReleaseOperator())
    catalog = http.get("/api/v1/deployments/catalog").json()
    assert "dashboard" not in catalog["environments"]["test"]["modules"]
    assert "dashboard" in catalog["environments"]["prod"]["modules"]
    status = http.get("/api/v1/environments/test/status").json()
    assert status["maintenance"]["enabled"] is False


def test_deployment_plan_keeps_operator_token_server_side(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    response = http.post(
        "/api/v1/deployment-plans",
        json={
            "environment": "test",
            "module": "central-api",
            "candidate_sha": "a" * 40,
            "maintenance": "planner",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.headers["x-request-id"].startswith("lrm-")
    payload = response.json()
    assert "plan_token" not in payload
    assert payload["candidate_sha"] == "a" * 40
    stored = (
        tmp_path / "data" / "deployment-plans" / f"{payload['plan_id']}.json"
    ).read_text()
    assert "server-secret-plan-token" in stored
    assert '"source_ip": "127.0.0.1"' in stored
    assert '"request_id": "lrm-' in stored


def test_deployment_execute_requires_exact_confirmation(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    plan = http.post(
        "/api/v1/deployment-plans",
        json={
            "environment": "prod",
            "module": "central-api",
            "candidate_sha": "a" * 40,
            "maintenance": "planner",
        },
        headers=headers,
    ).json()
    bad = http.post(
        f"/api/v1/deployment-plans/{plan['plan_id']}/execute",
        json={"confirmation": "wrong"},
        headers=headers,
    )
    assert bad.status_code == 422
    expected = f"PROD central-api {'a' * 40}"
    accepted = http.post(
        f"/api/v1/deployment-plans/{plan['plan_id']}/execute",
        json={"confirmation": expected},
        headers=headers,
    )
    assert accepted.status_code == 202
    operation = wait_operation(http, accepted.json()["operation_id"])
    assert operation["status"] == "succeeded"
    assert release.executions[0]["confirm_prod"] is True


def test_build_rejects_stale_main_and_accepts_exact_confirmation(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    stale = http.post(
        "/api/v1/releases/builds",
        json={"expected_main_sha": "b" * 40, "confirmation": f"BUILD {'b' * 40}"},
        headers=headers,
    )
    assert stale.status_code == 409
    accepted = http.post(
        "/api/v1/releases/builds",
        json={"expected_main_sha": "a" * 40, "confirmation": f"BUILD {'a' * 40}"},
        headers=headers,
    )
    assert accepted.status_code == 202
    assert wait_operation(http, accepted.json()["operation_id"])["status"] == "succeeded"
    assert release.builds == ["a" * 40]


def test_maintenance_uses_expected_state_and_confirmation(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    response = http.post(
        "/api/v1/environments/test/maintenance",
        json={
            "enabled": True,
            "expected_enabled": False,
            "reason": "release window",
            "confirmation": "TEST MAINTENANCE ON",
        },
        headers=headers,
    )
    assert response.status_code == 202
    assert wait_operation(http, response.json()["operation_id"])["status"] == "succeeded"
    assert release.maintenance_calls[0]["reason"] == "release window"


def test_integration_status_and_mutations_are_exposed_with_exact_confirmation(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    status = http.get("/api/v1/integration/status")
    assert status.status_code == 200
    assert status.json()["queue"]["pending"][0]["branch"] == "codex/a-task"

    bad = http.post(
        "/api/v1/integration/run",
        json={"expected_main_sha": "a" * 40, "confirmation": "yes"},
        headers=headers,
    )
    assert bad.status_code == 422
    accepted = http.post(
        "/api/v1/integration/run",
        json={
            "expected_main_sha": "a" * 40,
            "confirmation": f"INTEGRATE {'a' * 40}",
        },
        headers=headers,
    )
    assert accepted.status_code == 202
    assert wait_operation(http, accepted.json()["operation_id"])["status"] == "succeeded"
    assert release.integration_calls[0]["expected_main_sha"] == "a" * 40

    aligned = http.post(
        "/api/v1/workspaces/align",
        json={
            "expected_main_sha": "a" * 40,
            "confirmation": f"ALIGN {'a' * 40}",
        },
        headers=headers,
    )
    assert aligned.status_code == 202
    assert wait_operation(http, aligned.json()["operation_id"])["status"] == "succeeded"


def test_gpu_release_build_prepares_artifacts_without_prod_deployment(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    sha = "a" * 40
    bad = http.post(
        "/api/v1/releases/gpu-builds",
        json={"expected_main_sha": sha, "confirmation": "yes"},
        headers=headers,
    )
    assert bad.status_code == 422
    accepted = http.post(
        "/api/v1/releases/gpu-builds",
        json={
            "expected_main_sha": sha,
            "confirmation": f"GPU BUILD {sha}",
        },
        headers=headers,
    )
    assert accepted.status_code == 202
    operation = wait_operation(http, accepted.json()["operation_id"])
    assert operation["status"] == "succeeded"
    assert operation["result"]["production_deployed"] is False
    assert release.gpu_builds == [
        {
            "expected_main_sha": sha,
            "confirmation": f"GPU BUILD {sha}",
        }
    ]


def test_test_config_sync_is_exact_sha_and_never_targets_prod(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    sha = "a" * 40
    accepted = http.post(
        "/api/v1/environments/test/config-sync",
        json={
            "expected_main_sha": sha,
            "confirmation": f"TEST CONFIG {sha}",
        },
        headers=headers,
    )

    assert accepted.status_code == 202
    operation = wait_operation(http, accepted.json()["operation_id"])
    assert operation["status"] == "succeeded"
    assert operation["result"]["environment"] == "test"
    assert operation["result"]["production_changed"] is False
    assert release.test_config_syncs == [
        {
            "expected_main_sha": sha,
            "confirmation": f"TEST CONFIG {sha}",
        }
    ]


def test_test_rollback_repair_is_bound_to_live_test_sha(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    current_sha = "b" * 40
    stale = http.post(
        "/api/v1/environments/test/rollback-repair",
        json={
            "expected_current_sha": "a" * 40,
            "confirmation": f"REPAIR TEST ROLLBACK {'a' * 40}",
        },
        headers=headers,
    )
    assert stale.status_code == 409

    accepted = http.post(
        "/api/v1/environments/test/rollback-repair",
        json={
            "expected_current_sha": current_sha,
            "confirmation": f"REPAIR TEST ROLLBACK {current_sha}",
        },
        headers=headers,
    )
    assert accepted.status_code == 202
    operation = wait_operation(http, accepted.json()["operation_id"])
    assert operation["status"] == "succeeded"
    assert operation["result"]["environment"] == "test"
    assert operation["result"]["runtime_changed"] is False
    assert release.test_rollback_repairs == [
        {
            "expected_current_sha": current_sha,
            "confirmation": f"REPAIR TEST ROLLBACK {current_sha}",
        }
    ]


def test_failed_integration_batch_can_be_retried_with_exact_confirmation(tmp_path):
    release = FakeReleaseOperator()
    release.integration_status = lambda: None

    async def failed_status():
        return {
            "main_sha": "a" * 40,
            "queue": {
                "pending": [],
                "running": [],
                "failed": [{"id": "20260727-161018-68941719"}],
            },
            "slots": [],
        }

    release.integration_status = failed_status
    http, headers = client(tmp_path, FakeOperator(), release)
    batch = "20260727-161018-68941719"
    bad = http.post(
        "/api/v1/integration/retry",
        json={"batch": batch, "confirmation": "RETRY something-else"},
        headers=headers,
    )
    assert bad.status_code == 422
    accepted = http.post(
        "/api/v1/integration/retry",
        json={"batch": batch, "confirmation": f"RETRY {batch}"},
        headers=headers,
    )
    assert accepted.status_code == 202
    operation = wait_operation(http, accepted.json()["operation_id"])
    assert operation["status"] == "succeeded"
    assert release.integration_retry_calls == [
        {"batch": batch, "confirmation": f"RETRY {batch}"}
    ]


def test_deploy_all_test_modules_runs_one_atomic_catalog_release_without_prod(tmp_path):
    release = FakeReleaseOperator()
    http, headers = client(tmp_path, FakeOperator(), release)
    response = http.post(
        "/api/v1/environments/test/deploy-all",
        json={
            "candidate_sha": "a" * 40,
            "confirmation": f"TEST ALL {'a' * 40}",
        },
        headers=headers,
    )
    assert response.status_code == 202
    operation = wait_operation(http, response.json()["operation_id"])
    assert operation["status"] == "succeeded"
    assert release.test_module_plans == [
        (["central-api", "web-api", "main-bot"], "a" * 40)
    ]
    assert release.test_module_executions == [
        {
            "modules": ["central-api", "web-api", "main-bot"],
            "sha": "a" * 40,
            "plan_token": "server-secret-plan-token",
        }
    ]
    assert release.plans == []
    assert release.executions == []
    assert operation["result"]["completed_modules"] == [
        "central-api",
        "web-api",
        "main-bot",
    ]


def test_restart_resumes_build_observation_but_interrupts_runtime_mutation(tmp_path):
    store = OperationStore(tmp_path)
    store.create("build-one", kind="build", request={"sha": "a" * 40})
    store.update("build-one", status="running", external_run_id=42)
    store.create("deploy-one", kind="deploy", request={"sha": "a" * 40})
    store.update("deploy-one", status="running")

    restarted = OperationStore(tmp_path)

    assert restarted.get("build-one")["status"] == "queued"
    assert restarted.get("build-one")["external_run_id"] == 42
    assert restarted.get("deploy-one")["status"] == "interrupted"
