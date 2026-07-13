from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert


PRIVATE_BOT_SUBMISSION_STATUSES = frozenset(
    {"reserved", "dispatching", "submitted", "failed"}
)
PRIVATE_BOT_DISPATCH_HARD_DEADLINE_SECONDS = 300
PRIVATE_BOT_PREPARATION_HARD_DEADLINE_SECONDS = 900
PRIVATE_BOT_DISPATCH_SETTLE_GRACE_SECONDS = 60
PRIVATE_BOT_DEBIT_AUDIT_GRACE_SECONDS = 300
PRIVATE_BOT_SUBMISSION_RETENTION_DAYS = max(
    30,
    int(os.getenv("PRIVATE_QQCC_BOT_SUBMISSION_RETENTION_DAYS", "90")),
)
PRIVATE_BOT_SUBMISSION_RETENTION_BATCH_SIZE = 200
PRIVATE_BOT_DISPATCH_RECONCILIATION_GRACE_SECONDS = (
    PRIVATE_BOT_DISPATCH_HARD_DEADLINE_SECONDS
    + PRIVATE_BOT_DISPATCH_SETTLE_GRACE_SECONDS
)
_LOCAL_FILE_INPUT_KEYS = frozenset(
    {
        "body_image_path",
        "end_frame_path",
        "end_image",
        "end_image_path",
        "face_image",
        "face_image_path",
        "image",
        "image_path",
        "image_paths",
        "images",
        "input_files",
        "input_paths",
        "motion_video_path",
        "reference_image_path",
        "start_image_path",
        "target_image",
        "target_video",
        "video",
        "video_path",
    }
)


class PrivateBotSubmissionLedgerError(RuntimeError):
    pass


class PrivateBotSubmissionConflict(PrivateBotSubmissionLedgerError):
    pass


class PrivateBotSubmissionUnavailable(PrivateBotSubmissionLedgerError):
    pass


class PrivateBotSubmissionReplayHandled(Exception):
    """The durable original submission owns monitoring and result delivery."""

    def __init__(self, registry_task_id: str):
        super().__init__(registry_task_id)
        self.registry_task_id = registry_task_id


def private_bot_submission_refund_idempotency_key(
    registry_task_id: str,
) -> str:
    return f"task_refund:task:{registry_task_id}"


def private_bot_submission_concurrency_idempotency_key(
    registry_task_id: str,
) -> str:
    return f"task_concurrency:{registry_task_id}"


def private_bot_submission_release_idempotency_key(
    registry_task_id: str,
) -> str:
    return private_bot_submission_concurrency_idempotency_key(registry_task_id)


def _fingerprint_local_file(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as file_obj:
            while chunk := file_obj.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise PrivateBotSubmissionUnavailable(
            "private Bot submission input file is unavailable"
        ) from exc
    return {
        "local_file_sha256": digest.hexdigest(),
        "size": size,
    }


def _canonicalize_request_value(value: Any, *, input_key: str | None = None) -> Any:
    """Remove ephemeral local paths while preserving request identity."""

    if isinstance(value, bytes):
        return {
            "bytes_sha256": hashlib.sha256(value).hexdigest(),
            "length": len(value),
        }
    if isinstance(value, Path):
        if not value.is_file():
            raise PrivateBotSubmissionUnavailable(
                "private Bot submission input file is unavailable"
            )
        return _fingerprint_local_file(value)
    if isinstance(value, str):
        if input_key in _LOCAL_FILE_INPUT_KEYS:
            try:
                path = Path(value)
                if path.is_file():
                    return _fingerprint_local_file(path)
                if path.is_absolute():
                    raise PrivateBotSubmissionUnavailable(
                        "private Bot submission input file is unavailable"
                    )
            except (OSError, ValueError) as exc:
                raise PrivateBotSubmissionUnavailable(
                    "private Bot submission input file is unavailable"
                ) from exc
        return value
    if isinstance(value, dict):
        return {
            str(key): _canonicalize_request_value(
                nested,
                input_key=str(key),
            )
            for key, nested in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _canonicalize_request_value(nested, input_key=input_key)
            for nested in value
        ]
    if isinstance(value, (set, frozenset)):
        normalized = [
            _canonicalize_request_value(nested, input_key=input_key)
            for nested in value
        ]
        return sorted(
            normalized,
            key=lambda nested: json.dumps(
                nested,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
        )
    return value


def is_definitive_dispatch_rejection(error: BaseException) -> bool:
    """Return true only when Central/provider explicitly rejected the request."""

    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.HTTPStatusError):
            status_code = current.response.status_code
            return 400 <= status_code < 500 and status_code not in {
                408,
                425,
                429,
            }
        current = current.__cause__ or current.__context__
    return False


@dataclass(frozen=True, slots=True)
class PrivateBotSubmissionRequest:
    submission_key: str
    private_bot_id: int
    update_id: int
    sequence: int
    internal_user_id: int
    client_type: str
    task_type: str
    inputs: dict[str, Any]
    source_post_id: int | None
    deduct_quota: bool
    cost_override: int | None
    base_priority: int
    user_cancel_allowed: bool
    request_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "private_bot_id": self.private_bot_id,
            "update_id": self.update_id,
            "sequence": self.sequence,
            "internal_user_id": self.internal_user_id,
            "client_type": self.client_type,
            "task_type": self.task_type,
            "inputs": _canonicalize_request_value(self.inputs),
            "source_post_id": self.source_post_id,
            "deduct_quota": self.deduct_quota,
            "cost_override": self.cost_override,
            "base_priority": self.base_priority,
            "user_cancel_allowed": self.user_cancel_allowed,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        object.__setattr__(
            self,
            "request_sha256",
            hashlib.sha256(encoded).hexdigest(),
        )

    @property
    def registry_task_id(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, self.submission_key))


@dataclass(frozen=True, slots=True)
class PrivateBotSubmissionSnapshot:
    submission_key: str
    request_sha256: str
    registry_task_id: str
    dispatch_task_id: str
    backend_task_id: str | None
    status: str
    actual_cost: int | None
    saved_inputs: tuple[str, ...]
    debit_confirmed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    compensation_status: str = "not_required"
    compensation_attempts: int = 0
    compensation_last_error: str | None = None
    dispatch_started_at: datetime | None = None
    submission_owner_token: str | None = None
    submission_owner_deadline_at: datetime | None = None
    reconcile_not_before_at: datetime | None = None
    submission_owner_fence: int = 0
    private_bot_id: int = 0
    internal_user_id: int = 0
    client_type: str = ""
    task_type: str = ""

    @property
    def has_durable_dispatch_outcome(self) -> bool:
        return self.status in {"dispatching", "submitted"} and bool(
            self.dispatch_task_id
        )

    def as_task_result(self) -> dict[str, Any]:
        if (
            not self.has_durable_dispatch_outcome
            or self.actual_cost is None
            or not self.backend_task_id
        ):
            raise PrivateBotSubmissionUnavailable(
                "private Bot submission has no durable dispatch outcome"
            )
        return {
            "cost": int(self.actual_cost),
            "registry_task_id": self.registry_task_id,
            "backend_task_id": str(self.backend_task_id),
            "saved_inputs": list(self.saved_inputs),
        }


@dataclass(frozen=True, slots=True)
class PrivateBotDispatchReconciliation:
    confirmed: bool
    source: str | None
    definitively_missing: bool
    backend_task_id: str | None
    retry_after_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class PrivateBotRecoveryReconciliation:
    snapshot: PrivateBotSubmissionSnapshot | None
    confirmed: bool
    definitively_missing: bool
    backend_task_id: str | None
    retry_after_seconds: float | None = None


async def reconcile_private_bot_dispatching_submission(
    snapshot: PrivateBotSubmissionSnapshot,
    *,
    registry_lookup,
    backend_lookup,
    grace_seconds: float = PRIVATE_BOT_DISPATCH_RECONCILIATION_GRACE_SECONDS,
    now_func=datetime.now,
) -> PrivateBotDispatchReconciliation:
    """Confirm an uncertain deterministic dispatch without sending it again."""

    if snapshot.status != "dispatching" or not snapshot.dispatch_task_id:
        raise PrivateBotSubmissionConflict(
            "only a dispatching private Bot submission can be reconciled"
        )

    lookup_failed = False
    try:
        registry_task = await registry_lookup(snapshot.registry_task_id)
    except Exception:
        registry_task = None
        lookup_failed = True
    if registry_task:
        registry_backend_task_id = str(
            registry_task.get("backend_task_id") or snapshot.registry_task_id
        )
        if (
            snapshot.backend_task_id
            and registry_backend_task_id != snapshot.backend_task_id
        ):
            raise PrivateBotSubmissionConflict(
                "TaskRegistry backend outcome conflicts with the submission ledger"
            )
        if registry_task.get("backend_task_id"):
            return PrivateBotDispatchReconciliation(
                confirmed=True,
                source="task_registry",
                definitively_missing=False,
                backend_task_id=registry_backend_task_id,
            )

    lookup_task_id = snapshot.backend_task_id or snapshot.dispatch_task_id
    try:
        backend_task = await backend_lookup(lookup_task_id)
    except Exception:
        backend_task = None
        lookup_failed = True
    if backend_task is not None:
        return PrivateBotDispatchReconciliation(
            confirmed=True,
            source="backend",
            definitively_missing=False,
            backend_task_id=lookup_task_id,
        )
    now = now_func()
    if (
        snapshot.reconcile_not_before_at is not None
        and snapshot.reconcile_not_before_at > now
    ):
        return PrivateBotDispatchReconciliation(
            confirmed=False,
            source="dispatch_owner_fence",
            definitively_missing=False,
            backend_task_id=None,
            retry_after_seconds=(
                snapshot.reconcile_not_before_at - now
            ).total_seconds(),
        )
    if snapshot.dispatch_started_at is not None:
        elapsed_seconds = max(
            0.0,
            (now - snapshot.dispatch_started_at).total_seconds(),
        )
        remaining_grace = max(0.0, float(grace_seconds) - elapsed_seconds)
        if remaining_grace > 0:
            return PrivateBotDispatchReconciliation(
                confirmed=False,
                source="dispatch_grace",
                definitively_missing=False,
                backend_task_id=None,
                retry_after_seconds=remaining_grace,
            )
    return PrivateBotDispatchReconciliation(
        confirmed=False,
        source=None,
        definitively_missing=not lookup_failed,
        backend_task_id=None,
    )


class PrivateBotSubmissionRepository(Protocol):
    async def reserve(
        self, request: PrivateBotSubmissionRequest
    ) -> PrivateBotSubmissionSnapshot: ...

    async def get_by_registry_task_id(
        self,
        registry_task_id: str,
    ) -> PrivateBotSubmissionSnapshot | None: ...

    async def list_recovery_candidates(
        self,
        *,
        now: datetime,
        limit: int,
        active_registry_task_ids: set[str] | None = None,
    ) -> list[PrivateBotSubmissionSnapshot]: ...

    async def record_cost(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        actual_cost: int,
        owner_token: str | None,
        owner_deadline_at: datetime | None,
        reconcile_not_before_at: datetime | None,
    ) -> PrivateBotSubmissionSnapshot: ...

    async def claim_submission_owner(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        owner_token: str,
        owner_deadline_at: datetime,
        reconcile_not_before_at: datetime,
    ) -> PrivateBotSubmissionSnapshot: ...

    async def delete_terminal_before(
        self,
        *,
        cutoff: datetime,
        exclude_registry_task_ids: set[str],
        limit: int,
    ) -> int: ...

    async def mark_dispatching(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        dispatch_task_id: str,
        owner_token: str | None,
        owner_deadline_at: datetime | None,
        reconcile_not_before_at: datetime | None,
        actual_cost: int,
        saved_inputs: list[str],
    ) -> PrivateBotSubmissionSnapshot: ...

    async def mark_submitted(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        backend_task_id: str,
        owner_token: str | None,
        actual_cost: int,
        saved_inputs: list[str],
    ) -> PrivateBotSubmissionSnapshot: ...

    async def mark_failed_if_reserved(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        actual_cost: int,
        error_code: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot: ...

    async def mark_failed(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        actual_cost: int,
        error_code: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot: ...

    async def claim_compensation(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        lease_seconds: int,
    ) -> str | None: ...

    async def request_compensation(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        error_code: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot: ...

    async def complete_compensation(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        lease_token: str,
    ) -> PrivateBotSubmissionSnapshot: ...

    async def record_compensation_error(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        lease_token: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot: ...


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {
            "bytes_sha256": hashlib.sha256(value).hexdigest(),
            "length": len(value),
        }
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    return str(value)


def parse_private_bot_submission_key(submission_key: str) -> tuple[int, int, int]:
    parts = str(submission_key).split(":")
    if len(parts) != 4 or parts[0] != "private_bot_update":
        raise PrivateBotSubmissionConflict("invalid private Bot submission key")
    try:
        private_bot_id = int(parts[1])
        update_id = int(parts[2])
        sequence = int(parts[3])
    except (TypeError, ValueError) as exc:
        raise PrivateBotSubmissionConflict(
            "invalid private Bot submission key"
        ) from exc
    if private_bot_id <= 0 or update_id < 0 or sequence < 0:
        raise PrivateBotSubmissionConflict("invalid private Bot submission key")
    return private_bot_id, update_id, sequence


def build_private_bot_submission_request(
    *,
    submission_key: str,
    internal_user_id: int,
    client_type: str,
    task_type: str,
    inputs: dict[str, Any],
    source_post_id: int | None,
    deduct_quota: bool,
    cost_override: int | None,
    base_priority: int,
    user_cancel_allowed: bool,
) -> PrivateBotSubmissionRequest:
    private_bot_id, update_id, sequence = parse_private_bot_submission_key(
        submission_key
    )
    expected_client_type = f"bot:qqcc-private:{private_bot_id}"
    if client_type != expected_client_type:
        raise PrivateBotSubmissionConflict(
            "private Bot submission key and client type do not match"
        )
    return PrivateBotSubmissionRequest(
        submission_key=submission_key,
        private_bot_id=private_bot_id,
        update_id=update_id,
        sequence=sequence,
        internal_user_id=int(internal_user_id),
        client_type=client_type,
        task_type=str(task_type),
        inputs=dict(inputs),
        source_post_id=source_post_id,
        deduct_quota=bool(deduct_quota),
        cost_override=(int(cost_override) if cost_override is not None else None),
        base_priority=int(base_priority),
        user_cancel_allowed=bool(user_cancel_allowed),
    )


def _snapshot(row) -> PrivateBotSubmissionSnapshot:
    saved_inputs = row.saved_inputs if isinstance(row.saved_inputs, list) else []
    return PrivateBotSubmissionSnapshot(
        submission_key=str(row.submission_key),
        request_sha256=str(row.request_sha256),
        registry_task_id=str(row.registry_task_id),
        dispatch_task_id=str(row.dispatch_task_id),
        backend_task_id=(
            str(row.backend_task_id) if row.backend_task_id is not None else None
        ),
        status=str(row.status),
        actual_cost=(int(row.actual_cost) if row.actual_cost is not None else None),
        saved_inputs=tuple(str(value) for value in saved_inputs),
        debit_confirmed_at=row.debit_confirmed_at,
        error_code=(str(row.error_code) if row.error_code else None),
        error_message=(str(row.error_message) if row.error_message else None),
        compensation_status=str(row.compensation_status),
        compensation_attempts=int(row.compensation_attempts or 0),
        compensation_last_error=(
            str(row.compensation_last_error)
            if row.compensation_last_error
            else None
        ),
        dispatch_started_at=row.dispatch_started_at,
        submission_owner_token=(
            str(row.submission_owner_token)
            if row.submission_owner_token
            else None
        ),
        submission_owner_deadline_at=row.submission_owner_deadline_at,
        reconcile_not_before_at=row.reconcile_not_before_at,
        submission_owner_fence=int(row.submission_owner_fence or 0),
        private_bot_id=int(row.private_bot_id),
        internal_user_id=int(row.internal_user_id),
        client_type=str(row.client_type),
        task_type=str(row.task_type),
    )


def _assert_same_request(row, *, request_sha256: str, registry_task_id: str) -> None:
    if (
        str(row.request_sha256) != request_sha256
        or str(row.registry_task_id) != registry_task_id
    ):
        raise PrivateBotSubmissionConflict(
            "submission key was already used with different parameters"
        )


def _assert_same_outcome(
    row,
    *,
    backend_task_id: str | None,
    actual_cost: int,
    saved_inputs: list[str],
) -> None:
    if (
        backend_task_id is not None
        and row.backend_task_id is not None
        and str(row.backend_task_id) != backend_task_id
    ):
        raise PrivateBotSubmissionConflict("backend task outcome changed during replay")
    if row.actual_cost is not None and int(row.actual_cost) != int(actual_cost):
        raise PrivateBotSubmissionConflict("submission cost changed during replay")
    current_inputs = row.saved_inputs if isinstance(row.saved_inputs, list) else []
    if current_inputs and list(map(str, current_inputs)) != list(map(str, saved_inputs)):
        raise PrivateBotSubmissionConflict("saved inputs changed during replay")


class SqlAlchemyPrivateBotSubmissionRepository:
    def __init__(self, session_factory=None):
        if session_factory is None:
            from src.database.core import AsyncSessionLocal

            session_factory = AsyncSessionLocal
        self._session_factory = session_factory

    async def reserve(
        self, request: PrivateBotSubmissionRequest
    ) -> PrivateBotSubmissionSnapshot:
        from src.database.models import PrivateBotTaskSubmission

        values = {
            "submission_key": request.submission_key,
            "private_bot_id": request.private_bot_id,
            "update_id": request.update_id,
            "submission_sequence": request.sequence,
            "internal_user_id": request.internal_user_id,
            "client_type": request.client_type,
            "task_type": request.task_type,
            "request_sha256": request.request_sha256,
            "registry_task_id": request.registry_task_id,
            "dispatch_task_id": request.registry_task_id,
            "dispatch_started_at": None,
            "submission_owner_token": None,
            "submission_owner_deadline_at": None,
            "reconcile_not_before_at": None,
            "submission_owner_fence": 0,
            "backend_task_id": None,
            "status": "reserved",
            "saved_inputs": [],
            "compensation_status": "not_required",
            "compensation_attempts": 0,
        }
        async with self._session_factory() as session:
            await session.execute(
                insert(PrivateBotTaskSubmission)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["submission_key"])
            )
            await session.commit()
            result = await session.execute(
                select(PrivateBotTaskSubmission).where(
                    PrivateBotTaskSubmission.submission_key == request.submission_key
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise PrivateBotSubmissionUnavailable(
                    "private Bot submission reservation is unavailable"
                )
            _assert_same_request(
                row,
                request_sha256=request.request_sha256,
                registry_task_id=request.registry_task_id,
            )
            return _snapshot(row)

    async def get_by_registry_task_id(
        self,
        registry_task_id: str,
    ) -> PrivateBotSubmissionSnapshot | None:
        from src.database.models import PrivateBotTaskSubmission

        async with self._session_factory() as session:
            result = await session.execute(
                select(PrivateBotTaskSubmission).where(
                    PrivateBotTaskSubmission.registry_task_id
                    == str(registry_task_id)
                )
            )
            row = result.scalar_one_or_none()
            return _snapshot(row) if row is not None else None

    async def list_recovery_candidates(
        self,
        *,
        now: datetime,
        limit: int,
        active_registry_task_ids: set[str] | None = None,
    ) -> list[PrivateBotSubmissionSnapshot]:
        from src.database.models import PrivateBotTaskSubmission

        async with self._session_factory() as session:
            compensation_due = or_(
                PrivateBotTaskSubmission.compensation_status == "pending",
                and_(
                    PrivateBotTaskSubmission.compensation_status == "processing",
                    PrivateBotTaskSubmission.compensation_lease_until <= now,
                ),
            )
            orphan_due = and_(
                PrivateBotTaskSubmission.status.in_(("reserved", "dispatching")),
                PrivateBotTaskSubmission.reconcile_not_before_at <= now,
            )
            if active_registry_task_ids:
                orphan_due = and_(
                    orphan_due,
                    PrivateBotTaskSubmission.registry_task_id.not_in(
                        sorted(map(str, active_registry_task_ids))
                    ),
                )
            result = await session.execute(
                select(PrivateBotTaskSubmission)
                .where(or_(compensation_due, orphan_due))
                .order_by(PrivateBotTaskSubmission.id)
                .limit(max(1, int(limit)))
            )
            return [_snapshot(row) for row in result.scalars().all()]

    async def _locked_row(self, session, submission_key: str):
        from src.database.models import PrivateBotTaskSubmission

        result = await session.execute(
            select(PrivateBotTaskSubmission)
            .where(PrivateBotTaskSubmission.submission_key == submission_key)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise PrivateBotSubmissionUnavailable(
                "private Bot submission reservation is unavailable"
            )
        return row

    async def delete_terminal_before(
        self,
        *,
        cutoff: datetime,
        exclude_registry_task_ids: set[str],
        limit: int,
    ) -> int:
        from src.database.models import PrivateBotTaskSubmission

        terminal = or_(
            and_(
                PrivateBotTaskSubmission.status == "submitted",
                PrivateBotTaskSubmission.compensation_status == "not_required",
            ),
            and_(
                PrivateBotTaskSubmission.status == "failed",
                PrivateBotTaskSubmission.compensation_status == "completed",
            ),
        )
        candidate_query = (
            select(PrivateBotTaskSubmission.id)
            .where(
                terminal,
                PrivateBotTaskSubmission.updated_at < cutoff,
            )
            .order_by(PrivateBotTaskSubmission.id)
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        )
        if exclude_registry_task_ids:
            candidate_query = candidate_query.where(
                PrivateBotTaskSubmission.registry_task_id.not_in(
                    sorted(map(str, exclude_registry_task_ids))
                )
            )

        async with self._session_factory() as session:
            candidate_ids = list(
                (await session.execute(candidate_query)).scalars().all()
            )
            if not candidate_ids:
                return 0
            result = await session.execute(
                delete(PrivateBotTaskSubmission).where(
                    PrivateBotTaskSubmission.id.in_(candidate_ids)
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def mark_dispatching(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        dispatch_task_id: str,
        owner_token: str | None,
        owner_deadline_at: datetime | None,
        reconcile_not_before_at: datetime | None,
        actual_cost: int,
        saved_inputs: list[str],
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            _assert_same_outcome(
                row,
                backend_task_id=None,
                actual_cost=actual_cost,
                saved_inputs=saved_inputs,
            )
            if (
                owner_token
                and row.submission_owner_token
                and row.submission_owner_token != owner_token
            ):
                raise PrivateBotSubmissionConflict(
                    "private Bot dispatch ownership fence changed"
                )
            if owner_token and row.submission_owner_token == owner_token:
                row.submission_owner_deadline_at = owner_deadline_at
                row.reconcile_not_before_at = reconcile_not_before_at
            if row.status == "failed":
                raise PrivateBotSubmissionConflict(
                    "failed private Bot submission cannot be dispatched"
                )
            if row.status == "reserved":
                row.status = "dispatching"
                row.dispatch_task_id = dispatch_task_id
                row.dispatch_started_at = datetime.now()
                row.actual_cost = int(actual_cost)
                row.saved_inputs = list(map(str, saved_inputs))
                row.error_code = None
                row.error_message = None
            await session.commit()
            return _snapshot(row)

    async def record_cost(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        actual_cost: int,
        owner_token: str | None,
        owner_deadline_at: datetime | None,
        reconcile_not_before_at: datetime | None,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            if row.status != "reserved":
                raise PrivateBotSubmissionConflict(
                    "only a reserved private Bot submission can record cost"
                )
            if row.actual_cost is not None and int(row.actual_cost) != int(actual_cost):
                raise PrivateBotSubmissionConflict(
                    "submission cost changed during replay"
                )
            now = datetime.now()
            if owner_token:
                if (
                    row.submission_owner_token
                    and row.submission_owner_token != owner_token
                    and row.reconcile_not_before_at is not None
                    and row.reconcile_not_before_at > now
                ):
                    raise PrivateBotSubmissionUnavailable(
                        "private Bot submission is still owned by another dispatcher"
                    )
                if row.submission_owner_token != owner_token:
                    row.submission_owner_fence = int(
                        row.submission_owner_fence or 0
                    ) + 1
                row.submission_owner_token = owner_token
                row.submission_owner_deadline_at = owner_deadline_at
                row.reconcile_not_before_at = reconcile_not_before_at
            row.actual_cost = int(actual_cost)
            await session.commit()
            return _snapshot(row)

    async def claim_submission_owner(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        owner_token: str,
        owner_deadline_at: datetime,
        reconcile_not_before_at: datetime,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            if row.status != "reserved":
                raise PrivateBotSubmissionConflict(
                    "only a reserved private Bot submission can claim dispatch ownership"
                )
            now = datetime.now()
            if (
                row.submission_owner_token
                and row.submission_owner_token != owner_token
                and row.reconcile_not_before_at is not None
                and row.reconcile_not_before_at > now
            ):
                raise PrivateBotSubmissionUnavailable(
                    "private Bot submission is still owned by another dispatcher"
                )
            if row.submission_owner_token != owner_token:
                row.submission_owner_fence = int(row.submission_owner_fence or 0) + 1
            row.submission_owner_token = owner_token
            row.submission_owner_deadline_at = owner_deadline_at
            row.reconcile_not_before_at = reconcile_not_before_at
            await session.commit()
            return _snapshot(row)

    async def mark_submitted(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        backend_task_id: str,
        owner_token: str | None,
        actual_cost: int,
        saved_inputs: list[str],
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            _assert_same_outcome(
                row,
                backend_task_id=backend_task_id,
                actual_cost=actual_cost,
                saved_inputs=saved_inputs,
            )
            if (
                owner_token
                and row.submission_owner_token
                and row.submission_owner_token != owner_token
            ):
                raise PrivateBotSubmissionConflict(
                    "private Bot submitted outcome lost its dispatch ownership fence"
                )
            if row.status == "failed":
                raise PrivateBotSubmissionConflict(
                    "failed private Bot submission cannot become submitted"
                )
            row.status = "submitted"
            row.backend_task_id = backend_task_id
            row.actual_cost = int(actual_cost)
            row.saved_inputs = list(map(str, saved_inputs))
            row.error_code = None
            row.error_message = None
            await session.commit()
            return _snapshot(row)

    async def mark_failed_if_reserved(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        actual_cost: int,
        error_code: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=str(row.registry_task_id),
            )
            if row.actual_cost is not None and int(row.actual_cost) != int(actual_cost):
                raise PrivateBotSubmissionConflict(
                    "submission cost changed during replay"
                )
            if row.status == "reserved":
                row.status = "failed"
                row.actual_cost = int(actual_cost)
                row.error_code = str(error_code)[:64]
                row.error_message = str(error_message)[:500]
                row.compensation_status = "pending"
                row.compensation_lease_token = None
                row.compensation_lease_until = None
            await session.commit()
            return _snapshot(row)

    async def mark_failed(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        actual_cost: int,
        error_code: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=str(row.registry_task_id),
            )
            if row.actual_cost is not None and int(row.actual_cost) != int(actual_cost):
                raise PrivateBotSubmissionConflict(
                    "submission cost changed during replay"
                )
            if row.status != "submitted":
                first_failure = row.status != "failed"
                row.status = "failed"
                row.actual_cost = int(actual_cost)
                row.error_code = str(error_code)[:64]
                row.error_message = str(error_message)[:500]
                if first_failure or row.compensation_status == "not_required":
                    row.compensation_status = "pending"
                    row.compensation_lease_token = None
                    row.compensation_lease_until = None
            await session.commit()
            return _snapshot(row)

    async def claim_compensation(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        lease_seconds: int,
    ) -> str | None:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            if row.compensation_status == "not_required":
                raise PrivateBotSubmissionConflict(
                    "private Bot submission compensation was not requested"
                )
            now = datetime.now()
            if row.compensation_status == "completed":
                return None
            if (
                row.compensation_status == "processing"
                and row.compensation_lease_until is not None
                and row.compensation_lease_until > now
            ):
                return None
            lease_token = uuid.uuid4().hex
            row.compensation_status = "processing"
            row.compensation_lease_token = lease_token
            row.compensation_lease_until = now + timedelta(
                seconds=max(1, int(lease_seconds))
            )
            row.compensation_attempts = int(row.compensation_attempts or 0) + 1
            row.compensation_last_error = None
            await session.commit()
            return lease_token

    async def request_compensation(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        error_code: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            row.error_code = str(error_code)[:64]
            row.error_message = str(error_message)[:500]
            if row.compensation_status == "not_required":
                row.compensation_status = "pending"
                row.compensation_lease_token = None
                row.compensation_lease_until = None
            await session.commit()
            return _snapshot(row)

    async def complete_compensation(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        lease_token: str,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            if row.compensation_status == "completed":
                return _snapshot(row)
            if (
                row.compensation_status != "processing"
                or row.compensation_lease_token != lease_token
            ):
                raise PrivateBotSubmissionConflict(
                    "private Bot compensation lease ownership changed"
                )
            row.compensation_status = "completed"
            row.compensation_lease_token = None
            row.compensation_lease_until = None
            row.compensation_last_error = None
            row.compensation_completed_at = datetime.now()
            await session.commit()
            return _snapshot(row)

    async def record_compensation_error(
        self,
        *,
        submission_key: str,
        request_sha256: str,
        registry_task_id: str,
        lease_token: str,
        error_message: str,
    ) -> PrivateBotSubmissionSnapshot:
        async with self._session_factory() as session:
            row = await self._locked_row(session, submission_key)
            _assert_same_request(
                row,
                request_sha256=request_sha256,
                registry_task_id=registry_task_id,
            )
            if (
                row.compensation_status == "processing"
                and row.compensation_lease_token == lease_token
            ):
                row.compensation_last_error = str(error_message)[:500]
                row.compensation_lease_until = datetime.now()
            await session.commit()
            return _snapshot(row)


_default_repository: PrivateBotSubmissionRepository | None = None


def _repository() -> PrivateBotSubmissionRepository:
    global _default_repository
    if _default_repository is None:
        _default_repository = SqlAlchemyPrivateBotSubmissionRepository()
    return _default_repository


async def reserve_private_bot_submission(
    request: PrivateBotSubmissionRequest,
    *,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).reserve(request)


async def get_private_bot_submission_by_registry_task_id(
    registry_task_id: str,
    *,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot | None:
    return await (repository or _repository()).get_by_registry_task_id(
        str(registry_task_id)
    )


async def list_private_bot_submission_recovery_candidates(
    *,
    now: datetime | None = None,
    limit: int = 200,
    active_registry_task_ids: set[str] | None = None,
    repository: PrivateBotSubmissionRepository | None = None,
) -> list[PrivateBotSubmissionSnapshot]:
    return await (repository or _repository()).list_recovery_candidates(
        now=now or datetime.now(),
        limit=max(1, int(limit)),
        active_registry_task_ids=active_registry_task_ids,
    )


async def prune_private_bot_submission_ledger(
    *,
    active_registry_task_ids: set[str],
    now: datetime | None = None,
    retention_days: int = PRIVATE_BOT_SUBMISSION_RETENTION_DAYS,
    limit: int = PRIVATE_BOT_SUBMISSION_RETENTION_BATCH_SIZE,
    repository: PrivateBotSubmissionRepository | None = None,
) -> int:
    """Bound ledger growth without deleting recoverable or refundable rows."""

    safe_retention_days = max(30, int(retention_days))
    cutoff = (now or datetime.now()) - timedelta(days=safe_retention_days)
    return await (repository or _repository()).delete_terminal_before(
        cutoff=cutoff,
        exclude_registry_task_ids=set(map(str, active_registry_task_ids)),
        limit=max(1, int(limit)),
    )


async def reconcile_private_bot_recovery_submission(
    *,
    registry_task_id: str,
    registry_task: dict[str, Any],
    backend_lookup,
    update_registry_backend,
    repository: PrivateBotSubmissionRepository | None = None,
    grace_seconds: float = PRIVATE_BOT_DISPATCH_RECONCILIATION_GRACE_SECONDS,
    now_func=datetime.now,
) -> PrivateBotRecoveryReconciliation:
    repository = repository or _repository()
    snapshot = await repository.get_by_registry_task_id(str(registry_task_id))
    if snapshot is None:
        return PrivateBotRecoveryReconciliation(
            snapshot=None,
            confirmed=False,
            definitively_missing=False,
            backend_task_id=None,
        )

    if snapshot.status == "submitted" and snapshot.backend_task_id:
        await update_registry_backend(
            snapshot.registry_task_id,
            snapshot.backend_task_id,
        )
        return PrivateBotRecoveryReconciliation(
            snapshot=snapshot,
            confirmed=True,
            definitively_missing=False,
            backend_task_id=snapshot.backend_task_id,
        )
    if snapshot.status == "failed":
        return PrivateBotRecoveryReconciliation(
            snapshot=snapshot,
            confirmed=False,
            definitively_missing=True,
            backend_task_id=None,
        )
    if snapshot.status == "reserved":
        now = now_func()
        if (
            snapshot.reconcile_not_before_at is None
            or snapshot.reconcile_not_before_at > now
        ):
            retry_after = (
                (snapshot.reconcile_not_before_at - now).total_seconds()
                if snapshot.reconcile_not_before_at is not None
                else None
            )
            return PrivateBotRecoveryReconciliation(
                snapshot=snapshot,
                confirmed=False,
                definitively_missing=False,
                backend_task_id=None,
                retry_after_seconds=retry_after,
            )
        return PrivateBotRecoveryReconciliation(
            snapshot=snapshot,
            confirmed=False,
            definitively_missing=True,
            backend_task_id=None,
        )

    async def registry_lookup(_registry_task_id: str):
        return registry_task

    reconciliation = await reconcile_private_bot_dispatching_submission(
        snapshot,
        registry_lookup=registry_lookup,
        backend_lookup=backend_lookup,
        grace_seconds=grace_seconds,
        now_func=now_func,
    )
    if not reconciliation.confirmed:
        return PrivateBotRecoveryReconciliation(
            snapshot=snapshot,
            confirmed=False,
            definitively_missing=reconciliation.definitively_missing,
            backend_task_id=None,
            retry_after_seconds=reconciliation.retry_after_seconds,
        )

    backend_task_id = str(reconciliation.backend_task_id)
    submitted = await repository.mark_submitted(
        submission_key=snapshot.submission_key,
        request_sha256=snapshot.request_sha256,
        registry_task_id=snapshot.registry_task_id,
        backend_task_id=backend_task_id,
        owner_token=None,
        actual_cost=int(snapshot.actual_cost or 0),
        saved_inputs=list(snapshot.saved_inputs),
    )
    await update_registry_backend(submitted.registry_task_id, backend_task_id)
    return PrivateBotRecoveryReconciliation(
        snapshot=submitted,
        confirmed=True,
        definitively_missing=False,
        backend_task_id=backend_task_id,
    )


async def mark_private_bot_submission_dispatching(
    *,
    request: PrivateBotSubmissionRequest,
    registry_task_id: str,
    actual_cost: int,
    saved_inputs: list[str],
    owner_token: str | None = None,
    owner_deadline_at: datetime | None = None,
    reconcile_not_before_at: datetime | None = None,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    if registry_task_id != request.registry_task_id:
        raise PrivateBotSubmissionConflict(
            "private Bot registry task id must remain deterministic"
        )
    return await (repository or _repository()).mark_dispatching(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=registry_task_id,
        dispatch_task_id=registry_task_id,
        owner_token=owner_token,
        owner_deadline_at=owner_deadline_at,
        reconcile_not_before_at=reconcile_not_before_at,
        actual_cost=int(actual_cost),
        saved_inputs=saved_inputs,
    )


async def record_private_bot_submission_cost(
    *,
    request: PrivateBotSubmissionRequest,
    actual_cost: int,
    owner_token: str | None = None,
    owner_deadline_at: datetime | None = None,
    reconcile_not_before_at: datetime | None = None,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).record_cost(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        actual_cost=int(actual_cost),
        owner_token=owner_token,
        owner_deadline_at=owner_deadline_at,
        reconcile_not_before_at=reconcile_not_before_at,
    )


async def claim_private_bot_submission_owner(
    *,
    request: PrivateBotSubmissionRequest,
    owner_token: str,
    owner_deadline_at: datetime,
    reconcile_not_before_at: datetime,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    """Fence a reserved submission before acquiring any runtime resources."""

    return await (repository or _repository()).claim_submission_owner(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        owner_token=owner_token,
        owner_deadline_at=owner_deadline_at,
        reconcile_not_before_at=reconcile_not_before_at,
    )


async def mark_private_bot_submission_submitted(
    *,
    request: PrivateBotSubmissionRequest,
    result: dict[str, Any],
    owner_token: str | None = None,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    registry_task_id = str(result["registry_task_id"])
    backend_task_id = str(result.get("backend_task_id") or registry_task_id)
    if registry_task_id != request.registry_task_id:
        raise PrivateBotSubmissionConflict(
            "private Bot task outcome must use the deterministic task id"
        )
    return await (repository or _repository()).mark_submitted(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        owner_token=owner_token,
        actual_cost=int(result["cost"]),
        saved_inputs=list(result.get("saved_inputs") or []),
    )


async def mark_private_bot_submission_failed(
    *,
    request: PrivateBotSubmissionRequest,
    actual_cost: int,
    error_code: str,
    error_message: str,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).mark_failed(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        actual_cost=int(actual_cost),
        error_code=error_code,
        error_message=error_message,
    )


async def mark_private_bot_recovery_submission_failed(
    *,
    snapshot: PrivateBotSubmissionSnapshot,
    error_code: str,
    error_message: str,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).mark_failed(
        submission_key=snapshot.submission_key,
        request_sha256=snapshot.request_sha256,
        actual_cost=int(snapshot.actual_cost or 0),
        error_code=error_code,
        error_message=error_message,
    )


async def mark_private_bot_submission_failed_if_reserved(
    *,
    request: PrivateBotSubmissionRequest,
    actual_cost: int,
    error_code: str,
    error_message: str,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).mark_failed_if_reserved(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        actual_cost=int(actual_cost),
        error_code=error_code,
        error_message=error_message,
    )


async def claim_private_bot_submission_compensation(
    *,
    request: PrivateBotSubmissionRequest,
    lease_seconds: int = 60,
    repository: PrivateBotSubmissionRepository | None = None,
) -> str | None:
    return await (repository or _repository()).claim_compensation(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        lease_seconds=max(1, int(lease_seconds)),
    )


async def request_private_bot_submission_compensation(
    *,
    request: PrivateBotSubmissionRequest | PrivateBotSubmissionSnapshot,
    error_code: str,
    error_message: str,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).request_compensation(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        error_code=error_code,
        error_message=error_message,
    )


async def complete_private_bot_submission_compensation(
    *,
    request: PrivateBotSubmissionRequest,
    lease_token: str,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).complete_compensation(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        lease_token=lease_token,
    )


async def record_private_bot_submission_compensation_error(
    *,
    request: PrivateBotSubmissionRequest,
    lease_token: str,
    error_message: str,
    repository: PrivateBotSubmissionRepository | None = None,
) -> PrivateBotSubmissionSnapshot:
    return await (repository or _repository()).record_compensation_error(
        submission_key=request.submission_key,
        request_sha256=request.request_sha256,
        registry_task_id=request.registry_task_id,
        lease_token=lease_token,
        error_message=error_message,
    )
