from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lan_resource_manager.backend.config import Settings
from lan_resource_manager.backend.main import create_app
from lan_resource_manager.backend.runner import ReleaseRunner, RunnerError


SHA = "a" * 40
DIGEST_A = "ghcr.io/giraffu/a@sha256:" + "1" * 64
DIGEST_B = "ghcr.io/giraffu/b@sha256:" + "2" * 64


def _catalog(root: Path) -> None:
    (root / "deploy").mkdir(parents=True)
    (root / "deploy/module-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "modules": {
                    "central-api": {
                        "kind": "image",
                        "adapter": "compose-image",
                        "environments": ["test", "prod"],
                    },
                    "web-api": {
                        "kind": "image",
                        "adapter": "compose-image",
                        "environments": ["test", "prod"],
                    },
                    "payment-api": {
                        "kind": "image",
                        "adapter": "compose-image",
                        "environments": ["prod"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_runner_builds_only_explicit_modules_with_release_cli(tmp_path):
    _catalog(tmp_path)
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "git":
            return SHA + "\n"
        return json.dumps(
            {
                "central-api": DIGEST_A,
                "web-api": DIGEST_B,
                "python-runtime-base": "ghcr.io/base@sha256:" + "3" * 64,
            }
        )

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner.dispatch(
            "build_modules",
            {
                "sha": SHA,
                "modules": ["central-api", "web-api"],
                "confirmation": f"BUILD central-api,web-api {SHA}",
            },
        )
    )

    assert result["artifacts"] == {
        "central-api": DIGEST_A,
        "web-api": DIGEST_B,
    }
    command = commands[-1]
    assert command.count("--module") == 2
    assert "payment-api" not in command
    assert command[-2:] == ["--sha", SHA]


def test_runner_deploys_selected_modules_one_by_one_and_confirms_prod(tmp_path):
    _catalog(tmp_path)
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        return '{"status":"succeeded"}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner.dispatch(
            "deploy_modules",
            {
                "environment": "prod",
                "artifacts": {
                    "central-api": DIGEST_A,
                    "payment-api": DIGEST_B,
                },
                "confirmation": "DEPLOY PROD central-api,payment-api",
            },
        )
    )

    assert result["completed_modules"] == ["central-api", "payment-api"]
    assert len(commands) == 2
    assert all("--confirm-prod" in command for command in commands)
    assert all(command.count("--module") == 1 for command in commands)


def test_runner_limits_test_deployment_to_two_modules(tmp_path):
    _catalog(tmp_path)
    runner = ReleaseRunner(tmp_path)
    with pytest.raises(RunnerError, match="test_module_limit"):
        asyncio.run(
            runner.dispatch(
                "deploy_modules",
                {
                    "environment": "test",
                    "artifacts": {
                        "central-api": DIGEST_A,
                        "web-api": DIGEST_B,
                        "payment-api": DIGEST_A,
                    },
                    "confirmation": "DEPLOY TEST central-api,payment-api,web-api",
                },
            )
        )


def test_runner_integrates_and_aligns_only_selected_slots(tmp_path, monkeypatch):
    _catalog(tmp_path / "repo")
    commands = []
    monkeypatch.setenv("WORKSPACE_REPO_ROOT", str(tmp_path / "repo"))

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "git":
            return SHA + "\n"
        return '{"status":"completed","completed":[],"needs_rebase":[]}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    pending = {"A": ["1" * 40, "2" * 40], "C": ["3" * 40]}
    result = asyncio.run(
        runner.dispatch(
            "integrate_slots",
            {
                "expected_main_sha": SHA,
                "slots": ["A", "C"],
                "heads": pending,
                "confirmation": f"INTEGRATE A,C {SHA}",
            },
        )
    )
    assert result["status"] == "completed"
    assert commands[-1].count("--head") == 3
    assert all(digit * 40 in commands[-1] for digit in ("1", "2", "3"))

    awaitable = runner.dispatch(
        "align_slots",
        {
            "expected_main_sha": SHA,
            "slots": ["B", "D"],
            "confirmation": f"ALIGN B,D {SHA}",
        },
    )
    asyncio.run(awaitable)
    assert commands[-1][-4:] == ["--slot", "B", "--slot", "D"]


class FakeFleetOperator:
    async def list_slots(self):
        return {"ok": True, "slots": []}

    async def read_ledger(self):
        return {"physical_slots": {}}

    async def status(self, slot_id=None):
        return {"ok": True, "slots": [], "state": {"status": "passed", "drift": []}}


class FakeReleaseOperator:
    def __init__(self):
        self.build_calls = []
        self.deploy_calls = []
        self.integration_calls = []
        self.align_calls = []

    async def catalog(self):
        return {
            "modules": {
                "central-api": {
                    "adapter": "compose-image",
                    "environments": ["test", "prod"],
                },
                "web-api": {
                    "adapter": "compose-image",
                    "environments": ["test", "prod"],
                },
                "payment-api": {
                    "adapter": "compose-image",
                    "environments": ["prod"],
                },
            }
        }

    async def integration_status(self):
        return {
            "main_sha": SHA,
            "slots": [
                {"slot": "A", "clean": True, "branch": None, "head": SHA},
                {"slot": "B", "clean": True, "branch": None, "head": SHA},
            ],
            "queue": {
                "pending": [
                    {
                        "slot": "A",
                        "head": "1" * 40,
                        "branch": "codex/a-ready",
                        "status": "pending",
                    }
                ],
                "integrating": [],
                "needs-rebase": [],
                "completed": [],
            },
        }

    async def build_modules(self, **kwargs):
        self.build_calls.append(kwargs)
        return {"artifacts": {"central-api": DIGEST_A}}

    async def deploy_modules(self, **kwargs):
        self.deploy_calls.append(kwargs)
        return {"completed_modules": sorted(kwargs["artifacts"])}

    async def integrate_slots(self, **kwargs):
        self.integration_calls.append(kwargs)
        return {
            "completed": [
                head for values in kwargs["heads"].values() for head in values
            ],
            "needs_rebase": [],
        }

    async def align_slots(self, **kwargs):
        self.align_calls.append(kwargs)
        return {"slots": [{"slot": slot, "status": "aligned"} for slot in kwargs["slots"]]}


def _client(tmp_path: Path):
    settings = Settings(
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
    release = FakeReleaseOperator()
    app = create_app(settings, FakeFleetOperator(), release)
    http = TestClient(app, client=("127.0.0.1", 50000))
    http.__enter__()
    csrf = http.get("/api/v1/security/csrf").json()["csrf_token"]
    headers = {"origin": "http://testserver", "x-csrf-token": csrf}
    return http, headers, release


def test_api_exposes_scan_selected_integration_and_module_release(tmp_path):
    http, headers, release = _client(tmp_path)
    scan = http.get("/api/v1/workspaces/scan")
    assert scan.status_code == 200
    assert scan.json()["queue"]["pending"][0]["slot"] == "A"

    response = http.post(
        "/api/v1/workspaces/integrate",
        headers=headers,
        json={
            "expected_main_sha": SHA,
            "slots": ["A"],
            "confirmation": f"INTEGRATE A {SHA}",
        },
    )
    assert response.status_code == 202


def test_api_allows_prod_multi_module_and_removes_old_release_routes(tmp_path):
    http, headers, _release = _client(tmp_path)
    response = http.post(
        "/api/v1/modules/deploy",
        headers=headers,
        json={
            "environment": "prod",
            "artifacts": {
                "central-api": DIGEST_A,
                "payment-api": DIGEST_B,
            },
            "confirmation": "DEPLOY PROD central-api,payment-api",
        },
    )
    assert response.status_code == 202

    paths = http.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/releases/candidate",
        "/api/v1/releases/builds",
        "/api/v1/deployment-plans",
        "/api/v1/environments/test/deploy-all",
        "/api/v1/integration/retry",
    ):
        assert path not in paths


def test_api_exposes_module_build_and_test_deploy(tmp_path):
    http, headers, _release = _client(tmp_path / "build")
    response = http.post(
        "/api/v1/modules/build",
        headers=headers,
        json={
            "sha": SHA,
            "modules": ["central-api"],
            "confirmation": f"BUILD central-api {SHA}",
        },
    )
    assert response.status_code == 202

    http, headers, _release = _client(tmp_path / "deploy")
    response = http.post(
        "/api/v1/modules/deploy",
        headers=headers,
        json={
            "environment": "test",
            "artifacts": {"central-api": DIGEST_A},
            "confirmation": "DEPLOY TEST central-api",
        },
    )
    assert response.status_code == 202
