from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.services.private_bot_submission_ledger import (
    PrivateBotSubmissionConflict,
    PrivateBotSubmissionSnapshot,
    SqlAlchemyPrivateBotSubmissionRepository,
    build_private_bot_submission_request,
    claim_private_bot_submission_owner,
    claim_private_bot_submission_compensation,
    complete_private_bot_submission_compensation,
    mark_private_bot_submission_failed,
    mark_private_bot_submission_dispatching,
    mark_private_bot_submission_submitted,
    prune_private_bot_submission_ledger,
    record_private_bot_submission_cost,
    is_definitive_dispatch_rejection,
    reconcile_private_bot_dispatching_submission,
    reconcile_private_bot_recovery_submission,
    reserve_private_bot_submission,
)
from src.services import private_bot_submission_ledger as ledger_module


class InMemorySubmissionRepository:
    def __init__(self):
        self.requests = {}
        self.snapshots = {}

    async def reserve(self, request):
        existing_request = self.requests.get(request.submission_key)
        if existing_request is not None:
            if (
                existing_request.request_sha256 != request.request_sha256
                or existing_request.registry_task_id != request.registry_task_id
            ):
                raise PrivateBotSubmissionConflict(
                    "submission key was already used with different parameters"
                )
            return self.snapshots[request.submission_key]
        self.requests[request.submission_key] = request
        snapshot = PrivateBotSubmissionSnapshot(
            submission_key=request.submission_key,
            request_sha256=request.request_sha256,
            registry_task_id=request.registry_task_id,
            dispatch_task_id=request.registry_task_id,
            backend_task_id=None,
            status="reserved",
            actual_cost=None,
            saved_inputs=(),
        )
        self.snapshots[request.submission_key] = snapshot
        return snapshot

    async def get_by_registry_task_id(self, registry_task_id):
        return next(
            (
                snapshot
                for snapshot in self.snapshots.values()
                if snapshot.registry_task_id == registry_task_id
            ),
            None,
        )

    async def list_recovery_candidates(self, **_values):
        return list(self.snapshots.values())

    async def delete_terminal_before(self, **values):
        self.delete_terminal_values = values
        return 3

    def _validate(self, *, submission_key, request_sha256, registry_task_id):
        request = self.requests[submission_key]
        if (
            request.request_sha256 != request_sha256
            or request.registry_task_id != registry_task_id
        ):
            raise PrivateBotSubmissionConflict("request changed")
        return self.snapshots[submission_key]

    async def mark_dispatching(self, **values):
        snapshot = self._validate(
            submission_key=values["submission_key"],
            request_sha256=values["request_sha256"],
            registry_task_id=values["registry_task_id"],
        )
        if snapshot.actual_cost is not None and snapshot.actual_cost != values["actual_cost"]:
            raise PrivateBotSubmissionConflict("cost changed")
        snapshot = replace(
            snapshot,
            status="dispatching",
            dispatch_task_id=values["dispatch_task_id"],
            actual_cost=values["actual_cost"],
            saved_inputs=tuple(values["saved_inputs"]),
            submission_owner_token=values.get("owner_token"),
            submission_owner_deadline_at=values.get("owner_deadline_at"),
            reconcile_not_before_at=values.get("reconcile_not_before_at"),
        )
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def record_cost(self, **values):
        snapshot = self._validate(
            submission_key=values["submission_key"],
            request_sha256=values["request_sha256"],
            registry_task_id=values["registry_task_id"],
        )
        if snapshot.actual_cost is not None and snapshot.actual_cost != values["actual_cost"]:
            raise PrivateBotSubmissionConflict("cost changed")
        snapshot = replace(
            snapshot,
            actual_cost=values["actual_cost"],
            submission_owner_token=(
                values.get("owner_token") or snapshot.submission_owner_token
            ),
            submission_owner_deadline_at=(
                values.get("owner_deadline_at")
                or snapshot.submission_owner_deadline_at
            ),
            reconcile_not_before_at=(
                values.get("reconcile_not_before_at")
                or snapshot.reconcile_not_before_at
            ),
        )
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def claim_submission_owner(self, **values):
        snapshot = self._validate(
            submission_key=values["submission_key"],
            request_sha256=values["request_sha256"],
            registry_task_id=values["registry_task_id"],
        )
        if (
            snapshot.submission_owner_token
            and snapshot.submission_owner_token != values["owner_token"]
            and snapshot.reconcile_not_before_at > datetime.now()
        ):
            raise PrivateBotSubmissionConflict("submission is already owned")
        snapshot = replace(
            snapshot,
            submission_owner_token=values["owner_token"],
            submission_owner_deadline_at=values["owner_deadline_at"],
            reconcile_not_before_at=values["reconcile_not_before_at"],
            submission_owner_fence=snapshot.submission_owner_fence + 1,
        )
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def mark_submitted(self, **values):
        snapshot = self._validate(
            submission_key=values["submission_key"],
            request_sha256=values["request_sha256"],
            registry_task_id=values["registry_task_id"],
        )
        if snapshot.actual_cost is not None and snapshot.actual_cost != values["actual_cost"]:
            raise PrivateBotSubmissionConflict("cost changed")
        if (
            values.get("owner_token")
            and snapshot.submission_owner_token
            and values["owner_token"] != snapshot.submission_owner_token
        ):
            raise PrivateBotSubmissionConflict("submission owner changed")
        snapshot = replace(
            snapshot,
            status="submitted",
            backend_task_id=values["backend_task_id"],
            actual_cost=values["actual_cost"],
            saved_inputs=tuple(values["saved_inputs"]),
        )
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def mark_failed_if_reserved(self, **values):
        snapshot = self.snapshots[values["submission_key"]]
        if snapshot.status == "reserved":
            snapshot = replace(
                snapshot,
                status="failed",
                actual_cost=values["actual_cost"],
                error_code=values["error_code"],
                error_message=values["error_message"],
                compensation_status="pending",
            )
            self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def mark_failed(self, **values):
        snapshot = self.snapshots[values["submission_key"]]
        snapshot = replace(
            snapshot,
            status="failed",
            actual_cost=values["actual_cost"],
            error_code=values["error_code"],
            error_message=values["error_message"],
            compensation_status="pending",
        )
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def claim_compensation(self, **values):
        snapshot = self._validate(
            submission_key=values["submission_key"],
            request_sha256=values["request_sha256"],
            registry_task_id=values["registry_task_id"],
        )
        if snapshot.compensation_status != "pending":
            return None
        token = "lease-token"
        self.snapshots[values["submission_key"]] = replace(
            snapshot,
            compensation_status="processing",
            compensation_attempts=snapshot.compensation_attempts + 1,
        )
        return token

    async def request_compensation(self, **values):
        snapshot = self._validate(
            submission_key=values["submission_key"],
            request_sha256=values["request_sha256"],
            registry_task_id=values["registry_task_id"],
        )
        if snapshot.compensation_status == "not_required":
            snapshot = replace(snapshot, compensation_status="pending")
            self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def complete_compensation(self, **values):
        snapshot = self.snapshots[values["submission_key"]]
        if values["lease_token"] != "lease-token":
            raise PrivateBotSubmissionConflict("lease changed")
        snapshot = replace(snapshot, compensation_status="completed")
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot

    async def record_compensation_error(self, **values):
        snapshot = replace(
            self.snapshots[values["submission_key"]],
            compensation_last_error=values["error_message"],
        )
        self.snapshots[values["submission_key"]] = snapshot
        return snapshot


@pytest.mark.asyncio
async def test_sql_repository_request_compensation_persists_without_signature_error(
    monkeypatch,
):
    request = request_for()
    row = SimpleNamespace(
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        compensation_status="not_required",
        compensation_lease_token="stale",
        compensation_lease_until=datetime.now(),
        error_code=None,
        error_message=None,
    )
    session = SimpleNamespace(commit=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc_info):
            return False

    repository = SqlAlchemyPrivateBotSubmissionRepository(
        session_factory=SessionContext
    )
    repository._locked_row = AsyncMock(return_value=row)
    monkeypatch.setattr(ledger_module, "_snapshot", lambda value: value)

    result = await repository.request_compensation(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        error_code="dispatch_failed",
        error_message="failed",
    )

    assert result is row
    assert row.compensation_status == "pending"
    assert row.compensation_lease_token is None
    assert row.compensation_lease_until is None
    session.commit.assert_awaited_once()


def request_for(*, inputs=None, cost_override=6):
    return build_private_bot_submission_request(
        submission_key="private_bot_update:17:901:0",
        internal_user_id=456,
        client_type="bot:qqcc-private:17",
        task_type="quick_image",
        inputs=inputs or {"prompt": "hello", "images": ["a.png"]},
        source_post_id=None,
        deduct_quota=True,
        cost_override=cost_override,
        base_priority=0,
        user_cancel_allowed=True,
    )


def test_submission_request_has_deterministic_id_and_canonical_parameter_hash():
    first = request_for(inputs={"prompt": "hello", "images": ["a.png"]})
    reordered = request_for(inputs={"images": ["a.png"], "prompt": "hello"})
    changed_cost = request_for(cost_override=7)

    assert first.registry_task_id == reordered.registry_task_id
    assert first.request_sha256 == reordered.request_sha256
    assert changed_cost.registry_task_id == first.registry_task_id
    assert changed_cost.request_sha256 != first.request_sha256


def test_submission_hash_uses_file_content_not_ephemeral_temp_path(tmp_path):
    first_path = tmp_path / "first" / "random-a.png"
    second_path = tmp_path / "second" / "random-b.png"
    changed_path = tmp_path / "third" / "random-c.png"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    changed_path.parent.mkdir()
    first_path.write_bytes(b"same telegram payload")
    second_path.write_bytes(b"same telegram payload")
    changed_path.write_bytes(b"different telegram payload")

    first = request_for(inputs={"images": [str(first_path)]})
    same_content = request_for(inputs={"images": [str(second_path)]})
    changed_content = request_for(inputs={"images": [str(changed_path)]})

    assert first.request_sha256 == same_content.request_sha256
    assert first.request_sha256 != changed_content.request_sha256


def test_submission_hash_does_not_treat_arbitrary_prompt_as_local_file(tmp_path):
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("first local content")
    first = request_for(inputs={"prompt": str(prompt_path)})

    prompt_path.write_text("changed local content")
    replay = request_for(inputs={"prompt": str(prompt_path)})

    assert first.request_sha256 == replay.request_sha256


def test_submission_hash_accepts_stable_telegram_file_identity():
    first = request_for(
        inputs={"image": {"telegram_file_unique_id": "stable-file-identity"}}
    )
    replay = request_for(
        inputs={"image": {"telegram_file_unique_id": "stable-file-identity"}}
    )
    changed = request_for(
        inputs={"image": {"telegram_file_unique_id": "different-file-identity"}}
    )

    assert first.request_sha256 == replay.request_sha256
    assert first.request_sha256 != changed.request_sha256


def test_only_explicit_non_transient_http_rejection_is_safe_to_compensate():
    request = httpx.Request("POST", "https://central.example/tasks")

    def error(status_code):
        cause = httpx.HTTPStatusError(
            "rejected",
            request=request,
            response=httpx.Response(status_code, request=request),
        )
        return RuntimeError("dispatch failed").with_traceback(None), cause

    rejected, rejected_cause = error(422)
    rejected.__cause__ = rejected_cause
    timeout, timeout_cause = error(408)
    timeout.__cause__ = timeout_cause
    conflict, conflict_cause = error(409)
    conflict.__cause__ = conflict_cause
    server, server_cause = error(503)
    server.__cause__ = server_cause

    assert is_definitive_dispatch_rejection(rejected) is True
    assert is_definitive_dispatch_rejection(conflict) is True
    assert is_definitive_dispatch_rejection(timeout) is False
    assert is_definitive_dispatch_rejection(server) is False
    assert is_definitive_dispatch_rejection(ConnectionError("network")) is False


@pytest.mark.asyncio
async def test_submission_owner_is_fenced_before_runtime_acquisition():
    repository = InMemorySubmissionRepository()
    request = request_for()
    await reserve_private_bot_submission(request, repository=repository)
    deadline = datetime.now() + timedelta(minutes=15)
    reconcile_at = deadline + timedelta(minutes=1)

    claimed = await claim_private_bot_submission_owner(
        request=request,
        owner_token="owner-a",
        owner_deadline_at=deadline,
        reconcile_not_before_at=reconcile_at,
        repository=repository,
    )

    assert claimed.status == "reserved"
    assert claimed.submission_owner_token == "owner-a"
    assert claimed.submission_owner_deadline_at == deadline
    assert claimed.reconcile_not_before_at == reconcile_at
    assert claimed.submission_owner_fence == 1


@pytest.mark.asyncio
async def test_stale_submission_owner_cannot_publish_submitted_outcome():
    repository = InMemorySubmissionRepository()
    request = request_for()
    await reserve_private_bot_submission(request, repository=repository)
    deadline = datetime.now() + timedelta(minutes=15)
    await claim_private_bot_submission_owner(
        request=request,
        owner_token="current-owner",
        owner_deadline_at=deadline,
        reconcile_not_before_at=deadline + timedelta(minutes=1),
        repository=repository,
    )
    await record_private_bot_submission_cost(
        request=request,
        actual_cost=6,
        owner_token="current-owner",
        owner_deadline_at=deadline,
        reconcile_not_before_at=deadline + timedelta(minutes=1),
        repository=repository,
    )

    with pytest.raises(PrivateBotSubmissionConflict, match="owner changed"):
        await mark_private_bot_submission_submitted(
            request=request,
            result={
                "registry_task_id": request.registry_task_id,
                "backend_task_id": "backend-actual",
                "cost": 6,
                "saved_inputs": [],
            },
            owner_token="stale-owner",
            repository=repository,
        )


@pytest.mark.asyncio
async def test_submission_retention_is_bounded_and_excludes_active_registry_tasks():
    repository = InMemorySubmissionRepository()
    now = datetime(2026, 7, 12, 12, 0, 0)

    deleted = await prune_private_bot_submission_ledger(
        active_registry_task_ids={"active-task"},
        now=now,
        retention_days=1,
        limit=17,
        repository=repository,
    )

    assert deleted == 3
    assert repository.delete_terminal_values == {
        "cutoff": now - timedelta(days=30),
        "exclude_registry_task_ids": {"active-task"},
        "limit": 17,
    }


@pytest.mark.asyncio
async def test_ledger_replays_first_dispatch_outcome_and_rejects_parameter_or_cost_change():
    repository = InMemorySubmissionRepository()
    request = request_for()

    reserved = await reserve_private_bot_submission(request, repository=repository)
    cost_recorded = await record_private_bot_submission_cost(
        request=request,
        actual_cost=6,
        repository=repository,
    )
    dispatching = await mark_private_bot_submission_dispatching(
        request=request,
        registry_task_id=request.registry_task_id,
        actual_cost=6,
        saved_inputs=["saved/a.png"],
        repository=repository,
    )
    submitted = await mark_private_bot_submission_submitted(
        request=request,
        result={
            "registry_task_id": request.registry_task_id,
            "backend_task_id": "backend-actual",
            "cost": 6,
            "saved_inputs": ["saved/a.png"],
        },
        repository=repository,
    )

    assert reserved.status == "reserved"
    assert cost_recorded.actual_cost == 6
    assert dispatching.status == "dispatching"
    assert submitted.status == "submitted"
    assert submitted.as_task_result() == {
        "registry_task_id": request.registry_task_id,
        "backend_task_id": "backend-actual",
        "cost": 6,
        "saved_inputs": ["saved/a.png"],
    }
    assert await reserve_private_bot_submission(request, repository=repository) == submitted

    with pytest.raises(PrivateBotSubmissionConflict, match="different parameters"):
        await reserve_private_bot_submission(
            request_for(inputs={"prompt": "changed"}),
            repository=repository,
        )
    with pytest.raises(PrivateBotSubmissionConflict, match="cost changed"):
        await record_private_bot_submission_cost(
            request=request,
            actual_cost=7,
            repository=repository,
        )


@pytest.mark.asyncio
async def test_failed_compensation_uses_single_durable_lease_and_completion_state():
    repository = InMemorySubmissionRepository()
    request = request_for()
    await reserve_private_bot_submission(request, repository=repository)
    failed = await mark_private_bot_submission_failed(
        request=request,
        actual_cost=6,
        error_code="dispatch_rejected",
        error_message="rejected",
        repository=repository,
    )

    lease_token = await claim_private_bot_submission_compensation(
        request=request,
        repository=repository,
    )
    duplicate_claim = await claim_private_bot_submission_compensation(
        request=request,
        repository=repository,
    )
    completed = await complete_private_bot_submission_compensation(
        request=request,
        lease_token=lease_token,
        repository=repository,
    )

    assert failed.compensation_status == "pending"
    assert lease_token == "lease-token"
    assert duplicate_claim is None
    assert completed.compensation_status == "completed"


@pytest.mark.asyncio
async def test_dispatching_reconciliation_queries_deterministic_backend_without_redispatch():
    snapshot = PrivateBotSubmissionSnapshot(
        submission_key="private_bot_update:17:901:0",
        request_sha256="a" * 64,
        registry_task_id="deterministic-task",
        dispatch_task_id="deterministic-task",
        backend_task_id=None,
        status="dispatching",
        actual_cost=6,
        saved_inputs=("saved/a.png",),
    )
    registry_lookup = AsyncMock(return_value=None)
    backend_lookup = AsyncMock(return_value={"status": "pending"})

    result = await reconcile_private_bot_dispatching_submission(
        snapshot,
        registry_lookup=registry_lookup,
        backend_lookup=backend_lookup,
    )

    assert result.confirmed is True
    assert result.source == "backend"
    registry_lookup.assert_awaited_once_with("deterministic-task")
    backend_lookup.assert_awaited_once_with("deterministic-task")


@pytest.mark.asyncio
async def test_dispatching_reconciliation_distinguishes_not_found_from_lookup_failure():
    snapshot = PrivateBotSubmissionSnapshot(
        submission_key="private_bot_update:17:901:0",
        request_sha256="a" * 64,
        registry_task_id="deterministic-task",
        dispatch_task_id="deterministic-task",
        backend_task_id=None,
        status="dispatching",
        actual_cost=6,
        saved_inputs=(),
    )

    missing = await reconcile_private_bot_dispatching_submission(
        snapshot,
        registry_lookup=AsyncMock(return_value=None),
        backend_lookup=AsyncMock(return_value=None),
    )
    unavailable = await reconcile_private_bot_dispatching_submission(
        snapshot,
        registry_lookup=AsyncMock(side_effect=RuntimeError("redis down")),
        backend_lookup=AsyncMock(side_effect=RuntimeError("central down")),
    )

    assert missing.confirmed is False
    assert missing.definitively_missing is True
    assert unavailable.confirmed is False
    assert unavailable.definitively_missing is False


@pytest.mark.asyncio
async def test_dispatching_404_stays_uncertain_during_original_dispatch_grace():
    now = datetime(2026, 7, 12, 12, 0, 0)
    snapshot = PrivateBotSubmissionSnapshot(
        submission_key="private_bot_update:17:901:0",
        request_sha256="a" * 64,
        registry_task_id="deterministic-task",
        dispatch_task_id="deterministic-task",
        backend_task_id=None,
        status="dispatching",
        actual_cost=6,
        saved_inputs=(),
        dispatch_started_at=now - timedelta(seconds=10),
    )

    outcome = await reconcile_private_bot_dispatching_submission(
        snapshot,
        registry_lookup=AsyncMock(return_value={"backend_task_id": None}),
        backend_lookup=AsyncMock(return_value=None),
        grace_seconds=60,
        now_func=lambda: now,
    )

    assert outcome.confirmed is False
    assert outcome.definitively_missing is False
    assert outcome.source == "dispatch_grace"
    assert outcome.retry_after_seconds == 50


@pytest.mark.asyncio
async def test_alive_dispatch_owner_fence_outlives_single_http_timeout():
    now = datetime(2026, 7, 12, 12, 0, 0)
    snapshot = PrivateBotSubmissionSnapshot(
        submission_key="private_bot_update:17:901:0",
        request_sha256="a" * 64,
        registry_task_id="deterministic-task",
        dispatch_task_id="deterministic-task",
        backend_task_id=None,
        status="dispatching",
        actual_cost=6,
        saved_inputs=(),
        dispatch_started_at=now - timedelta(seconds=75),
        submission_owner_token="owner",
        submission_owner_deadline_at=now + timedelta(seconds=225),
        reconcile_not_before_at=now + timedelta(seconds=285),
        submission_owner_fence=1,
    )

    outcome = await reconcile_private_bot_dispatching_submission(
        snapshot,
        registry_lookup=AsyncMock(return_value={"backend_task_id": None}),
        backend_lookup=AsyncMock(return_value=None),
        grace_seconds=60,
        now_func=lambda: now,
    )

    assert outcome.confirmed is False
    assert outcome.definitively_missing is False
    assert outcome.source == "dispatch_owner_fence"
    assert outcome.retry_after_seconds == 285


@pytest.mark.asyncio
async def test_reserved_registry_is_not_missing_while_submission_owner_is_alive():
    repository = InMemorySubmissionRepository()
    request = request_for()
    await reserve_private_bot_submission(request, repository=repository)
    now = datetime(2026, 7, 12, 12, 0, 0)
    repository.snapshots[request.submission_key] = replace(
        repository.snapshots[request.submission_key],
        actual_cost=6,
        submission_owner_token="owner",
        submission_owner_deadline_at=now + timedelta(seconds=200),
        reconcile_not_before_at=now + timedelta(seconds=260),
        submission_owner_fence=1,
    )

    outcome = await reconcile_private_bot_recovery_submission(
        registry_task_id=request.registry_task_id,
        registry_task={"backend_task_id": None},
        backend_lookup=AsyncMock(return_value=None),
        update_registry_backend=AsyncMock(),
        repository=repository,
        now_func=lambda: now,
    )

    assert outcome.confirmed is False
    assert outcome.definitively_missing is False
    assert outcome.retry_after_seconds == 260


@pytest.mark.asyncio
async def test_recovery_binds_accepted_timeout_to_same_deterministic_task():
    repository = InMemorySubmissionRepository()
    request = request_for()
    await reserve_private_bot_submission(request, repository=repository)
    await record_private_bot_submission_cost(
        request=request,
        actual_cost=6,
        repository=repository,
    )
    await mark_private_bot_submission_dispatching(
        request=request,
        registry_task_id=request.registry_task_id,
        actual_cost=6,
        saved_inputs=["saved/a.png"],
        repository=repository,
    )
    update_registry = AsyncMock()

    outcome = await reconcile_private_bot_recovery_submission(
        registry_task_id=request.registry_task_id,
        registry_task={"backend_task_id": None},
        backend_lookup=AsyncMock(return_value={"status": "pending"}),
        update_registry_backend=update_registry,
        repository=repository,
    )

    assert outcome.confirmed is True
    assert outcome.backend_task_id == request.registry_task_id
    assert outcome.snapshot.status == "submitted"
    update_registry.assert_awaited_once_with(
        request.registry_task_id,
        request.registry_task_id,
    )
