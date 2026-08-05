from types import SimpleNamespace

import pytest

from src.services.media_archive_service import renew_archive_lease


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
