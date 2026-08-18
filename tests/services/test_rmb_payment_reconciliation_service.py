from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.rmb_payment_reconciliation_service import (
    ClaimedRMBReconciliationJob,
    RMBPaymentReconciler,
    RMBReconciliationDependencies,
    build_rmb_payment_reconciler_if_enabled,
    retry_delay_seconds,
)
from src.services.rmb_payment_service import (
    RMBOrderQueryResult,
    RMBOrderQueryStatus,
)


def _job(*, attempt_count: int = 1):
    return ClaimedRMBReconciliationJob(
        job_id=11,
        order_id=22,
        out_trade_no="RMB-ORDER-1",
        expected_amount="30.00",
        payment_provider="HUANYUY",
        attempt_count=attempt_count,
        lease_token="lease-1",
        created_at=datetime(2026, 7, 28, 12, 0, 0),
    )


def _dependencies(*, claimed_jobs=None, query_result=None, fulfillment_status="success"):
    return RMBReconciliationDependencies(
        claim_jobs_func=AsyncMock(return_value=claimed_jobs or []),
        query_order_func=AsyncMock(return_value=query_result),
        fulfill_order_func=AsyncMock(
            return_value=SimpleNamespace(status=fulfillment_status)
        ),
        complete_job_func=AsyncMock(),
        reschedule_job_func=AsyncMock(),
        notify_func=AsyncMock(),
    )


@pytest.mark.parametrize(
    ("attempt_count", "expected"),
    [
        (1, 60),
        (2, 120),
        (3, 300),
        (4, 600),
        (5, 1800),
        (6, 3600),
        (20, 3600),
    ],
)
def test_retry_delay_seconds_uses_bounded_backoff(attempt_count, expected):
    assert retry_delay_seconds(attempt_count) == expected


@pytest.mark.asyncio
async def test_reconciler_fulfills_verified_paid_order_and_completes_job():
    paid = RMBOrderQueryResult(
        status=RMBOrderQueryStatus.PAID,
        out_trade_no="RMB-ORDER-1",
        external_trade_no="gateway-1",
        paid_amount="30.00",
    )
    dependencies = _dependencies(claimed_jobs=[_job()], query_result=paid)
    reconciler = RMBPaymentReconciler(
        dependencies=dependencies,
        query_url="https://gateway.test/query",
    )

    processed = await reconciler.run_once()

    assert processed == 1
    dependencies.query_order_func.assert_awaited_once_with(
        provider="HUANYUY",
        out_trade_no="RMB-ORDER-1",
        expected_amount="30.00",
        query_url="https://gateway.test/query",
    )
    dependencies.fulfill_order_func.assert_awaited_once_with(
        "RMB-ORDER-1",
        "gateway-1",
        "30.00",
        source="rmb_payment_reconciliation",
    )
    dependencies.complete_job_func.assert_awaited_once_with(
        _job(),
        outcome="fulfilled",
    )
    dependencies.notify_func.assert_awaited_once()
    dependencies.reschedule_job_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciler_completes_duplicate_without_notifying_again():
    paid = RMBOrderQueryResult(
        status=RMBOrderQueryStatus.PAID,
        out_trade_no="RMB-ORDER-1",
        external_trade_no="gateway-1",
        paid_amount="30.00",
    )
    dependencies = _dependencies(
        claimed_jobs=[_job()],
        query_result=paid,
        fulfillment_status="noop",
    )
    reconciler = RMBPaymentReconciler(
        dependencies=dependencies,
        query_url="https://gateway.test/query",
    )

    await reconciler.run_once()

    dependencies.complete_job_func.assert_awaited_once_with(
        _job(),
        outcome="already_fulfilled",
    )
    dependencies.notify_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciler_reschedules_unpaid_order_with_backoff():
    unpaid = RMBOrderQueryResult(
        status=RMBOrderQueryStatus.NOT_PAID,
        out_trade_no="RMB-ORDER-1",
    )
    dependencies = _dependencies(claimed_jobs=[_job(attempt_count=3)], query_result=unpaid)
    reconciler = RMBPaymentReconciler(
        dependencies=dependencies,
        query_url="https://gateway.test/query",
    )

    await reconciler.run_once()

    dependencies.fulfill_order_func.assert_not_awaited()
    dependencies.complete_job_func.assert_not_awaited()
    dependencies.reschedule_job_func.assert_awaited_once_with(
        _job(attempt_count=3),
        delay_seconds=300,
        error_code=None,
    )


@pytest.mark.asyncio
async def test_reconciler_reschedules_gateway_error_without_exposing_message():
    dependencies = _dependencies(claimed_jobs=[_job()])
    dependencies.query_order_func.side_effect = ValueError(
        "secret gateway response body"
    )
    reconciler = RMBPaymentReconciler(
        dependencies=dependencies,
        query_url="https://gateway.test/query",
    )

    await reconciler.run_once()

    dependencies.reschedule_job_func.assert_awaited_once_with(
        _job(),
        delay_seconds=60,
        error_code="ValueError",
    )
    dependencies.complete_job_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_failure_does_not_reschedule_completed_payment():
    paid = RMBOrderQueryResult(
        status=RMBOrderQueryStatus.PAID,
        out_trade_no="RMB-ORDER-1",
        external_trade_no="gateway-1",
        paid_amount="30.00",
    )
    dependencies = _dependencies(claimed_jobs=[_job()], query_result=paid)
    dependencies.notify_func.side_effect = RuntimeError("telegram unavailable")
    reconciler = RMBPaymentReconciler(
        dependencies=dependencies,
        query_url="https://gateway.test/query",
    )

    await reconciler.run_once()

    dependencies.complete_job_func.assert_awaited_once_with(
        _job(),
        outcome="fulfilled",
    )
    dependencies.reschedule_job_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciler_claims_with_configured_batch_and_lease():
    dependencies = _dependencies()
    now = datetime(2026, 7, 28, 13, 0, 0)
    reconciler = RMBPaymentReconciler(
        dependencies=dependencies,
        query_url="https://gateway.test/query",
        batch_size=17,
        lease_seconds=75,
        now_func=lambda: now,
    )

    await reconciler.run_once()

    dependencies.claim_jobs_func.assert_awaited_once_with(
        now=now,
        batch_size=17,
        lease_until=now + timedelta(seconds=75),
        max_age=timedelta(hours=24),
    )


def test_reconciler_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RMB_RECONCILIATION_ENABLED", raising=False)

    assert build_rmb_payment_reconciler_if_enabled() is None


def test_reconciler_fails_startup_when_enabled_without_query_url(monkeypatch):
    monkeypatch.setenv("RMB_RECONCILIATION_ENABLED", "true")
    monkeypatch.setattr(
        "src.services.rmb_payment_reconciliation_service.HUANYUY_QUERY_URL",
        None,
    )

    with pytest.raises(RuntimeError):
        build_rmb_payment_reconciler_if_enabled()
