from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import private_bot_task_finalization


@pytest.mark.asyncio
async def test_cross_reason_private_full_refund_reuses_one_persistent_identity(
    monkeypatch,
):
    snapshot = SimpleNamespace(
        submission_key="private_bot_update:7:9:0",
        request_sha256="a" * 64,
        registry_task_id="deterministic-task",
        compensation_status="pending",
    )
    request_compensation = AsyncMock(return_value=snapshot)
    claim = AsyncMock(side_effect=["lease-one", "lease-two"])
    complete = AsyncMock()
    record_error = AsyncMock()
    monkeypatch.setattr(
        private_bot_task_finalization.private_bot_submission_ledger,
        "request_private_bot_submission_compensation",
        request_compensation,
    )
    monkeypatch.setattr(
        private_bot_task_finalization.private_bot_submission_ledger,
        "claim_private_bot_submission_compensation",
        claim,
    )
    monkeypatch.setattr(
        private_bot_task_finalization.private_bot_submission_ledger,
        "complete_private_bot_submission_compensation",
        complete,
    )
    monkeypatch.setattr(
        private_bot_task_finalization.private_bot_submission_ledger,
        "record_private_bot_submission_compensation_error",
        record_error,
    )

    credited_identities = set()
    refund_calls = []

    async def idempotent_refund(_user_id, _cost, **kwargs):
        identity = (kwargs["task_type"], kwargs["idempotency_key"])
        refund_calls.append(identity)
        first_application = identity not in credited_identities
        credited_identities.add(identity)
        return first_application

    cleanup = AsyncMock(side_effect=[RuntimeError("crash after refund"), None])

    with pytest.raises(RuntimeError, match="crash after refund"):
        await private_bot_task_finalization.finalize_private_bot_submission(
            request=snapshot,
            internal_user_id=123,
            username="visitor",
            actual_cost=6,
            registry_task_id="deterministic-task",
            credits_deducted=True,
            reason_code="recovery_failed",
            reason_message="recovery failed",
            refund_credits_func=idempotent_refund,
            cleanup_task_runtime_state_func=cleanup,
        )

    result = await private_bot_task_finalization.finalize_private_bot_submission(
        request=snapshot,
        internal_user_id=123,
        username="visitor",
        actual_cost=6,
        registry_task_id="deterministic-task",
        credits_deducted=True,
        reason_code="zombie_timeout",
        reason_message="zombie retry",
        refund_credits_func=idempotent_refund,
        cleanup_task_runtime_state_func=cleanup,
    )

    expected_identity = (
        "refund_private_submission",
        "task_refund:task:deterministic-task",
    )
    assert refund_calls == [expected_identity, expected_identity]
    assert credited_identities == {expected_identity}
    assert result.completed is True
    complete.assert_awaited_once_with(
        request=snapshot,
        lease_token="lease-two",
    )
