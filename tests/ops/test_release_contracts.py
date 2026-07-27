from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from scripts import release
from scripts.release_contracts import ReleaseCommand, ReleasePlan
from scripts.release_planning import PlanValidationError, validate_v2_plan_request


FULL_SHA = "a" * 40


def test_release_command_and_plan_are_immutable_public_contracts():
    command = ReleaseCommand.from_argv(["plan", "--env", "test"])
    plan = ReleasePlan.from_legacy(
        SimpleNamespace(
            services={"web-api", "central-api"},
            level="rolling",
            requires_db_upgrade=False,
            blockers=set(),
            unknown_paths=[],
            matched_rules=["track:control-plane"],
        ),
        {
            "schema_version": 2,
            "git_sha": FULL_SHA,
            "artifacts": {"central-api": {"dependencies": ["python-runtime-base"]}},
        },
        "b" * 40,
    )

    assert command.argv == ("plan", "--env", "test")
    assert plan.services == ("central-api", "web-api")
    with pytest.raises(FrozenInstanceError):
        command.argv = ()
    with pytest.raises(TypeError):
        plan.manifest["git_sha"] = "c" * 40
    with pytest.raises(TypeError):
        plan.manifest["artifacts"]["central-api"]["dependencies"] += ("worker",)


def test_build_plan_uses_explicit_manifest_dependency_without_private_patching():
    class ExpectedBoundary(RuntimeError):
        pass

    def stop_at_manifest_resolution(*_args, **_kwargs):
        raise ExpectedBoundary

    dependencies = replace(
        release.default_release_dependencies(),
        resolve_manifest_path=stop_at_manifest_resolution,
    )

    with pytest.raises(ExpectedBoundary):
        release.build_plan(
            SimpleNamespace(sha=FULL_SHA, command="plan"),
            dependencies=dependencies,
        )


def test_v2_request_policy_is_pure_and_fail_closed():
    args = SimpleNamespace(
        modules=[],
        services=["postgres", "redis"],
        repair_test_data_services=True,
        dashboard_fast_track=False,
        control_plane_repair_fast_track=False,
        env="prod",
        track="control-plane",
        command="plan",
        from_sha=None,
    )

    with pytest.raises(PlanValidationError, match="test control-plane"):
        validate_v2_plan_request(
            args,
            split_services=lambda values: set(values),
        )


def test_cloud_target_uses_explicit_remote_shell_dependency():
    scripts: list[str] = []
    digest = "sha256:" + "7" * 64
    dependencies = replace(
        release.default_release_dependencies(),
        remote_shell=lambda _host, script, *, execute: scripts.append(script) or "",
    )
    args = SimpleNamespace(
        env="test",
        execute=False,
        command="deploy",
        execution_profile=release.ExecutionProfile("strict", ["unknown-impact"]),
        remote_host="cloud-test",
        remote_checkout_root="/release-root",
        remote_env_file="/etc/allbot/test.env",
    )

    release._deploy_cloud(
        args,
        release.ReleaseImpact(services={"central-api"}, level="rolling"),
        {
            "schema_version": 2,
            "track": "control-plane",
            "git_sha": FULL_SHA,
            "artifacts": {
                "central-api": {
                    "kind": "image",
                    "ref": f"ghcr.io/example/central@{digest}",
                    "oci_revision": FULL_SHA,
                }
            },
        },
        f"ALLBOT_CENTRAL_IMAGE=ghcr.io/example/central@{digest}\n",
        {},
        dependencies=dependencies,
    )

    assert len(scripts) == 1
    assert scripts[0].count("pull central-api") == 1
