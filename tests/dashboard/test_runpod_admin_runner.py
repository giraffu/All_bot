import json
import logging
import signal

import pytest
from fastapi import HTTPException

from dashboard.backend.services.runpod_admin_commands import (
    RunPodAdminCommandBuilder,
)
from dashboard.backend.services.runpod_admin_operation import RunPodAdminOperation
from dashboard.backend.services.runpod_admin_runner import RunPodAdminOperationRunner
from dashboard.backend.services.runpod_operation_store import (
    InMemoryRunPodOperationStore,
)


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


def _discard_operation_coroutine(coro):
    coro.close()
    return None


def _build_runner(tmp_path, *, create_subprocess_exec=None, kill_process_group=None):
    store = InMemoryRunPodOperationStore()
    runner = RunPodAdminOperationRunner(
        store=store,
        command_builder=RunPodAdminCommandBuilder(project_root=tmp_path),
        project_root=tmp_path,
        logger=logging.getLogger("test.runpod.runner"),
        create_subprocess_exec=create_subprocess_exec,
        kill_process_group=kill_process_group,
    )
    return runner, store


@pytest.mark.asyncio
async def test_runner_registers_operation_and_active_add_lock(tmp_path):
    runner, store = _build_runner(tmp_path)

    operation = await runner.register_operation(
        action="add",
        profile="img2img",
        command=["bash", "ops.sh", "add"],
        env={},
        requested_count=1,
        active_add_profile="img2img",
        spawn_task_func=_discard_operation_coroutine,
    )

    assert operation.id in runner.operations
    assert await store.get_active_add("img2img") == operation.id
    stored = await store.get_operation(operation.id)
    assert stored["status"] == "pending"
    assert stored["requested_count"] == 1

    with pytest.raises(HTTPException) as exc_info:
        await runner.register_operation(
            action="add",
            profile="img2img",
            command=["bash", "ops.sh", "add"],
            env={},
            active_add_profile="img2img",
            spawn_task_func=_discard_operation_coroutine,
        )

    assert exc_info.value.status_code == 409
    assert operation.id in exc_info.value.detail


@pytest.mark.asyncio
async def test_runner_operations_payload_reads_detached_store_records(tmp_path):
    runner, store = _build_runner(tmp_path)
    await store.save_operation(
        {
            "id": "detached-op",
            "action": "add",
            "profile": "img2img",
            "owner_id": "old-host:123:abc",
            "status": "running",
            "terminate_requested": False,
            "log_tail": [],
            "command": [],
        },
        created_at=1.0,
    )

    payload = await runner.operations_payload()

    assert payload["count"] == 1
    operation = payload["operations"][0]
    assert operation["id"] == "detached-op"
    assert operation["attached"] is False
    assert operation["can_terminate"] is False
    assert "detached" in operation["can_terminate_reason"]


def test_runner_prunes_old_finished_local_operations(tmp_path):
    runner, _store = _build_runner(tmp_path)
    runner.max_operation_records = 2
    runner.operations["old-done"] = RunPodAdminOperation(
        id="old-done",
        action="restart",
        profile="img2img",
        command=["bash", "ops.sh", "restart"],
        status="succeeded",
        ended_at=1.0,
    )
    runner.operations["new-done"] = RunPodAdminOperation(
        id="new-done",
        action="restart",
        profile="img2img",
        command=["bash", "ops.sh", "restart"],
        status="failed",
        ended_at=2.0,
    )
    runner.operations["running"] = RunPodAdminOperation(
        id="running",
        action="restart",
        profile="img2img",
        command=["bash", "ops.sh", "restart"],
        status="running",
    )

    runner.prune_operations()

    assert set(runner.operations) == {"new-done", "running"}


@pytest.mark.asyncio
async def test_runner_terminate_attached_operation_kills_process_group(tmp_path):
    killed = []
    runner, store = _build_runner(
        tmp_path,
        kill_process_group=lambda pid, sig: killed.append((pid, sig)),
    )
    operation = RunPodAdminOperation(
        id="op-kill",
        action="add",
        profile="img2img",
        command=["bash", "ops.sh", "add"],
        status="running",
        pid=4321,
        process=_FakeProcess(pid=4321),
    )
    runner.operations[operation.id] = operation

    payload = await runner.terminate_operation_payload(operation.id)

    assert payload["status"] == "accepted"
    assert operation.status == "terminating"
    assert operation.terminate_requested is True
    assert operation.cleanup_status == "pending"
    assert killed == [(4321, signal.SIGTERM)]
    stored = await store.get_operation(operation.id)
    assert stored["status"] == "terminating"


@pytest.mark.asyncio
async def test_runner_terminate_detached_operation_returns_409_without_kill(tmp_path):
    runner, store = _build_runner(
        tmp_path,
        kill_process_group=lambda *_args: pytest.fail(
            "detached operation must not kill by PID"
        ),
    )
    await store.save_operation(
        {
            "id": "detached-op",
            "action": "add",
            "profile": "img2img",
            "owner_id": "old-host:123:abc",
            "status": "running",
            "pid": 4321,
            "terminate_requested": False,
            "log_tail": [],
            "command": [],
        },
        created_at=1.0,
    )

    with pytest.raises(HTTPException) as exc_info:
        await runner.terminate_operation_payload("detached-op")

    assert exc_info.value.status_code == 409
    assert "detached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_runner_run_operation_persists_exit_code_and_redacted_logs(tmp_path):
    commands = []

    async def fake_create_subprocess_exec(*command, **_kwargs):
        commands.append(list(command))
        return _FakeProcess(
            exit_code=0,
            lines=[
                "started token=super-secret",
                "finished",
            ],
        )

    runner, store = _build_runner(
        tmp_path,
        create_subprocess_exec=fake_create_subprocess_exec,
    )
    operation = RunPodAdminOperation(
        id="op-run",
        action="restart",
        profile="img2img",
        command=["bash", "ops.sh", "restart"],
    )
    runner.operations[operation.id] = operation

    await runner.run_operation(
        operation.id,
        command=operation.command,
        env={"RUNPOD_DRY_RUN": "false"},
    )

    assert commands == [["bash", "ops.sh", "restart"]]
    assert operation.status == "succeeded"
    assert operation.exit_code == 0
    stored = await store.get_operation(operation.id)
    assert stored["status"] == "succeeded"
    assert stored["exit_code"] == 0
    assert "super-secret" not in "\n".join(stored["log_tail"])


@pytest.mark.asyncio
async def test_runner_summarizes_lan_aio_preflight_failure(tmp_path):
    failure_payload = {
        "ok": False,
        "slots": [
            {
                "slot": "gpu-177-gpu1-wan22_video_v2",
                "checks": [
                    {
                        "name": "docker_registry_or_image_present",
                        "ok": False,
                        "error": "LAN AIO image unavailable",
                        "registry_configured": False,
                        "remote_image_present": False,
                        "runner_image_present": True,
                        "image_ref": "192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:tag",
                    }
                ],
            }
        ],
    }

    async def fake_create_subprocess_exec(*_command, **_kwargs):
        return _FakeProcess(
            exit_code=1,
            lines=[
                "[lan-aio-takeover] preflight failed "
                + json.dumps(failure_payload, separators=(",", ":")),
                "RuntimeError: takeover preflight failed",
            ],
        )

    runner, store = _build_runner(
        tmp_path,
        create_subprocess_exec=fake_create_subprocess_exec,
    )
    operation = RunPodAdminOperation(
        id="op-lan-aio-failed",
        action="lan-aio-takeover",
        profile="wan22_video_v2",
        command=["python3", "lan_aio_fleet_prod_ops.py", "takeover"],
    )
    runner.operations[operation.id] = operation

    await runner.run_operation(
        operation.id,
        command=operation.command,
        env={},
    )

    assert operation.status == "failed"
    assert operation.error.startswith("LAN AIO preflight failed:")
    assert "docker_registry_or_image_present" in operation.error
    assert "runner_image_present=True" in operation.error
    stored = await store.get_operation(operation.id)
    assert stored["error"] == operation.error


@pytest.mark.asyncio
async def test_runner_cleanup_only_recorded_slots_and_deduplicates(tmp_path):
    commands = []

    async def fake_create_subprocess_exec(*command, **_kwargs):
        commands.append(list(command))
        return _FakeProcess(lines=["cleanup ok"])

    runner, _store = _build_runner(
        tmp_path,
        create_subprocess_exec=fake_create_subprocess_exec,
    )
    operation = RunPodAdminOperation(
        id="op-cleanup",
        action="add",
        profile="wan22_video_v2",
        command=["bash", "ops.sh", "add"],
        cleanup_slots=["03", "03", "05"],
    )

    ok = await runner.run_termination_cleanup(operation, env={})

    assert ok is True
    assert operation.cleanup_status == "succeeded"
    assert operation.cleanup_exit_codes == [0, 0]
    assert [command[command.index("--slot") + 1] for command in commands] == [
        "03",
        "05",
    ]
    assert all("down" in command for command in commands)
    assert all("--execute" in command for command in commands)
