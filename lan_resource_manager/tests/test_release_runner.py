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


def test_atomic_test_module_commands_require_the_exact_test_catalog(tmp_path):
    captured = []
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

    async def fake_run(command, **_kwargs):
        captured.append(command)
        return {"status": "passed", "plan_token": "safe-token"}

    runner = ReleaseRunner(tmp_path, run_json=fake_run)
    payload = {
        "modules": ["central-api", "public-web"],
        "sha": "a" * 40,
    }
    asyncio.run(runner.dispatch("plan_test_modules", payload))
    asyncio.run(
        runner.dispatch(
            "deploy_test_modules",
            {**payload, "plan_token": "safe-token"},
        )
    )

    assert captured[0][2] == "plan"
    assert captured[0].count("--modules") == 2
    assert captured[0][captured[0].index("--env") + 1] == "test"
    assert captured[1][2] == "deploy"
    assert "--execute" in captured[1]
    assert "--confirm-prod" not in captured[1]
    assert "--skip-gate" not in captured[1]

    with pytest.raises(RunnerError, match="invalid_test_modules"):
        asyncio.run(
            runner.dispatch(
                "plan_test_modules",
                {"modules": ["central-api"], "sha": "a" * 40},
            )
        )


def test_environment_status_allows_slow_read_only_remote_probe(tmp_path):
    captured = []

    async def fake_run(command, **kwargs):
        captured.append((command, kwargs))
        return {"environment": "test"}

    runner = ReleaseRunner(tmp_path, run_json=fake_run)
    result = asyncio.run(
        runner.dispatch("environment_status", {"environment": "test"})
    )
    assert result == {"environment": "test"}
    assert captured[0][1]["timeout"] == 30


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


def test_github_runs_are_filtered_without_new_cli_commit_flag(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        return (
            '[{"databaseId":1,"headSha":"'
            + "b" * 40
            + '"},{"databaseId":2,"headSha":"'
            + "a" * 40
            + '"}]'
        )

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(runner._gh_runs("workflow.yml", "a" * 40))
    assert [item["databaseId"] for item in result] == [2]
    assert "--commit" not in commands[0]


def test_candidate_resolves_main_through_authenticated_github_api(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[:3] == ["gh", "api", "repos/giraffu/All_bot/git/ref/heads/main"]:
            return "a" * 40 + "\n"
        if command[:3] == ["gh", "run", "list"]:
            return "[]"
        raise AssertionError(f"unexpected command: {command}")

    async def ready(_sha):
        return True

    async def scope(_sha):
        return "runtime"

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    runner._bundle_ready = ready
    runner._change_scope = scope
    result = asyncio.run(runner._candidate())
    assert result["main_sha"] == "a" * 40
    assert all(command[0] != "git" for command in commands)


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
    assert "GITHUB_GIT_SSH_KEY" in runner
    assert "All_bot-workspaces" in runner
    assert "/home/hfy/.local/state/allbot" in runner
    assert "GIT_AUTHOR_NAME" in runner
    assert "GIT_AUTHOR_EMAIL" in runner
    assert "GIT_COMMITTER_NAME" in runner
    assert "GIT_COMMITTER_EMAIL" in runner
    assert "TMPDIR" in runner
    assert "lan-resource-manager-release-cache:/home/app/.cache/allbot" in runner


def test_integration_actions_are_fixed_and_require_exact_confirmation(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[:3] == [
            "gh",
            "api",
            "repos/giraffu/All_bot/git/ref/heads/main",
        ]:
            return "a" * 40 + "\n"
        return '{"status":"completed"}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    with pytest.raises(RunnerError, match="confirmation_mismatch"):
        asyncio.run(
            runner.dispatch(
                "integrate_all",
                {"expected_main_sha": "a" * 40, "confirmation": "yes"},
            )
        )

    result = asyncio.run(
        runner.dispatch(
            "integrate_all",
            {
                "expected_main_sha": "a" * 40,
                "confirmation": f"INTEGRATE {'a' * 40}",
            },
        )
    )
    assert result == {"status": "completed"}
    assert any("auto_integrate_handoffs.py" in part for part in commands[-1])
    assert "--queue-root" in commands[-1]
    assert "integrate-all" in commands[-1]
    assert "--execute" in commands[-1]
    assert all("--confirm-prod" not in command for command in commands)


def test_align_workspaces_uses_only_the_fixed_manager_action(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "gh":
            return "a" * 40 + "\n"
        return '{"main_sha":"' + "a" * 40 + '","slots":[]}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner.dispatch(
            "align_workspaces",
            {
                "expected_main_sha": "a" * 40,
                "confirmation": f"ALIGN {'a' * 40}",
            },
        )
    )
    assert result["main_sha"] == "a" * 40
    assert commands[:1] == [
        [
            "gh",
            "api",
            "repos/giraffu/All_bot/git/ref/heads/main",
            "--jq",
            ".object.sha",
        ],
    ]
    assert commands[1][:2] == [
        __import__("sys").executable,
        str(tmp_path / "scripts/manage_ai_workspaces.py"),
    ]
    assert "--lock-path" in commands[1]
    assert commands[1][-1] == "align-merged"


def test_retry_integration_requeues_one_exact_batch_then_resumes(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        return '{"status":"completed"}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner.dispatch(
            "retry_integration",
            {
                "batch": "20260727-161018-68941719",
                "confirmation": "RETRY 20260727-161018-68941719",
            },
        )
    )
    assert result == {"status": "completed"}
    assert "retry-failed" in commands[0]
    assert commands[0][-2:] == ["--batch", "20260727-161018-68941719"]
    assert "integrate-all" in commands[1]
    assert "--execute" in commands[1]
    assert all("--confirm-prod" not in command for command in commands)


def test_gpu_release_build_uses_only_fixed_prepare_script_and_no_prod(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "gh":
            return "a" * 40 + "\n"
        return '{"status":"ready","production_deployed":false}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner.dispatch(
            "prepare_gpu_release",
            {
                "expected_main_sha": "a" * 40,
                "confirmation": f"GPU BUILD {'a' * 40}",
            },
        )
    )

    assert result["status"] == "ready"
    assert "prepare_gpu_release_v2.py" in commands[-1][1]
    assert "--execute" in commands[-1]
    assert all("--confirm-prod" not in command for command in commands)


def test_test_config_sync_uses_fixed_test_only_script(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "gh":
            return "a" * 40 + "\n"
        return '{"status":"applied","environment":"test","production_changed":false}'

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    result = asyncio.run(
        runner.dispatch(
            "sync_test_config",
            {
                "expected_main_sha": "a" * 40,
                "confirmation": f"TEST CONFIG {'a' * 40}",
            },
        )
    )

    assert result["environment"] == "test"
    assert "sync_test_release_config.py" in commands[-1][1]
    assert "--execute" in commands[-1]
    assert all("--confirm-prod" not in command for command in commands)


def test_test_rollback_repair_uses_release_recovery_without_runtime_mutation(tmp_path):
    commands = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "ssh":
            return (
                '{"schema_version":2,"track":"control-plane",'
                f'"git_sha":"{"b" * 40}","artifacts":{{}}}}'
            )
        return (
            '{"status":"rollback-materials-ready","environment":"test",'
            '"runtime_changed":false}'
        )

    runner = ReleaseRunner(tmp_path)
    runner._run = fake_run
    sha = "b" * 40
    result = asyncio.run(
        runner.dispatch(
            "repair_test_rollback",
            {
                "expected_current_sha": sha,
                "confirmation": f"REPAIR TEST ROLLBACK {sha}",
            },
        )
    )

    state_command, command = commands
    assert result["runtime_changed"] is False
    assert state_command[0] == "ssh"
    assert "current.json" in state_command[-1]
    assert command[command.index("--bundle-repository") + 1] == (
        "ghcr.io/giraffu/allbot-release-v2"
    )
    assert command[1].endswith("scripts/release.py")
    assert command[2:6] == ["recover", "--env", "test", "--track"]
    assert "--repair-rollback-materials" in command
    assert "--execute" in command
    assert "--modules" in command
    assert command[command.index("--modules") + 1] == "dashboard"
    assert "--confirm-prod" not in command
    assert "--state-file" in command
    assert not Path(command[command.index("--state-file") + 1]).exists()


def test_long_release_actions_have_a_bounded_eight_hour_socket_budget():
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "release_operator.py"
    ).read_text(encoding="utf-8")

    assert '"prepare_gpu_release"' in source
    assert '"retry_integration"' in source
    assert "30000" in source


def test_runner_creates_its_tmpdir_inside_the_writable_cache_volume():
    source = (
        Path(__file__).resolve().parents[1] / "backend" / "runner.py"
    ).read_text(encoding="utf-8")

    assert 'os.environ.get("TMPDIR"' in source
    assert ".mkdir(parents=True, exist_ok=True)" in source


def test_runner_image_contains_digest_pinned_node_and_npx_for_pages():
    dockerfile = (
        Path(__file__).resolve().parents[1] / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert "node:22-bookworm-slim@sha256:" in dockerfile
    assert "COPY --from=node-runtime /usr/local/bin/node" in dockerfile
    assert "npm/bin/npx-cli.js /usr/local/bin/npx" in dockerfile
    assert "NPM_CONFIG_CACHE=/home/app/.cache/allbot/npm" in dockerfile
    assert "XDG_CONFIG_HOME=/home/app/.cache/allbot/config" in dockerfile


def test_runner_ssh_retries_transient_cloud_connection_failures():
    config = (
        Path(__file__).resolve().parents[1] / "ssh_config"
    ).read_text(encoding="utf-8")

    assert "ConnectTimeout 20" in config
    assert "ConnectionAttempts 4" in config
    assert "ServerAliveInterval 20" in config
    assert "ServerAliveCountMax 3" in config
