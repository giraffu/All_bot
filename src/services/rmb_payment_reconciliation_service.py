from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update

from src.database.core import AsyncSessionLocal
from src.database.models import Order, RMBPaymentReconciliationJob
from src.services.payment_fulfillment_service import (
    deliver_rmb_payment_success_notification,
    fulfill_rmb_order,
)
from src.services.rmb_payment_service import (
    HUANYUY_QUERY_URL,
    RMBOrderQueryStatus,
)
from src.services.rmb_payment_provider_service import HUANYUY, query_rmb_order

logger = logging.getLogger("rmb_payment_reconciliation")
RETRY_DELAYS_SECONDS = (60, 120, 300, 600, 1800, 3600)


@dataclass(frozen=True)
class ClaimedRMBReconciliationJob:
    job_id: int
    order_id: int
    out_trade_no: str
    expected_amount: Any
    payment_provider: str
    attempt_count: int
    lease_token: str
    created_at: datetime


@dataclass(frozen=True)
class RMBReconciliationDependencies:
    claim_jobs_func: Callable[..., Awaitable[list[ClaimedRMBReconciliationJob]]]
    query_order_func: Callable[..., Awaitable[Any]]
    fulfill_order_func: Callable[..., Awaitable[Any]]
    complete_job_func: Callable[..., Awaitable[None]]
    reschedule_job_func: Callable[..., Awaitable[None]]
    notify_func: Callable[..., Awaitable[None]]


def retry_delay_seconds(attempt_count: int) -> int:
    index = max(0, min(int(attempt_count) - 1, len(RETRY_DELAYS_SECONDS) - 1))
    return RETRY_DELAYS_SECONDS[index]


def is_rmb_reconciliation_enabled() -> bool:
    return os.getenv("RMB_RECONCILIATION_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _order_log_key(out_trade_no: str) -> str:
    return hashlib.sha256(out_trade_no.encode("utf-8")).hexdigest()[:12]


async def _finalize_inactive_jobs(
    session,
    *,
    now: datetime,
    max_age: timedelta,
) -> None:
    active_statuses = ("pending", "processing")
    successful_order_ids = select(Order.id).where(Order.status == "SUCCESS")
    await session.execute(
        update(RMBPaymentReconciliationJob)
        .where(
            RMBPaymentReconciliationJob.status.in_(active_statuses),
            RMBPaymentReconciliationJob.order_id.in_(successful_order_ids),
        )
        .values(
            status="completed",
            last_outcome="fulfilled_elsewhere",
            completed_at=now,
            lease_token=None,
            lease_until=None,
            updated_at=now,
        )
    )
    await session.execute(
        update(RMBPaymentReconciliationJob)
        .where(
            RMBPaymentReconciliationJob.status.in_(active_statuses),
            RMBPaymentReconciliationJob.created_at <= now - max_age,
            or_(
                RMBPaymentReconciliationJob.lease_until.is_(None),
                RMBPaymentReconciliationJob.lease_until < now,
            ),
        )
        .values(
            status="exhausted",
            last_outcome="max_age_exceeded",
            completed_at=now,
            lease_token=None,
            lease_until=None,
            updated_at=now,
        )
    )


async def claim_due_rmb_reconciliation_jobs(
    *,
    now: datetime,
    batch_size: int,
    lease_until: datetime,
    max_age: timedelta,
) -> list[ClaimedRMBReconciliationJob]:
    lease_token = uuid.uuid4().hex
    async with AsyncSessionLocal() as session:
        await _finalize_inactive_jobs(session, now=now, max_age=max_age)
        rows = (
            await session.execute(
                select(RMBPaymentReconciliationJob, Order)
                .join(Order, Order.id == RMBPaymentReconciliationJob.order_id)
                .where(
                    RMBPaymentReconciliationJob.status.in_(
                        ("pending", "processing")
                    ),
                    RMBPaymentReconciliationJob.next_attempt_at <= now,
                    RMBPaymentReconciliationJob.created_at > now - max_age,
                    or_(
                        RMBPaymentReconciliationJob.lease_until.is_(None),
                        RMBPaymentReconciliationJob.lease_until < now,
                    ),
                    Order.status == "PENDING",
                    Order.payment_channel == "RMB",
                )
                .order_by(
                    RMBPaymentReconciliationJob.next_attempt_at,
                    RMBPaymentReconciliationJob.id,
                )
                .with_for_update(
                    skip_locked=True,
                    of=RMBPaymentReconciliationJob,
                )
                .limit(batch_size)
            )
        ).all()

        claimed = []
        for job, order in rows:
            job.status = "processing"
            job.attempt_count = int(job.attempt_count or 0) + 1
            job.lease_token = lease_token
            job.lease_until = lease_until
            job.last_checked_at = now
            job.updated_at = now
            claimed.append(
                ClaimedRMBReconciliationJob(
                    job_id=job.id,
                    order_id=order.id,
                    out_trade_no=str(order.order_id),
                    expected_amount=order.final_price,
                    payment_provider=order.payment_provider or HUANYUY,
                    attempt_count=job.attempt_count,
                    lease_token=lease_token,
                    created_at=job.created_at,
                )
            )
        await session.commit()
        return claimed


async def complete_rmb_reconciliation_job(
    job: ClaimedRMBReconciliationJob,
    *,
    outcome: str,
) -> None:
    now = datetime.now()
    async with AsyncSessionLocal() as session:
        target = (
            await session.execute(
                select(RMBPaymentReconciliationJob)
                .where(
                    RMBPaymentReconciliationJob.id == job.job_id,
                    RMBPaymentReconciliationJob.status == "processing",
                    RMBPaymentReconciliationJob.lease_token == job.lease_token,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if target is None:
            return
        target.status = "completed"
        target.last_outcome = outcome[:100]
        target.last_error_code = None
        target.completed_at = now
        target.lease_token = None
        target.lease_until = None
        target.updated_at = now
        await session.commit()


async def reschedule_rmb_reconciliation_job(
    job: ClaimedRMBReconciliationJob,
    *,
    delay_seconds: int,
    error_code: str | None,
) -> None:
    now = datetime.now()
    async with AsyncSessionLocal() as session:
        target = (
            await session.execute(
                select(RMBPaymentReconciliationJob)
                .where(
                    RMBPaymentReconciliationJob.id == job.job_id,
                    RMBPaymentReconciliationJob.status == "processing",
                    RMBPaymentReconciliationJob.lease_token == job.lease_token,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if target is None:
            return
        target.status = "pending"
        target.next_attempt_at = now + timedelta(seconds=delay_seconds)
        target.last_error_code = error_code[:100] if error_code else None
        target.last_outcome = "retry_scheduled"
        target.lease_token = None
        target.lease_until = None
        target.updated_at = now
        await session.commit()


def build_default_rmb_reconciliation_dependencies() -> RMBReconciliationDependencies:
    return RMBReconciliationDependencies(
        claim_jobs_func=claim_due_rmb_reconciliation_jobs,
        query_order_func=query_rmb_order,
        fulfill_order_func=fulfill_rmb_order,
        complete_job_func=complete_rmb_reconciliation_job,
        reschedule_job_func=reschedule_rmb_reconciliation_job,
        notify_func=deliver_rmb_payment_success_notification,
    )


class RMBPaymentReconciler:
    def __init__(
        self,
        *,
        dependencies: RMBReconciliationDependencies | None = None,
        query_url: str,
        poll_interval_seconds: int = 30,
        batch_size: int = 50,
        concurrency: int = 5,
        lease_seconds: int = 60,
        max_age: timedelta = timedelta(hours=24),
        now_func: Callable[[], datetime] = datetime.now,
    ):
        if not query_url:
            raise ValueError("HUANYUY_QUERY_URL is required")
        self.dependencies = (
            dependencies or build_default_rmb_reconciliation_dependencies()
        )
        self.query_url = query_url
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))
        self.batch_size = max(1, int(batch_size))
        self.concurrency = max(1, int(concurrency))
        self.lease_seconds = max(1, int(lease_seconds))
        self.max_age = max_age
        self.now_func = now_func

    async def _process_job(self, job: ClaimedRMBReconciliationJob) -> None:
        try:
            query_result = await self.dependencies.query_order_func(
                provider=job.payment_provider,
                out_trade_no=job.out_trade_no,
                expected_amount=job.expected_amount,
                query_url=self.query_url,
            )
            if query_result.status == RMBOrderQueryStatus.NOT_PAID:
                await self.dependencies.reschedule_job_func(
                    job,
                    delay_seconds=retry_delay_seconds(job.attempt_count),
                    error_code=None,
                )
                return

            result = await self.dependencies.fulfill_order_func(
                job.out_trade_no,
                query_result.external_trade_no,
                query_result.paid_amount,
                source="rmb_payment_reconciliation",
            )
            if result.status == "success":
                await self.dependencies.complete_job_func(
                    job,
                    outcome="fulfilled",
                )
                try:
                    await self.dependencies.notify_func(result)
                except Exception as exc:
                    logger.warning(
                        "RMB reconciliation notification failed "
                        "order_key=%s error_type=%s",
                        _order_log_key(job.out_trade_no),
                        type(exc).__name__,
                    )
                return
            if result.status == "noop":
                await self.dependencies.complete_job_func(
                    job,
                    outcome="already_fulfilled",
                )
                return
            raise ValueError(f"unexpected fulfillment status: {result.status}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "RMB reconciliation attempt failed order_key=%s "
                "attempt=%d error_type=%s",
                _order_log_key(job.out_trade_no),
                job.attempt_count,
                type(exc).__name__,
            )
            await self.dependencies.reschedule_job_func(
                job,
                delay_seconds=retry_delay_seconds(job.attempt_count),
                error_code=type(exc).__name__,
            )

    async def run_once(self) -> int:
        now = self.now_func()
        jobs = await self.dependencies.claim_jobs_func(
            now=now,
            batch_size=self.batch_size,
            lease_until=now + timedelta(seconds=self.lease_seconds),
            max_age=self.max_age,
        )
        semaphore = asyncio.Semaphore(self.concurrency)

        async def _bounded(job):
            async with semaphore:
                await self._process_job(job)

        await asyncio.gather(*(_bounded(job) for job in jobs))
        return len(jobs)

    async def run_forever(self) -> None:
        logger.info("RMB payment reconciler started")
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "RMB reconciliation sweep failed error_type=%s",
                    type(exc).__name__,
                )
            await asyncio.sleep(self.poll_interval_seconds)


def build_rmb_payment_reconciler_if_enabled() -> RMBPaymentReconciler | None:
    if not is_rmb_reconciliation_enabled():
        return None
    if not HUANYUY_QUERY_URL:
        raise RuntimeError(
            "RMB_RECONCILIATION_ENABLED requires HUANYUY_QUERY_URL"
        )
    return RMBPaymentReconciler(query_url=HUANYUY_QUERY_URL)
