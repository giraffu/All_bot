import json
import signal

import pytest
from fastapi import HTTPException

from dashboard.backend.schemas import (
    RunPodScaleItem,
    RunPodScaleRequest,
    RunPodWorkerActionRequest,
)
from dashboard.backend.services.runpod_operation_store import (
    InMemoryRunPodOperationStore,
    RedisRunPodOperationStore,
)
from dashboard.backend.services import runpod_admin_service
from dashboard.backend.services.runpod_admin_commands import (
    RUNPOD_RELEASE_PROFILE_IMAGE_ENVS,
)


@pytest.fixture(autouse=True)
def _clear_runpod_admin_operations(monkeypatch):
    pins = {
        image_env: f"ghcr.io/giraffu/profile-{index}@sha256:" + str(index) * 64
        for index, image_env in enumerate(
            sorted(RUNPOD_RELEASE_PROFILE_IMAGE_ENVS),
            start=1,
        )
    }
    monkeypatch.setenv("RUNPOD_RELEASE_PROFILE_PINS_JSON", json.dumps(pins))
    monkeypatch.setenv(
        "RUNPOD_ASSET_CONTRACT_VERIFIED_PROFILES",
        "img2img,image_to_video,wan22_video_v2,i2i_pro,scail2,ltx_video,ltx_t2v,minimax_h3,pornmaster_flux2_edit_bf16",
    )
    runpod_admin_service.set_runpod_operation_store_for_tests(
        InMemoryRunPodOperationStore()
    )
    runpod_admin_service._operations.clear()
    runpod_admin_service._operation_runner.create_subprocess_exec = None
    runpod_admin_service._operation_runner.kill_process_group = None

    async def plan_slots(*, count, excluded_slots, **_kwargs):
        excluded = set(excluded_slots)
        slots = [f"{index:02d}" for index in range(1, 101)]
        return [slot for slot in slots if slot not in excluded][:count]

    monkeypatch.setattr(runpod_admin_service, "_manual_add_plan_func", plan_slots)
    yield
    runpod_admin_service._operations.clear()
    runpod_admin_service._operation_runner.create_subprocess_exec = None
    runpod_admin_service._operation_runner.kill_process_group = None
    runpod_admin_service.set_runpod_operation_store_for_tests(
        InMemoryRunPodOperationStore()
    )


@pytest.mark.asyncio
async def test_profiles_and_scale_fail_closed_to_asset_contract_allowlist(monkeypatch):
    monkeypatch.setenv(
        "RUNPOD_ASSET_CONTRACT_VERIFIED_PROFILES",
        "img2img,pornmaster_flux2_edit_bf16",
    )

    payload = await runpod_admin_service.get_runpod_profiles_payload()
    assert [item["profile"] for item in payload["profiles"]] == [
        "img2img", "pornmaster_flux2_edit_bf16"
    ]

    request = RunPodScaleRequest(items=[RunPodScaleItem(profile="image_to_video", count=1)])
    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.start_runpod_scale_payload(request)
    assert exc_info.value.status_code == 409
    assert "asset-contract canary" in exc_info.value.detail

    with pytest.raises(HTTPException) as enable_error:
        await runpod_admin_service.enable_runpod_worker_payload(
            "runpod_prod_image_to_video_manual_01",
            RunPodWorkerActionRequest(),
        )
    assert enable_error.value.status_code == 409


def _discard_operation_coroutine(coro):
    coro.close()
    return None


class _FakeStdout:
    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines]

    async def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProcess:
    def __init__(self, *, pid=12345, exit_code=0, lines=None):
        self.pid = pid
        self.stdout = _FakeStdout(lines or [])
        self._exit_code = exit_code
        self.terminated = False

    def terminate(self):
        self.terminated = True

    async def wait(self):
        return self._exit_code


class _ReservationRedis:
    def __init__(self):
        self.strings = {}
        self.hashes = {}

    async def eval(self, script, key_count, *args):
        keys = list(args[:key_count])
        argv = list(args[key_count:])
        if 'redis.call("hlen", KEYS[2])' in script:
            if self.hashes.get(keys[1]) or keys[0] in self.strings:
                return 0
            self.strings[keys[0]] = argv[0]
            return 1
        if 'redis.call("hexists", KEYS[2]' in script:
            if keys[0] in self.strings:
                return 0
            active = self.hashes.setdefault(keys[1], {})
            reservations = dict(zip(argv[::2], argv[1::2]))
            if any(slot in active for slot in reservations):
                return 0
            active.update(reservations)
            return 1
        if 'redis.call("hget", KEYS[1]' in script:
            active = self.hashes.setdefault(keys[0], {})
            if active.get(argv[0]) == argv[1]:
                active.pop(argv[0], None)
                return 1
            return 0
        raise AssertionError("unexpected Redis script")

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


@pytest.mark.asyncio
async def test_runpod_profiles_payload_lists_supported_prod_profiles():
    payload = await runpod_admin_service.get_runpod_profiles_payload()

    assert [item["profile"] for item in payload["profiles"]] == [
        "img2img",
        "image_to_video",
        "wan22_video_v2",
        "i2i_pro",
        "scail2",
        "ltx_video",
        "ltx_t2v",
        "minimax_h3",
        "pornmaster_flux2_edit_bf16",
    ]
    assert payload["profiles"][0]["supported_task_types"] == [
        "img2img",
        "img2img_lora",
    ]
    ltx_t2v = next(item for item in payload["profiles"] if item["profile"] == "ltx_t2v")
    assert ltx_t2v["supported_task_types"] == ["ltx_t2v", "ltx_t2v_ic"]
    assert ltx_t2v["autoscaler_enabled"] is False
    minimax_h3 = next(
        item for item in payload["profiles"] if item["profile"] == "minimax_h3"
    )
    assert minimax_h3["supported_task_types"] == [
        "minimax_h3_t2v",
        "minimax_h3_i2v",
        "minimax_h3_flf2v",
        "minimax_h3_ref2v",
    ]
    assert minimax_h3.get("autoscaler_enabled", True) is True
    pornmaster_bf16 = payload["profiles"][-1]
    assert pornmaster_bf16["label"] == (
        "pornmaster_flux2 BF16 / 自由P图 v2.5 + v3 共用执行池"
    )
    assert pornmaster_bf16["supported_task_types"] == [
        "character_reference_build",
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_multi_edit_bf16",
    ]
    assert pornmaster_bf16.get("autoscaler_enabled", True) is True


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_creates_retrying_operations():
    payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img_lora", count=2),
                RunPodScaleItem(profile="wan22_video_v2", count=1),
            ],
            max_attempts=100,
            retry_interval_seconds=30,
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    assert payload["status"] == "accepted"
    assert [operation["profile"] for operation in payload["operations"]] == [
        "img2img",
        "img2img",
        "wan22_video_v2",
    ]
    command = payload["operations"][0]["command"]
    assert "add" in command
    assert command[command.index("--profile") + 1] == "img2img"
    assert command[command.index("--count") + 1] == "1"
    assert command[command.index("--slot") + 1] == "01"
    assert "--desired" not in command
    assert "--retry-unavailable" in command
    assert command[command.index("--max-attempts") + 1] == "100"
    assert command[command.index("--retry-interval") + 1] == "30"
    assert "--execute" in command
    assert payload["operations"][0]["action"] == "add"
    assert payload["operations"][0]["requested_count"] == 1
    assert payload["operations"][1]["slot"] == "02"
    assert payload["operations"][0]["batch_id"] == payload["batch_id"]
    assert "desired_count" not in payload["operations"][0]


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_accepts_i2i_pro_profile():
    payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[RunPodScaleItem(profile="i2i_pro", count=1)],
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    assert payload["status"] == "accepted"
    assert len(payload["operations"]) == 1
    operation = payload["operations"][0]
    assert operation["profile"] == "i2i_pro"
    assert operation["slot"] == "01"
    assert operation["agent_id"] == "runpod_prod_i2i_pro_manual_01"
    command = operation["command"]
    assert "add" in command
    assert command[command.index("--profile") + 1] == "i2i_pro"
    assert command[command.index("--slot") + 1] == "01"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_treats_legacy_desired_as_add_count():
    payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img_lora", desired_count=1),
            ],
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    command = payload["operations"][0]["command"]
    assert "add" in command
    assert "--desired" not in command
    assert command[command.index("--count") + 1] == "1"
    assert payload["operations"][0]["requested_count"] == 1


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_rejects_duplicate_profiles():
    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.start_runpod_scale_payload(
            RunPodScaleRequest(
                items=[
                    RunPodScaleItem(profile="img2img", desired_count=1),
                    RunPodScaleItem(profile="img2img_lora", desired_count=2),
                ],
            ),
            spawn_task_func=_discard_operation_coroutine,
        )

    assert exc_info.value.status_code == 422
    assert "duplicate profile" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_allows_overlapping_manual_profile_adds():
    first_payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img", count=1),
            ],
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    second_payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img_lora", count=1),
            ],
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    assert first_payload["operations"][0]["status"] == "pending"
    assert first_payload["operations"][0]["slot"] == "01"
    assert second_payload["operations"][0]["slot"] == "02"


@pytest.mark.asyncio
async def test_runpod_operation_store_fake_create_list_update_prune_and_lock():
    store = InMemoryRunPodOperationStore()
    await store.save_operation(
        {"id": "op-1", "status": "pending"},
        created_at=1.0,
    )
    await store.save_operation(
        {"id": "op-2", "status": "running"},
        created_at=2.0,
    )

    assert [item["id"] for item in await store.list_operations(limit=10)] == [
        "op-2",
        "op-1",
    ]
    await store.save_operation(
        {"id": "op-1", "status": "succeeded"},
        created_at=1.0,
        ttl_seconds=60,
    )
    assert (await store.get_operation("op-1"))["status"] == "succeeded"

    assert await store.acquire_active_add("img2img", "op-2") is True
    assert await store.acquire_active_add("img2img", "op-3") is False
    assert await store.get_active_add("img2img") == "op-2"
    await store.release_active_add("img2img", "op-other")
    assert await store.get_active_add("img2img") == "op-2"
    await store.release_active_add("img2img", "op-2")
    assert await store.get_active_add("img2img") is None

    assert (
        await store.reserve_manual_add_slots(
            "img2img", {"03": "manual-op-3", "04": "manual-op-4"}
        )
        is True
    )
    assert await store.list_manual_add_slots("img2img") == {
        "03": "manual-op-3",
        "04": "manual-op-4",
    }
    assert await store.reserve_manual_add_slots("img2img", {"04": "other-op"}) is False
    assert await store.acquire_active_add("img2img", "auto-op") is False
    await store.release_manual_add_slot("img2img", "03", "wrong-op")
    assert "03" in await store.list_manual_add_slots("img2img")
    await store.release_manual_add_slot("img2img", "03", "manual-op-3")
    await store.release_manual_add_slot("img2img", "04", "manual-op-4")
    assert await store.list_manual_add_slots("img2img") == {}

    assert await store.acquire_active_add("img2img", "auto-op") is True
    assert (
        await store.reserve_manual_add_slots("img2img", {"05": "manual-op-5"}) is False
    )
    await store.release_active_add("img2img", "auto-op")

    assert await store.acquire_active_lan_aio_slot("gpu-252:gpu0", "op-2") is True
    assert await store.acquire_active_lan_aio_slot("gpu-252:gpu0", "op-3") is False
    assert await store.get_active_lan_aio_slot("gpu-252:gpu0") == "op-2"
    await store.release_active_lan_aio_slot("gpu-252:gpu0", "op-other")
    assert await store.get_active_lan_aio_slot("gpu-252:gpu0") == "op-2"
    await store.release_active_lan_aio_slot("gpu-252:gpu0", "op-2")
    assert await store.get_active_lan_aio_slot("gpu-252:gpu0") is None

    lock_payload = {
        "agent_id": "runpod_prod_wan22_video_v2_manual_03",
        "profile": "wan22_video_v2",
        "slot": "03",
        "locked": True,
    }
    await store.set_locked_runpod_worker(lock_payload["agent_id"], lock_payload)
    assert (
        await store.get_locked_runpod_worker(lock_payload["agent_id"]) == lock_payload
    )
    assert await store.list_locked_runpod_workers() == {
        lock_payload["agent_id"]: lock_payload
    }
    await store.clear_locked_runpod_worker(lock_payload["agent_id"])
    assert await store.get_locked_runpod_worker(lock_payload["agent_id"]) is None

    await store.prune_operations(max_records=1)
    assert [item["id"] for item in await store.list_operations(limit=10)] == ["op-2"]


@pytest.mark.asyncio
async def test_redis_operation_store_manual_slots_are_atomic_with_autoscaler_lock():
    store = RedisRunPodOperationStore(_ReservationRedis())

    assert (
        await store.reserve_manual_add_slots(
            "img2img", {"01": "manual-1", "02": "manual-2"}
        )
        is True
    )
    assert (
        await store.reserve_manual_add_slots("img2img", {"02": "manual-other"}) is False
    )
    assert await store.acquire_active_add("img2img", "autoscaler") is False
    assert await store.list_manual_add_slots("img2img") == {
        "01": "manual-1",
        "02": "manual-2",
    }

    await store.release_manual_add_slot("img2img", "01", "wrong")
    await store.release_manual_add_slot("img2img", "01", "manual-1")
    await store.release_manual_add_slot("img2img", "02", "manual-2")

    assert await store.acquire_active_add("img2img", "autoscaler") is True
    assert await store.reserve_manual_add_slots("img2img", {"03": "manual-3"}) is False


@pytest.mark.asyncio
async def test_runpod_operations_payload_reads_persisted_store_records():
    store = InMemoryRunPodOperationStore()
    runpod_admin_service.set_runpod_operation_store_for_tests(store)
    await store.save_operation(
        {
            "id": "detached-op",
            "action": "add",
            "profile": "img2img",
            "owner_id": "old-host:1:abc",
            "attached": True,
            "status": "running",
            "terminate_requested": False,
            "can_terminate": True,
            "log_tail": [],
            "command": ["bash", "scripts/runpod_prod_ops.sh", "add"],
        },
        created_at=1.0,
    )

    payload = await runpod_admin_service.get_runpod_operations_payload(
        workers_payload={"workers": []}
    )

    assert payload["count"] == 1
    operation = payload["operations"][0]
    assert operation["id"] == "detached-op"
    assert operation["owner_id"] == "old-host:1:abc"
    assert operation["attached"] is False
    assert operation["can_terminate"] is False
    assert "detached" in operation["can_terminate_reason"]


@pytest.mark.asyncio
async def test_runpod_operations_payload_uses_worker_snapshot_to_finish_detached_add():
    store = InMemoryRunPodOperationStore()
    runpod_admin_service.set_runpod_operation_store_for_tests(store)
    await store.save_operation(
        {
            "id": "detached-ready-op",
            "action": "add",
            "profile": "img2img",
            "owner_id": "old-host:1:abc",
            "status": "running",
            "terminate_requested": False,
            "requested_count": 1,
            "cleanup_slots": ["02"],
            "log_tail": [],
            "command": [],
        },
        created_at=1.0,
    )

    payload = await runpod_admin_service.get_runpod_operations_payload(
        workers_payload={
            "workers": [
                {
                    "agent_id": "runpod_prod_img2img_manual_02",
                    "provider": "runpod",
                    "status": "idle",
                    "control_state": "enabled",
                    "last_seen": 995.0,
                }
            ]
        },
        now=1000.0,
    )

    assert payload["operations"][0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_rejects_active_add_from_store():
    store = InMemoryRunPodOperationStore()
    runpod_admin_service.set_runpod_operation_store_for_tests(store)
    await store.save_operation(
        {
            "id": "store-op",
            "action": "add",
            "profile": "img2img",
            "owner_id": "old-host:1:abc",
            "status": "running",
            "terminate_requested": False,
            "log_tail": [],
            "command": [],
        },
        created_at=1.0,
    )
    await store.acquire_active_add("img2img", "store-op")

    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.start_runpod_scale_payload(
            RunPodScaleRequest(
                items=[
                    RunPodScaleItem(profile="img2img", count=1),
                ],
            ),
            spawn_task_func=_discard_operation_coroutine,
        )

    assert exc_info.value.status_code == 409
    assert "store-op" in exc_info.value.detail


@pytest.mark.asyncio
async def test_pause_restart_and_delete_runpod_worker_build_slot_scoped_operations():
    action_request = RunPodWorkerActionRequest(prod_max_manual_slots=4)

    pause_payload = await runpod_admin_service.pause_runpod_worker_payload(
        agent_id="runpod_prod_wan22_video_v2_manual_03",
        request=action_request,
        spawn_task_func=_discard_operation_coroutine,
    )
    restart_payload = await runpod_admin_service.restart_runpod_worker_payload(
        agent_id="runpod_prod_wan22_video_v2_manual_03",
        request=action_request,
        spawn_task_func=_discard_operation_coroutine,
    )
    delete_payload = await runpod_admin_service.delete_runpod_worker_payload(
        agent_id="runpod_prod_wan22_video_v2_manual_03",
        request=action_request,
        spawn_task_func=_discard_operation_coroutine,
    )

    pause_command = pause_payload["operation"]["command"]
    restart_command = restart_payload["operation"]["command"]
    delete_command = delete_payload["operation"]["command"]
    assert "disable" in pause_command
    assert "restart" in restart_command
    assert "down" in delete_command
    assert pause_command[pause_command.index("--profile") + 1] == "wan22_video_v2"
    assert pause_command[pause_command.index("--slot") + 1] == "03"
    assert restart_command[restart_command.index("--profile") + 1] == "wan22_video_v2"
    assert restart_command[restart_command.index("--slot") + 1] == "03"
    assert delete_command[delete_command.index("--slot") + 1] == "03"
    assert pause_payload["operation"]["status"] == "pending"
    assert restart_payload["operation"]["action"] == "restart"
    assert delete_payload["operation"]["status"] == "pending"


@pytest.mark.asyncio
async def test_lock_runpod_worker_marks_payload_and_blocks_deletes():
    agent_id = "runpod_prod_wan22_video_v2_manual_03"

    lock_payload = await runpod_admin_service.lock_runpod_worker_payload(
        agent_id=agent_id,
        request=RunPodWorkerActionRequest(reason="pin expensive pod"),
    )

    assert lock_payload["status"] == "locked"
    assert lock_payload["worker"]["agent_id"] == agent_id
    assert lock_payload["worker"]["profile"] == "wan22_video_v2"
    assert lock_payload["worker"]["slot"] == "03"
    assert lock_payload["worker"]["locked"] is True
    assert lock_payload["worker"]["reason"] == "pin expensive pod"

    workers_payload = await runpod_admin_service.annotate_runpod_worker_locks_payload(
        {
            "workers": [
                {"agent_id": agent_id, "provider": "runpod"},
                {
                    "agent_id": "runpod_prod_wan22_video_v2_manual_04",
                    "provider": "runpod",
                },
            ]
        }
    )
    assert workers_payload["workers"][0]["runpod_locked"] is True
    assert workers_payload["workers"][0]["runpod_lock"]["slot"] == "03"
    assert workers_payload["workers"][1]["runpod_locked"] is False

    with pytest.raises(HTTPException) as manual_exc:
        await runpod_admin_service.delete_runpod_worker_payload(
            agent_id=agent_id,
            request=RunPodWorkerActionRequest(),
            spawn_task_func=_discard_operation_coroutine,
        )
    assert manual_exc.value.status_code == 409
    assert "unlock before deleting" in manual_exc.value.detail

    with pytest.raises(HTTPException) as autoscaler_exc:
        await runpod_admin_service.start_runpod_autoscaler_delete_operation(
            profile="wan22_video_v2",
            slot="03",
            trigger_reason="scale_down: no backlog and idle runpod available",
            spawn_task_func=_discard_operation_coroutine,
        )
    assert autoscaler_exc.value.status_code == 409

    unlock_payload = await runpod_admin_service.unlock_runpod_worker_payload(
        agent_id=agent_id,
        request=RunPodWorkerActionRequest(),
    )
    assert unlock_payload["status"] == "unlocked"
    assert unlock_payload["worker"]["locked"] is False

    delete_payload = await runpod_admin_service.delete_runpod_worker_payload(
        agent_id=agent_id,
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )
    assert delete_payload["operation"]["action"] == "delete"


@pytest.mark.asyncio
async def test_enable_runpod_worker_builds_slot_scoped_operation():
    payload = await runpod_admin_service.enable_runpod_worker_payload(
        agent_id="runpod_prod_wan22_video_v2_manual_03",
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )

    operation = payload["operation"]
    command = operation["command"]
    assert operation["status"] == "pending"
    assert operation["action"] == "enable"
    assert operation["profile"] == "wan22_video_v2"
    assert operation["slot"] == "03"
    assert "enable" in command
    assert command[command.index("--profile") + 1] == "wan22_video_v2"
    assert command[command.index("--slot") + 1] == "03"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_autoscaler_recovery_operations_build_slot_scoped_operations():
    restart_operation = (
        await runpod_admin_service.start_runpod_autoscaler_restart_operation(
            profile="scail2",
            slot="01",
            agent_id="runpod_prod_scail2_manual_01",
            trigger_reason="restart: runpod fault persisted 350s",
            spawn_task_func=_discard_operation_coroutine,
        )
    )
    enable_operation = (
        await runpod_admin_service.start_runpod_autoscaler_enable_operation(
            profile="image_to_video",
            slot="03",
            agent_id="runpod_prod_image_to_video_manual_03",
            trigger_reason="enable: runpod paused worker available",
            spawn_task_func=_discard_operation_coroutine,
        )
    )

    restart_command = restart_operation.command
    enable_command = enable_operation.command
    assert restart_operation.action == "restart"
    assert restart_operation.source == "autoscaler"
    assert restart_operation.trigger_reason == "restart: runpod fault persisted 350s"
    assert restart_operation.agent_id == "runpod_prod_scail2_manual_01"
    assert restart_operation.slot == "01"
    assert "restart" in restart_command
    assert restart_command[restart_command.index("--profile") + 1] == "scail2"
    assert restart_command[restart_command.index("--slot") + 1] == "01"
    assert "--execute" in restart_command
    assert enable_operation.action == "enable"
    assert enable_operation.source == "autoscaler"
    assert enable_operation.trigger_reason == "enable: runpod paused worker available"
    assert enable_operation.agent_id == "runpod_prod_image_to_video_manual_03"
    assert enable_operation.slot == "03"
    assert "enable" in enable_command
    assert enable_command[enable_command.index("--profile") + 1] == "image_to_video"
    assert enable_command[enable_command.index("--slot") + 1] == "03"
    assert "--execute" in enable_command


@pytest.mark.asyncio
async def test_autoscaler_add_operation_uses_bootstrap_timeout():
    operation = await runpod_admin_service.start_runpod_autoscaler_add_operation(
        profile="img2img",
        trigger_reason=(
            "scale_up: estimated non-low-trust clear time 1300s exceeds 1200s"
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    command = operation.command
    assert operation.action == "add"
    assert command[command.index("--worker-timeout") + 1] == "2400"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_restart_lan_aio_worker_builds_slot_scoped_operation():
    payload = await runpod_admin_service.restart_lan_aio_worker_payload(
        agent_id="lan_aio_prod_gpu177_gpu0_wan22_video_v2_01",
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )

    operation = payload["operation"]
    command = operation["command"]
    assert operation["status"] == "pending"
    assert operation["action"] == "restart"
    assert operation["profile"] == "wan22_video_v2"
    assert operation["slot"] == "gpu-177-gpu0-wan22_video_v2"
    assert command[:3] == [
        "python3",
        str(
            runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"
        ),
        "restart-aio",
    ]
    assert command[command.index("--slot") + 1] == "gpu-177-gpu0-wan22_video_v2"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_pause_and_enable_lan_aio_worker_build_slot_scoped_operations():
    pause_payload = await runpod_admin_service.pause_lan_aio_worker_payload(
        agent_id="lan_aio_prod_gpu177_gpu0_wan22_video_v2_01",
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )
    enable_payload = await runpod_admin_service.enable_lan_aio_worker_payload(
        agent_id="lan_aio_prod_gpu177_gpu0_wan22_video_v2_01",
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )

    pause_operation = pause_payload["operation"]
    enable_operation = enable_payload["operation"]
    pause_command = pause_operation["command"]
    enable_command = enable_operation["command"]
    assert pause_operation["status"] == "pending"
    assert pause_operation["action"] == "pause"
    assert pause_operation["profile"] == "wan22_video_v2"
    assert pause_operation["slot"] == "gpu-177-gpu0-wan22_video_v2"
    assert pause_command[:3] == [
        "python3",
        str(
            runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"
        ),
        "disable-aio",
    ]
    assert (
        pause_command[pause_command.index("--slot") + 1]
        == "gpu-177-gpu0-wan22_video_v2"
    )
    assert "--execute" in pause_command
    assert enable_operation["action"] == "enable"
    assert enable_operation["profile"] == "wan22_video_v2"
    assert enable_operation["slot"] == "gpu-177-gpu0-wan22_video_v2"
    assert enable_command[:3] == [
        "python3",
        str(
            runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"
        ),
        "enable-aio",
    ]
    assert (
        enable_command[enable_command.index("--slot") + 1]
        == "gpu-177-gpu0-wan22_video_v2"
    )
    assert "--execute" in enable_command


@pytest.mark.asyncio
async def test_restart_lan_aio_worker_rejects_unknown_agent():
    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.restart_lan_aio_worker_payload(
            agent_id="lan_aio_prod_unknown_01",
            request=RunPodWorkerActionRequest(),
            spawn_task_func=_discard_operation_coroutine,
        )

    assert exc_info.value.status_code == 422
    assert "unsupported LAN AIO worker" in exc_info.value.detail


def test_runpod_operation_log_records_created_slots_for_cleanup():
    operation = runpod_admin_service.RunPodAdminOperation(
        id="op-1",
        action="add",
        profile="wan22_video_v2",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
    )

    runpod_admin_service._append_log(
        operation,
        "[runpod-prod-worker] runpod_create_pod_03: running",
    )
    runpod_admin_service._append_log(
        operation,
        "[runpod-prod-worker] runpod_create_pod_03: ok",
    )

    assert operation.cleanup_slots == ["03"]
    payload = runpod_admin_service._operation_payload(operation)
    assert payload["cleanup_slots"] == ["03"]


@pytest.mark.asyncio
async def test_terminate_runpod_add_operation_marks_terminating_and_kills_group():
    killed = []
    operation = runpod_admin_service.RunPodAdminOperation(
        id="op-terminate",
        action="add",
        profile="img2img",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
        status="running",
        pid=4321,
        process=_FakeProcess(pid=4321),
    )
    runpod_admin_service._operations[operation.id] = operation

    runpod_admin_service._operation_runner.kill_process_group = lambda pid, sig: (
        killed.append((pid, sig))
    )

    payload = await runpod_admin_service.terminate_runpod_operation_payload(
        operation.id
    )

    assert payload["status"] == "accepted"
    assert operation.status == "terminating"
    assert operation.terminate_requested is True
    assert killed == [(4321, signal.SIGTERM)]
    assert operation.cleanup_status == "pending"


@pytest.mark.asyncio
async def test_terminate_detached_runpod_operation_returns_409_and_does_not_kill():
    store = InMemoryRunPodOperationStore()
    runpod_admin_service.set_runpod_operation_store_for_tests(store)
    await store.save_operation(
        {
            "id": "detached-op",
            "action": "add",
            "profile": "img2img",
            "owner_id": "old-host:1:abc",
            "status": "running",
            "pid": 4321,
            "terminate_requested": False,
            "log_tail": [],
            "command": [],
        },
        created_at=1.0,
    )
    runpod_admin_service._operation_runner.kill_process_group = lambda *_args: (
        pytest.fail("detached operation must not kill by PID")
    )

    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.terminate_runpod_operation_payload("detached-op")

    assert exc_info.value.status_code == 409
    assert "detached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_runpod_operation_persistence_keeps_log_redaction():
    store = InMemoryRunPodOperationStore()
    runpod_admin_service.set_runpod_operation_store_for_tests(store)
    operation = runpod_admin_service.RunPodAdminOperation(
        id="op-redact",
        action="add",
        profile="img2img",
        command=[
            "bash",
            "scripts/runpod_prod_ops.sh",
            "add",
            "--token=super-secret-token",
        ],
    )
    runpod_admin_service._append_log(
        operation,
        "Authorization: Bearer abc.def access_key=AKIASECRET x-amz-signature=123",
    )
    await runpod_admin_service._persist_operation(operation)

    payload = await store.get_operation("op-redact")

    assert payload is not None
    redacted_text = " ".join(payload["command"] + payload["log_tail"])
    assert "super-secret-token" not in redacted_text
    assert "abc.def" not in redacted_text
    assert "AKIASECRET" not in redacted_text
    assert "x-amz-signature=123" not in redacted_text


@pytest.mark.asyncio
async def test_termination_cleanup_runs_down_for_recorded_slots():
    commands = []
    operation = runpod_admin_service.RunPodAdminOperation(
        id="op-cleanup",
        action="add",
        profile="wan22_video_v2",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
        cleanup_slots=["03"],
    )

    async def fake_create_subprocess_exec(*command, **_kwargs):
        commands.append(list(command))
        return _FakeProcess(lines=["cleanup ok"])

    runpod_admin_service._operation_runner.create_subprocess_exec = (
        fake_create_subprocess_exec
    )

    ok = await runpod_admin_service._run_termination_cleanup(
        operation,
        env={},
    )

    assert ok is True
    assert operation.cleanup_status == "succeeded"
    assert operation.cleanup_exit_codes == [0]
    command = commands[0]
    assert "down" in command
    assert command[command.index("--profile") + 1] == "wan22_video_v2"
    assert command[command.index("--slot") + 1] == "03"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_failed_runpod_add_operation_auto_cleans_recorded_slots():
    commands = []
    processes = [
        _FakeProcess(
            exit_code=1,
            lines=[
                "[runpod-prod-worker] runpod_create_pod_03: running",
                "prod worker heartbeat timeout",
            ],
        ),
        _FakeProcess(exit_code=0, lines=["cleanup ok"]),
    ]
    operation = runpod_admin_service.RunPodAdminOperation(
        id="op-failed-add",
        action="add",
        profile="wan22_video_v2",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
        source="autoscaler",
    )
    runpod_admin_service._operations[operation.id] = operation

    async def fake_create_subprocess_exec(*command, **_kwargs):
        commands.append(list(command))
        return processes.pop(0)

    runpod_admin_service._operation_runner.create_subprocess_exec = (
        fake_create_subprocess_exec
    )

    await runpod_admin_service._run_operation(
        operation.id,
        command=operation.command,
        env={},
    )

    assert operation.status == "failed"
    assert operation.cleanup_slots == ["03"]
    assert operation.cleanup_status == "succeeded"
    assert operation.cleanup_exit_codes == [0]
    cleanup_command = commands[1]
    assert "down" in cleanup_command
    assert cleanup_command[cleanup_command.index("--profile") + 1] == "wan22_video_v2"
    assert cleanup_command[cleanup_command.index("--slot") + 1] == "03"
    assert "--execute" in cleanup_command


def test_runpod_operation_env_opens_required_mutation_gates(monkeypatch):
    monkeypatch.delenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", raising=False)
    monkeypatch.setenv("RUNPOD_MAX_PODS_TOTAL", "1")
    monkeypatch.setenv("RUNPOD_MAX_PODS_PER_TYPE", "1")
    monkeypatch.setenv("RUNPOD_MAX_HOURLY_COST_USD", "1")
    env = runpod_admin_service._operation_env(prod_max_manual_slots=None)

    assert env["RUNPOD_DRY_RUN"] == "false"
    assert env["RUNPOD_AUTOSCALER_ENABLED"] == "true"
    assert "RUNPOD_MAX_PODS_TOTAL" not in env
    assert "RUNPOD_MAX_PODS_PER_TYPE" not in env
    assert "RUNPOD_MAX_HOURLY_COST_USD" not in env
    assert env["RUNPOD_PROD_MAX_MANUAL_SLOTS"] == "100"


def test_runpod_env_defaults_prefer_container_env(monkeypatch, tmp_path):
    container_env = tmp_path / "container.env"
    cloud_test_env = tmp_path / ".env.cloud.test"
    cloud_prod_env = tmp_path / ".env.cloud.prod"
    container_env.write_text("APP_ENV=prod\n", encoding="utf-8")
    cloud_test_env.write_text("APP_ENV=test\n", encoding="utf-8")
    cloud_prod_env.write_text("APP_ENV=prod_file\n", encoding="utf-8")

    monkeypatch.delenv("DASHBOARD_RUNPOD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_RUNPOD_PROD_ENV_FILE", raising=False)
    monkeypatch.setenv("DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", str(container_env))
    monkeypatch.setattr(runpod_admin_service, "PROJECT_ROOT", tmp_path)

    assert runpod_admin_service._runpod_env_file() == str(container_env)
    assert runpod_admin_service._prod_env_file() == str(container_env)
