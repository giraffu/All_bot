from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lan_resource_manager.backend.runner import ReleaseRunner, RunnerError


def test_runner_has_only_current_allowlisted_actions(tmp_path):
    runner = ReleaseRunner(tmp_path)
    for action in (
        "plan",
        "deploy",
        "start_build",
        "build_status",
        "plan_test_modules",
        "deploy_test_modules",
        "prepare_gpu_release",
        "sync_test_config",
        "repair_test_rollback",
        "retry_integration",
        "set_maintenance",
    ):
        with pytest.raises(RunnerError, match="unsupported_action"):
            asyncio.run(runner.dispatch(action, {}))


def test_compose_separates_web_and_runner_credentials_without_docker_socket():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "compose.yml").read_text(encoding="utf-8")
    web, runner = compose.split("  release-runner:", 1)
    assert "release-runner.sock" in web
    assert "CLOUD_DEPLOY_SSH_KEY" not in web
    assert "GITHUB_GIT_SSH_KEY" not in web
    assert "/var/run/docker.sock" not in compose
    assert "CLOUD_DEPLOY_SSH_KEY" in runner
    assert "GITHUB_GIT_SSH_KEY" in runner
    assert "All_bot-workspaces" in runner
    assert "/home/hfy/.local/state/allbot" in runner
    assert "lan-resource-manager-release-cache:/home/app/.cache/allbot" in runner


def test_runner_image_contains_release_cli_dependencies():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "docker:27.5.1-cli@sha256:" in dockerfile
    assert "cli-plugins/docker-buildx" in dockerfile
    assert "openssh-client" in dockerfile
    assert "node-runtime" in dockerfile
    assert "npm" in dockerfile
