from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import recover_scail2_history_delivery as recovery


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, store):
        self.store = store
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        history = self.store.get("history")
        return _FakeResult([history] if history else [])

    async def get(self, model, _key):
        if model is recovery.RuntimeCheckpoint:
            return self.store.get("checkpoint")
        if model is recovery.User:
            return self.store.get("user")
        return None

    def add(self, obj):
        if isinstance(obj, recovery.RuntimeCheckpoint):
            self.store["checkpoint"] = obj


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionFactory:
    def __init__(self, store):
        self.store = store

    def __call__(self):
        return _SessionContext(_FakeSession(self.store))


class _SequenceSessionFactory:
    def __init__(self, stores):
        self._stores = list(stores)

    def __call__(self):
        store = self._stores.pop(0)
        return _SessionContext(_FakeSession(store))


def _candidate(
    *,
    registry_task_id="task-1",
    backend_task_id="backend-1",
    internal_user_id=1001,
    task_type="scail2_action_transfer",
):
    return recovery.FinalizerCandidate(
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        internal_user_id=internal_user_id,
        username="tester",
        task_type=task_type,
        cost=40,
    )


def test_filter_scail2_candidates_keeps_only_target_task_types():
    pending = {
        "task-1": {
            "backend_task_id": "backend-1",
            "internal_user_id": 1001,
            "submission_context": {"task_type": "scail2_action_transfer"},
        },
        "task-2": {
            "backend_task_id": "backend-2",
            "internal_user_id": 1001,
            "submission_context": {"task_type": "image"},
        },
        "task-3": {
            "backend_task_id": "backend-3",
            "internal_user_id": 1001,
            "submission_context": {"task_type": "scail2_video_replacement"},
        },
        "task-4": {
            "backend_task_id": "backend-4",
            "internal_user_id": 1001,
            "submission_context": {"task_type": "scail2_face_swap_v2"},
        },
        "task-5": {
            "backend_task_id": "backend-5",
            "internal_user_id": 1001,
            "submission_context": {"task_type": "scail2_action_transfer_long"},
        },
    }

    candidates = recovery.filter_scail2_candidates(
        pending,
        task_types=recovery.SCAIL2_TASK_TYPES,
    )

    assert [candidate.registry_task_id for candidate in candidates] == [
        "task-1",
        "task-3",
        "task-4",
        "task-5",
    ]


@pytest.mark.asyncio
async def test_recover_dry_run_does_not_process_finalizer():
    process_finalizer = AsyncMock()
    get_status = AsyncMock(return_value={"status": "done", "result_path": "out.mp4"})

    report = await recovery.recover_snapshot_histories(
        candidates=[_candidate()],
        execute=False,
        session_factory=_SessionFactory({"history": None}),
        process_finalizer_func=process_finalizer,
        get_task_status_func=get_status,
    )

    assert report["summary"] == {"would_recover": 1}
    process_finalizer.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_skips_backend_error_without_refund_finalizer():
    process_finalizer = AsyncMock()
    get_status = AsyncMock(return_value={"status": "error", "result_path": "out.mp4"})

    report = await recovery.recover_snapshot_histories(
        candidates=[_candidate()],
        execute=True,
        session_factory=_SessionFactory({"history": None}),
        process_finalizer_func=process_finalizer,
        get_task_status_func=get_status,
    )

    assert report["summary"] == {"audit_backend_not_success": 1}
    process_finalizer.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_execute_processes_done_result_and_confirms_history():
    history = SimpleNamespace(output_file="user-data-prod/history/task-1/output.mp4")
    process_finalizer = AsyncMock(return_value=True)
    get_status = AsyncMock(return_value={"status": "done", "result_path": "out.mp4"})

    report = await recovery.recover_snapshot_histories(
        candidates=[_candidate()],
        execute=True,
        session_factory=_SequenceSessionFactory(
            [
                {"history": None},
                {"history": history},
            ]
        ),
        process_finalizer_func=process_finalizer,
        get_task_status_func=get_status,
    )

    assert report["summary"] == {"recovered": 1}
    process_finalizer.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_send_dry_run_does_not_send_telegram():
    send_service = AsyncMock()
    history = SimpleNamespace(output_file="user-data-prod/history/task-1/output.mp4")
    user = SimpleNamespace(id=1001, telegram_id=2002)

    report = await recovery.send_recovered_histories(
        candidates=[_candidate()],
        execute=False,
        session_factory=_SessionFactory(
            {
                "checkpoint": SimpleNamespace(value={}),
                "history": history,
                "user": user,
            }
        ),
        send_service_func=send_service,
    )

    assert report["summary"] == {"would_send": 1}
    send_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_skips_user_without_telegram_binding():
    send_service = AsyncMock()
    history = SimpleNamespace(output_file="user-data-prod/history/task-1/output.mp4")
    user = SimpleNamespace(id=1001, telegram_id=None)

    report = await recovery.send_recovered_histories(
        candidates=[_candidate()],
        execute=True,
        session_factory=_SessionFactory(
            {
                "checkpoint": SimpleNamespace(value={}),
                "history": history,
                "user": user,
            }
        ),
        send_service_func=send_service,
    )

    assert report["summary"] == {"skipped_no_telegram": 1}
    send_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_checkpoint_prevents_duplicate_delivery():
    send_service = AsyncMock()

    report = await recovery.send_recovered_histories(
        candidates=[_candidate()],
        execute=True,
        session_factory=_SessionFactory(
            {
                "checkpoint": SimpleNamespace(value={"sent_task_ids": ["task-1"]}),
            }
        ),
        send_service_func=send_service,
    )

    assert report["summary"] == {"already_sent": 1}
    send_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_execute_records_sent_task_id_in_checkpoint():
    send_service = AsyncMock(return_value={"status": "success"})
    history = SimpleNamespace(output_file="user-data-prod/history/task-1/output.mp4")
    user = SimpleNamespace(id=1001, telegram_id=2002)
    store = {
        "checkpoint": None,
        "history": history,
        "user": user,
    }

    report = await recovery.send_recovered_histories(
        candidates=[_candidate()],
        execute=True,
        session_factory=_SessionFactory(store),
        send_service_func=send_service,
    )

    assert report["summary"] == {"sent": 1}
    assert store["checkpoint"].value["sent_task_ids"] == ["task-1"]
    send_service.assert_awaited_once()
