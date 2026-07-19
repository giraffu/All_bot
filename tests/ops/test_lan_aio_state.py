from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ops.gpu_pool_controller.lan_aio_prod import (
    LanAioProdOps,
    _select_action_slots,
    build_parser,
)
from ops.gpu_pool_controller.lan_aio_state import (
    LanAioStateStore,
    StateDriftError,
    assess_state_drift,
    default_lan_aio_state_dir,
)


def test_default_state_dir_uses_xdg_then_local_state(tmp_path: Path):
    xdg_root = tmp_path / "xdg-state"

    assert (
        default_lan_aio_state_dir(
            environ={"XDG_STATE_HOME": str(xdg_root)}, home=tmp_path / "home"
        )
        == xdg_root / "allbot" / "lan-aio"
    )
    assert (
        default_lan_aio_state_dir(environ={}, home=tmp_path / "home")
        == tmp_path / "home" / ".local" / "state" / "allbot" / "lan-aio"
    )


def test_store_atomically_writes_current_and_operation_history(tmp_path: Path):
    store = LanAioStateStore(tmp_path / "state")
    operation_id = "20260717T120000Z-takeover-gpu252-gpu0"

    store.begin_operation(
        operation_id,
        action="takeover",
        physical_slots=["gpu-252:gpu0"],
        request={"target_slot": "gpu-252-gpu0-image_to_video"},
    )
    store.write_current(
        {
            "catalog_sha256": "a" * 64,
            "physical_slots": {
                "gpu-252:gpu0": {
                    "current": {
                        "slot_id": "gpu-252-gpu0-image_to_video",
                        "profile": "image_to_video",
                    }
                }
            },
        },
        operation_id=operation_id,
    )
    store.finish_operation(
        operation_id,
        status="succeeded",
        result={"verified": True},
    )

    current = yaml.safe_load((tmp_path / "state" / "current.yml").read_text())
    history = json.loads(
        (tmp_path / "state" / "history" / f"{operation_id}.json").read_text()
    )
    assert current["version"] == 1
    assert current["last_operation_id"] == operation_id
    assert current["physical_slots"]["gpu-252:gpu0"]["current"]["slot_id"] == (
        "gpu-252-gpu0-image_to_video"
    )
    assert history["status"] == "succeeded"
    assert history["request"]["target_slot"] == "gpu-252-gpu0-image_to_video"
    assert not list((tmp_path / "state").rglob("*.tmp"))


def test_store_keeps_failed_operation_audit_without_changing_current(tmp_path: Path):
    store = LanAioStateStore(tmp_path / "state")
    operation_id = "failed-takeover"

    store.begin_operation(
        operation_id,
        action="takeover",
        physical_slots=["gpu-226:gpu0"],
        request={"target_slot": "gpu-226-gpu0-scail2"},
    )
    store.finish_operation(
        operation_id,
        status="rolled_back",
        result={"recovery_status": "succeeded"},
        error="candidate failed health validation",
    )

    history = json.loads(
        (tmp_path / "state" / "history" / f"{operation_id}.json").read_text()
    )
    assert history["status"] == "rolled_back"
    assert history["error"] == "candidate failed health validation"
    assert not (tmp_path / "state" / "current.yml").exists()


def test_assess_state_drift_requires_live_ledger_and_catalog_to_agree():
    ledger = {
        "catalog_sha256": "a" * 64,
        "physical_slots": {
            "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
        },
    }

    report = assess_state_drift(
        live_current={"gpu-252:gpu0": "gpu-252-gpu0-image_to_video"},
        ledger=ledger,
        catalog_slot_ids={
            "gpu-252-gpu0-i2i_pro",
            "gpu-252-gpu0-image_to_video",
        },
        catalog_sha256="a" * 64,
    )

    assert report["status"] == "blocked"
    assert report["drift"] == [
        {
            "physical_slot": "gpu-252:gpu0",
            "kind": "live_ledger_mismatch",
            "live_slot": "gpu-252-gpu0-image_to_video",
            "ledger_slot": "gpu-252-gpu0-i2i_pro",
        }
    ]
    with pytest.raises(StateDriftError, match="live_ledger_mismatch"):
        LanAioStateStore.assert_mutation_allowed(report)


def test_assess_state_drift_blocks_missing_live_and_catalog_revision_change():
    ledger = {
        "catalog_sha256": "a" * 64,
        "physical_slots": {
            "gpu-177:gpu0": {"current": {"slot_id": "gpu-177-gpu0-wan22_video_v2"}}
        },
    }

    report = assess_state_drift(
        live_current={"gpu-177:gpu0": None},
        live_errors={"gpu-177:gpu0": "ssh unavailable"},
        ledger=ledger,
        catalog_slot_ids={"gpu-177-gpu0-wan22_video_v2"},
        catalog_sha256="b" * 64,
    )

    assert report["status"] == "blocked"
    assert {item["kind"] for item in report["drift"]} == {
        "catalog_revision_mismatch",
        "live_unavailable",
    }


def test_migrate_legacy_state_preserves_current_cache_and_block_observations(
    tmp_path: Path,
):
    legacy = {
        "version": 1,
        "nodes": {
            "gpu-252": {
                "physical_gpus": [
                    {
                        "gpu_index": 0,
                        "current": {
                            "slot_id": "gpu-252-gpu0-i2i_pro",
                            "profile": "i2i_pro",
                            "last_verified_at": "2026-07-16T18:51:05Z",
                        },
                        "cached_profiles": [
                            {"profile": "i2i_pro", "cache_state": "ready"}
                        ],
                        "blocked_profiles": [
                            {"profile": "wan22_video_v2", "reason": "blocked_oom"}
                        ],
                    }
                ]
            }
        },
    }
    store = LanAioStateStore(tmp_path / "state")

    migrated = store.migrate_legacy_state(
        legacy,
        catalog_sha256="c" * 64,
        operation_id="bootstrap-legacy-state",
    )

    physical = migrated["physical_slots"]["gpu-252:gpu0"]
    assert physical["current"]["slot_id"] == "gpu-252-gpu0-i2i_pro"
    assert physical["cached_profiles"] == [
        {"profile": "i2i_pro", "cache_state": "ready"}
    ]
    assert physical["blocked_observations"] == [
        {"profile": "wan22_video_v2", "reason": "blocked_oom"}
    ]


def test_managed_takeover_updates_local_current_only_after_live_verification(
    tmp_path: Path,
):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )
            self.live_slot = "gpu-252-gpu0-i2i_pro"

        def live_current_snapshot(self, physical_slots):
            return {
                "current": {
                    physical_slot: self.live_slot for physical_slot in physical_slots
                },
                "errors": {},
                "observations": {},
            }

    ops = RecordingOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {
                    "current": {
                        "slot_id": "gpu-252-gpu0-i2i_pro",
                        "profile": "i2i_pro",
                    }
                }
            },
        },
        operation_id="bootstrap",
    )
    target = ops.slots["gpu-252-gpu0-image_to_video"]

    def execute():
        ops.live_slot = target.id
        return {"ok": True, "action": "takeover", "slot": target.id}

    result = ops.execute_managed_mutation(
        action="takeover",
        slots=[target],
        operation_id="takeover-success",
        execute=execute,
    )

    assert result["operation_id"] == "takeover-success"
    current = ops.state_store.load_current()
    assert current is not None
    assert current["physical_slots"]["gpu-252:gpu0"]["current"]["slot_id"] == (
        target.id
    )
    history = json.loads(
        (tmp_path / "state" / "history" / "takeover-success.json").read_text()
    )
    assert history["status"] == "succeeded"


def test_managed_mutation_blocks_before_handler_when_live_has_drift(tmp_path: Path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )

        def live_current_snapshot(self, physical_slots):
            return {
                "current": {"gpu-252:gpu0": "gpu-252-gpu0-image_to_video"},
                "errors": {},
                "observations": {},
            }

    ops = RecordingOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
            },
        },
        operation_id="bootstrap",
    )
    called = False

    def execute():
        nonlocal called
        called = True
        return {"ok": True}

    with pytest.raises(StateDriftError, match="live_ledger_mismatch"):
        ops.execute_managed_mutation(
            action="warm-cache",
            slots=[ops.slots["gpu-252-gpu0-image_to_video"]],
            operation_id="blocked-mutation",
            execute=execute,
        )

    assert called is False
    assert not (tmp_path / "state" / "history" / "blocked-mutation.json").exists()


def test_managed_recover_can_restore_a_missing_current_runtime(tmp_path: Path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )
            self.live_calls = 0

        def live_current_snapshot(self, physical_slots):
            self.live_calls += 1
            current = (
                None
                if self.live_calls == 1
                else "gpu-252-gpu0-image_to_video"
            )
            return {
                "current": {"gpu-252:gpu0": current},
                "errors": {},
                "observations": {},
            }

    ops = RecordingOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": "0" * 64,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
            },
        },
        operation_id="bootstrap",
    )
    target = ops.slots["gpu-252-gpu0-image_to_video"]

    result = ops.execute_managed_mutation(
        action="recover",
        slots=[ops.slots["gpu-252-gpu0-i2i_pro"]],
        operation_id="recover-missing-runtime",
        execute=lambda: {
            "ok": True,
            "selected_slot": target.id,
            "recovery_status": "succeeded",
        },
    )

    assert result["selected_slot"] == target.id
    current = ops.state_store.load_current()
    assert current is not None
    assert current["catalog_sha256"] == ops.catalog_sha256
    assert current["physical_slots"]["gpu-252:gpu0"]["current"]["slot_id"] == (
        target.id
    )


def test_managed_recover_still_blocks_when_live_is_unavailable(tmp_path: Path):
    class UnreachableOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )

        def live_current_snapshot(self, physical_slots):
            return {
                "current": {"gpu-252:gpu0": None},
                "errors": {"gpu-252:gpu0": "ssh unavailable"},
                "observations": {},
            }

    ops = UnreachableOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
            },
        },
        operation_id="bootstrap",
    )

    with pytest.raises(StateDriftError, match="live_unavailable"):
        ops.execute_managed_mutation(
            action="recover",
            slots=[ops.slots["gpu-252-gpu0-i2i_pro"]],
            operation_id="recover-unreachable-runtime",
            execute=lambda: pytest.fail("unreachable target must not execute"),
        )


def test_managed_mutation_records_rolled_back_failure(tmp_path: Path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )

        def live_current_snapshot(self, physical_slots):
            return {
                "current": {"gpu-252:gpu0": "gpu-252-gpu0-i2i_pro"},
                "errors": {},
                "observations": {},
            }

    ops = RecordingOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
            },
        },
        operation_id="bootstrap",
    )

    def execute():
        raise RuntimeError("candidate failed; recovery_status=succeeded")

    with pytest.raises(RuntimeError, match="recovery_status=succeeded"):
        ops.execute_managed_mutation(
            action="takeover",
            slots=[ops.slots["gpu-252-gpu0-image_to_video"]],
            operation_id="takeover-rolled-back",
            execute=execute,
        )

    history = json.loads(
        (tmp_path / "state" / "history" / "takeover-rolled-back.json").read_text()
    )
    assert history["status"] == "rolled_back"


def test_takeover_retargets_from_local_ledger_not_git_enabled_flags(tmp_path: Path):
    ops = LanAioProdOps(
        config_root=None,
        prod_env_file=Path(".env.cloud.prod.missing"),
        aio_env_file=Path(".env.lan-aio-prod.missing"),
        model_env_file=Path(".env.lan.model-cache.missing"),
        state_dir=tmp_path / "state",
    )
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-image_to_video"}}
            },
        },
        operation_id="bootstrap",
    )
    args = build_parser().parse_args(
        [
            "takeover",
            "--slot",
            "gpu-252-gpu0-i2i_pro",
            "--include-disabled",
            "--execute",
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )

    selected = _select_action_slots(args, ops)

    assert len(selected) == 1
    assert selected[0].id == "gpu-252-gpu0-i2i_pro"
    assert selected[0].legacy_worker_id == (
        "lan_aio_prod_gpu252_gpu0_image_to_video_01"
    )
    assert selected[0].old_runtime_container == (
        "allbot-lan-aio-gpu-252-gpu0-image_to_video-prod"
    )


def test_dashboard_style_control_action_must_target_ledger_current(tmp_path: Path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )

        def live_current_snapshot(self, physical_slots):
            return {
                "current": {"gpu-252:gpu0": "gpu-252-gpu0-i2i_pro"},
                "errors": {},
                "observations": {},
            }

    ops = RecordingOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": ops.catalog_sha256,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
            },
        },
        operation_id="bootstrap",
    )

    with pytest.raises(StateDriftError, match="target is not current"):
        ops.execute_managed_mutation(
            action="restart-aio",
            slots=[ops.slots["gpu-252-gpu0-image_to_video"]],
            operation_id="wrong-restart-target",
            execute=lambda: pytest.fail("wrong target must not execute"),
        )


def test_state_reconcile_explicitly_supersedes_unfinished_operation(tmp_path: Path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )

        def live_current_snapshot(self, physical_slots):
            return {
                "current": {"gpu-252:gpu0": "gpu-252-gpu0-image_to_video"},
                "errors": {},
                "observations": {},
            }

    ops = RecordingOps()
    ops.state_store.write_current(
        {
            "catalog_sha256": "0" * 64,
            "physical_slots": {
                "gpu-252:gpu0": {"current": {"slot_id": "gpu-252-gpu0-i2i_pro"}}
            },
        },
        operation_id="bootstrap",
    )
    ops.state_store.begin_operation(
        "interrupted-takeover",
        action="takeover",
        physical_slots=["gpu-252:gpu0"],
        request={"target_slot": "gpu-252-gpu0-image_to_video"},
    )

    result = ops.reconcile_state_from_live(
        operation_id="reconcile-after-inspection",
        reason="operator confirmed image_to_video is the only healthy live runtime",
    )

    assert result["ok"] is True
    interrupted = json.loads(
        (tmp_path / "state" / "history" / "interrupted-takeover.json").read_text()
    )
    assert interrupted["status"] == "failed"
    assert "superseded by reconcile-after-inspection" in interrupted["error"]
    current = ops.state_store.load_current()
    assert current is not None
    assert current["physical_slots"]["gpu-252:gpu0"]["current"]["slot_id"] == (
        "gpu-252-gpu0-image_to_video"
    )


def test_live_snapshot_requires_container_and_matching_central_worker(tmp_path: Path):
    class RecordingOps(LanAioProdOps):
        def __init__(self):
            super().__init__(
                config_root=None,
                prod_env_file=Path(".env.cloud.prod.missing"),
                aio_env_file=Path(".env.lan-aio-prod.missing"),
                model_env_file=Path(".env.lan.model-cache.missing"),
                state_dir=tmp_path / "state",
            )

        def _remote_target_container_state(self, slot):
            return {
                "exists": slot.id == "gpu-252-gpu0-i2i_pro",
                "name": slot.container_name,
                "status": (
                    "running" if slot.id == "gpu-252-gpu0-i2i_pro" else "missing"
                ),
                "running": slot.id == "gpu-252-gpu0-i2i_pro",
            }

        def _system_workers(self):
            slot = self.slots["gpu-252-gpu0-i2i_pro"]
            return [
                {
                    "agent_id": slot.agent_id,
                    "node_id": slot.node_id,
                    "provider": "lan_ssh",
                    "runtime_profile": "wrong-profile",
                    "pool_managed": True,
                }
            ]

    snapshot = RecordingOps().live_current_snapshot({"gpu-252:gpu0"})

    assert snapshot["current"]["gpu-252:gpu0"] is None
    assert "Central worker metadata mismatch" in snapshot["errors"]["gpu-252:gpu0"]
