from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from src.services.media_archive_service import (
    claim_archive_jobs,
    renew_archive_lease,
    renew_restore_lease,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, outbox):
        self.outbox = outbox
        self.commits = 0

    async def execute(self, _statement):
        return _Result(self.outbox)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_renew_archive_lease_extends_only_owned_revision():
    outbox = SimpleNamespace(
        status="leased",
        lease_owner="worker-1",
        revision=3,
        lease_expires_at=None,
    )
    session = _Session(outbox)

    expires_at = await renew_archive_lease(
        session,
        history_id=1,
        worker_id="worker-1",
        revision=3,
        lease_seconds=900,
    )

    assert outbox.lease_expires_at == expires_at
    assert session.commits == 1


@pytest.mark.asyncio
async def test_renew_archive_lease_rejects_stale_revision():
    outbox = SimpleNamespace(
        status="leased",
        lease_owner="worker-1",
        revision=4,
        lease_expires_at=None,
    )

    with pytest.raises(ValueError, match="revision changed"):
        await renew_archive_lease(
            _Session(outbox),
            history_id=1,
            worker_id="worker-1",
            revision=3,
        )


@pytest.mark.asyncio
async def test_renew_restore_lease_extends_only_owned_revision():
    outbox = SimpleNamespace(
        status="leased",
        lease_owner="restore-1",
        revision=2,
        lease_expires_at=None,
    )
    session = _Session(outbox)

    expires_at = await renew_restore_lease(
        session,
        history_id=1,
        worker_id="restore-1",
        revision=2,
    )

    assert outbox.lease_expires_at == expires_at
    assert session.commits == 1


@pytest.mark.asyncio
async def test_claim_archive_jobs_can_be_limited_to_exact_history_ids():
    class Result:
        def all(self):
            return []

    class Session:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return Result()

        async def commit(self):
            return None

    session = Session()
    await claim_archive_jobs(
        session,
        worker_id="canary-worker",
        limit=100,
        history_ids=(11, 22, 33),
    )

    compiled = session.statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    assert "media_archive_outbox.history_id IN (11, 22, 33)" in sql
