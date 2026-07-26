from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lan_resource_manager.backend.runner import ReleaseRunner, RunnerError


def test_runner_rejects_unknown_actions(tmp_path):
    runner = ReleaseRunner(tmp_path)
    with pytest.raises(RunnerError, match="unsupported_action"):
        asyncio.run(runner.dispatch("shell", {"command": "id"}))


def test_catalog_comes_from_policy_and_filters_prod_only_modules(tmp_path):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/release-policy.yml").write_text(
        """
{"independent_modules": {
  "central-api": {"artifacts": ["central-api"]},
  "dashboard": {"artifacts": ["dashboard-backend", "dashboard-frontend"]},
  "public-web": {"artifacts": ["public-web"]}
}}
""",
        encoding="utf-8",
    )
    result = asyncio.run(ReleaseRunner(tmp_path).dispatch("catalog", {}))
    assert result["environments"]["test"]["modules"] == [
        "central-api",
        "public-web",
    ]
    assert "dashboard" in result["environments"]["prod"]["modules"]


def test_plan_and_deploy_commands_are_fixed(tmp_path):
    captured = []
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/release-policy.yml").write_text(
        '{"independent_modules":{"central-api":{"artifacts":["central-api"]}}}',
        encoding="utf-8",
    )

    async def fake_run(command, **_kwargs):
        captured.append(command)
        return {
            "status": "passed",
            "plan_token": "token",
            "plan_token_expires_at": "2099-01-01T00:00:00+00:00",
        }

    runner = ReleaseRunner(tmp_path, run_json=fake_run)
    asyncio.run(
        runner.dispatch(
            "plan",
            {
                "environment": "prod",
                "module": "central-api",
                "sha": "a" * 40,
                "maintenance": "planner",
            },
        )
    )
    asyncio.run(
        runner.dispatch(
            "deploy",
            {
                "environment": "prod",
                "module": "central-api",
                "sha": "a" * 40,
                "maintenance": "rolling",
                "plan_token": "safe-token",
                "confirm_prod": True,
            },
        )
    )
    assert captured[0][1:4] == [
        str(tmp_path / "scripts/release.py"),
        "plan",
        "--env",
    ]
    deploy = captured[1]
    assert "--execute" in deploy
    assert "--confirm-prod" in deploy
    assert "--no-maintenance" in deploy
    assert "--skip-gate" not in deploy
    assert "--services" not in deploy


def test_deploy_rejects_non_catalog_module_before_subprocess(tmp_path):
    runner = ReleaseRunner(tmp_path)
    with pytest.raises(RunnerError, match="invalid_module"):
        asyncio.run(
            runner.dispatch(
                "deploy",
                {
                    "environment": "prod",
                    "module": "../../shell",
                    "sha": "a" * 40,
                    "maintenance": "planner",
                    "plan_token": "token",
                    "confirm_prod": True,
                },
            )
        )


def test_successful_ci_dispatches_only_full_modular_bundle(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        return ""

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner._start_build(
            "a" * 40,
            {
                "build": None,
                "ci": {
                    "databaseId": 314,
                    "status": "completed",
                    "conclusion": "success",
                },
            },
        )
    )
    assert result == {"run_id": None, "status": "queued", "reused": False}
    assert commands == [
        [
            "gh",
            "workflow",
            "run",
            "modular-release-v2.yml",
            "--ref",
            "main",
            "-f",
            f"source_sha={'a' * 40}",
            "-f",
            "release_channel=main",
            "-f",
            "validation_mode=full",
            "-f",
            "upstream_run_id=314",
        ]
    ]
    assert "build-only" not in commands[0]


def test_latest_bundle_follows_main_history(tmp_path):
    async def fake_run(command, **_kwargs):
        if command[:3] == ["oras", "repo", "tags"]:
            return f"{'b' * 40}\n{'c' * 40}\n"
        return f"{'a' * 40}\n{'b' * 40}\n{'c' * 40}\n"

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(runner._latest_deployable_sha("a" * 40))
    assert result == "b" * 40


def test_compose_separates_web_and_runner_credentials():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "compose.yml").read_text(encoding="utf-8")
    web, runner = compose.split("  release-runner:", 1)
    assert "release-runner.sock" in web
    assert "CLOUD_DEPLOY_SSH_KEY" not in web
    assert "GITHUB_ACTIONS_TOKEN" not in web
    assert "/var/run/docker.sock" not in compose
    assert "CLOUD_DEPLOY_SSH_KEY" in runner
    assert "GITHUB_ACTIONS_TOKEN" in runner
