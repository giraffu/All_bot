import signal

import pytest
from fastapi import HTTPException

from dashboard.backend.schemas import (
    LanAioSlotActionRequest,
    RunPodScaleItem,
    RunPodScaleRequest,
    RunPodWorkerActionRequest,
)
from dashboard.backend.services.runpod_operation_store import (
    InMemoryRunPodOperationStore,
)
from dashboard.backend.services import runpod_admin_service
from ops.gpu_pool_controller.config_loader import load_controller_config
from ops.gpu_pool_controller.lan_aio_prod import (
    load_lan_aio_prod_slots,
    slot_to_jsonable,
)


@pytest.fixture(autouse=True)
def _clear_runpod_admin_operations():
    runpod_admin_service.set_runpod_operation_store_for_tests(
        InMemoryRunPodOperationStore()
    )
    runpod_admin_service._operations.clear()
    runpod_admin_service._operation_runner.create_subprocess_exec = None
    runpod_admin_service._operation_runner.kill_process_group = None
    yield
    runpod_admin_service._operations.clear()
    runpod_admin_service._operation_runner.create_subprocess_exec = None
    runpod_admin_service._operation_runner.kill_process_group = None
    runpod_admin_service.set_runpod_operation_store_for_tests(
        InMemoryRunPodOperationStore()
    )


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
    ]
    assert payload["profiles"][0]["supported_task_types"] == [
        "img2img",
        "img2img_lora",
    ]


@pytest.mark.asyncio
async def test_lan_aio_profiles_payload_lists_configured_aio_profiles():
    payload = await runpod_admin_service.get_lan_aio_profiles_payload()

    profiles = {item["profile"]: item for item in payload["profiles"]}
    assert "pornmaster_flux2_edit" in profiles
    assert "scail2" in profiles
    assert "face_i2i_t2i" not in profiles
    assert profiles["pornmaster_flux2_edit"]["all_in_one_image_ref"]
    assert profiles["pornmaster_flux2_edit"]["model_manifest_key"] == (
        "pornmaster_flux2_edit/2026-06-27/manifest.json"
    )


@pytest.mark.asyncio
async def test_lan_aio_slots_payload_groups_enabled_and_disabled_candidates(monkeypatch):
    class FakeLanAioOps:
        def __init__(self):
            self.config = load_controller_config()
            self.slots = load_lan_aio_prod_slots(include_disabled=True)

        def select_slots(self, slot_id, *, include_disabled=False):
            if slot_id is not None:
                return [self.slots[slot_id]]
            return [
                slot
                for slot in self.slots.values()
                if include_disabled or slot.enabled
            ]

        def status_payload(self, slots):
            return {
                "ok": True,
                "slots": [
                    {
                        "slot": slot_to_jsonable(slot, self.config),
                        "workers": [],
                        "control": {"legacy": "disabled", "aio": "enabled"},
                        "remote_containers": [],
                        "model_cache": {"status": "ready", "profile": slot.target_profile_id},
                    }
                    for slot in slots
                ],
            }

    monkeypatch.setattr(
        runpod_admin_service,
        "_build_lan_aio_ops",
        lambda: FakeLanAioOps(),
    )

    payload = await runpod_admin_service.get_lan_aio_slots_payload(
        include_disabled=True,
    )

    groups = {item["physical_slot_key"]: item for item in payload["groups"]}
    assert "gpu-252:gpu0" in groups
    gpu252_slots = {
        item["slot"]["id"]: item
        for item in groups["gpu-252:gpu0"]["slots"]
    }
    assert "gpu-252-gpu0-img2img_lora" in gpu252_slots
    assert "gpu-252-gpu0-pornmaster_flux2_edit" in gpu252_slots
    assert gpu252_slots["gpu-252-gpu0-img2img_lora"]["slot"]["enabled"] is False
    assert gpu252_slots["gpu-252-gpu0-pornmaster_flux2_edit"]["model_cache"]["status"] == "ready"
    gpu002_slots = {
        item["slot"]["id"]: item
        for item in groups["gpu-002:gpu1"]["slots"]
    }
    assert "gpu-002-gpu1-image_to_video" in gpu002_slots
    assert "gpu-002-gpu1-pornmaster_flux2_edit" in gpu002_slots
    assert gpu002_slots["gpu-002-gpu1-image_to_video"]["slot"]["enabled"] is True
    assert gpu002_slots["gpu-002-gpu1-pornmaster_flux2_edit"]["slot"]["enabled"] is False


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
        "wan22_video_v2",
    ]
    command = payload["operations"][0]["command"]
    assert "add" in command
    assert command[command.index("--profile") + 1] == "img2img"
    assert command[command.index("--count") + 1] == "2"
    assert "--desired" not in command
    assert "--retry-unavailable" in command
    assert command[command.index("--max-attempts") + 1] == "100"
    assert command[command.index("--retry-interval") + 1] == "30"
    assert "--execute" in command
    assert payload["operations"][0]["action"] == "add"
    assert payload["operations"][0]["requested_count"] == 2
    assert "desired_count" not in payload["operations"][0]


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
async def test_start_runpod_scale_payload_rejects_active_profile_add():
    first_payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img", count=1),
            ],
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.start_runpod_scale_payload(
            RunPodScaleRequest(
                items=[
                    RunPodScaleItem(profile="img2img_lora", count=1),
                ],
            ),
            spawn_task_func=_discard_operation_coroutine,
        )

    assert first_payload["operations"][0]["status"] == "pending"
    assert exc_info.value.status_code == 409
    assert "already active for profile img2img" in exc_info.value.detail


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

    assert await store.acquire_active_lan_aio_slot("gpu-252:gpu0", "op-2") is True
    assert await store.acquire_active_lan_aio_slot("gpu-252:gpu0", "op-3") is False
    assert await store.get_active_lan_aio_slot("gpu-252:gpu0") == "op-2"
    await store.release_active_lan_aio_slot("gpu-252:gpu0", "op-other")
    assert await store.get_active_lan_aio_slot("gpu-252:gpu0") == "op-2"
    await store.release_active_lan_aio_slot("gpu-252:gpu0", "op-2")
    assert await store.get_active_lan_aio_slot("gpu-252:gpu0") is None

    await store.prune_operations(max_records=1)
    assert [item["id"] for item in await store.list_operations(limit=10)] == ["op-2"]


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

    payload = await runpod_admin_service.get_runpod_operations_payload()

    assert payload["count"] == 1
    operation = payload["operations"][0]
    assert operation["id"] == "detached-op"
    assert operation["owner_id"] == "old-host:1:abc"
    assert operation["attached"] is False
    assert operation["can_terminate"] is False
    assert "detached" in operation["can_terminate_reason"]


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
        trigger_reason="scale_up: estimated clear time 1300s exceeds 1200s",
        spawn_task_func=_discard_operation_coroutine,
    )

    command = operation.command
    assert operation.action == "add"
    assert command[command.index("--worker-timeout") + 1] == "2400"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_restart_lan_aio_worker_builds_slot_scoped_operation():
    payload = await runpod_admin_service.restart_lan_aio_worker_payload(
        agent_id="lan_aio_prod_gpu177_gpu0_image_to_video_01",
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )

    operation = payload["operation"]
    command = operation["command"]
    assert operation["status"] == "pending"
    assert operation["action"] == "restart"
    assert operation["profile"] == "wan22_video_v2"
    assert operation["slot"] == "gpu-177-gpu0-image_to_video"
    assert command[:3] == [
        "python3",
        str(runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "restart-aio",
    ]
    assert command[command.index("--slot") + 1] == "gpu-177-gpu0-image_to_video"
    assert "--execute" in command


@pytest.mark.asyncio
async def test_pause_and_enable_lan_aio_worker_build_slot_scoped_operations():
    pause_payload = await runpod_admin_service.pause_lan_aio_worker_payload(
        agent_id="lan_aio_prod_gpu177_gpu0_image_to_video_01",
        request=RunPodWorkerActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )
    enable_payload = await runpod_admin_service.enable_lan_aio_worker_payload(
        agent_id="lan_aio_prod_gpu177_gpu0_image_to_video_01",
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
    assert pause_operation["slot"] == "gpu-177-gpu0-image_to_video"
    assert pause_command[:3] == [
        "python3",
        str(runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "disable-aio",
    ]
    assert pause_command[pause_command.index("--slot") + 1] == "gpu-177-gpu0-image_to_video"
    assert "--execute" in pause_command
    assert enable_operation["action"] == "enable"
    assert enable_operation["profile"] == "wan22_video_v2"
    assert enable_operation["slot"] == "gpu-177-gpu0-image_to_video"
    assert enable_command[:3] == [
        "python3",
        str(runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "enable-aio",
    ]
    assert enable_command[enable_command.index("--slot") + 1] == "gpu-177-gpu0-image_to_video"
    assert "--execute" in enable_command


@pytest.mark.asyncio
async def test_lan_aio_slot_action_builds_operation_and_locks_physical_slot():
    first_payload = await runpod_admin_service.start_lan_aio_slot_action_payload(
        slot_id="gpu-252-gpu0-pornmaster_flux2_edit",
        action="warm-cache",
        request=LanAioSlotActionRequest(reason="dashboard warm cache"),
        spawn_task_func=_discard_operation_coroutine,
    )

    operation = first_payload["operation"]
    command = operation["command"]
    assert operation["status"] == "pending"
    assert operation["action"] == "lan-aio-warm-cache"
    assert operation["profile"] == "pornmaster_flux2_edit"
    assert operation["slot"] == "gpu-252-gpu0-pornmaster_flux2_edit"
    assert operation["active_lan_aio_slot"] == "gpu-252:gpu0"
    assert operation["trigger_reason"] == "dashboard warm cache"
    assert command[:3] == [
        "python3",
        str(runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "warm-cache",
    ]
    assert command[command.index("--slot") + 1] == (
        "gpu-252-gpu0-pornmaster_flux2_edit"
    )
    assert "--include-disabled" in command
    assert "--execute" in command

    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.start_lan_aio_slot_action_payload(
            slot_id="gpu-252-gpu0-img2img_lora",
            action="pull-image",
            request=LanAioSlotActionRequest(),
            spawn_task_func=_discard_operation_coroutine,
        )

    assert exc_info.value.status_code == 409
    assert "gpu-252:gpu0" in exc_info.value.detail


@pytest.mark.asyncio
async def test_lan_aio_takeover_action_builds_single_slot_operation():
    payload = await runpod_admin_service.start_lan_aio_slot_action_payload(
        slot_id="gpu-002-gpu1-pornmaster_flux2_edit",
        action="takeover",
        request=LanAioSlotActionRequest(),
        spawn_task_func=_discard_operation_coroutine,
    )

    operation = payload["operation"]
    command = operation["command"]
    assert operation["status"] == "pending"
    assert operation["action"] == "lan-aio-takeover"
    assert operation["profile"] == "pornmaster_flux2_edit"
    assert operation["slot"] == "gpu-002-gpu1-pornmaster_flux2_edit"
    assert operation["active_lan_aio_slot"] == "gpu-002:gpu1"
    assert operation["trigger_reason"] == "dashboard lan-aio-takeover"
    assert command[:3] == [
        "python3",
        str(runpod_admin_service.PROJECT_ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "takeover",
    ]
    assert command[command.index("--slot") + 1] == (
        "gpu-002-gpu1-pornmaster_flux2_edit"
    )
    assert "--include-disabled" in command
    assert "--execute" in command


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

    runpod_admin_service._operation_runner.kill_process_group = (
        lambda pid, sig: killed.append((pid, sig))
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
async def test_terminate_detached_runpod_operation_returns_409_and_does_not_kill(
):
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
    runpod_admin_service._operation_runner.kill_process_group = (
        lambda *_args: pytest.fail("detached operation must not kill by PID")
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
