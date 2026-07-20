import asyncio

import httpx
import pytest

from src.web_api.services.r2_public_probe_service import R2PublicProbeService


class _FakeClient:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.head_calls = []
        self.closed = False

    async def head(self, url, **_kwargs):
        self.head_calls.append(url)
        await asyncio.sleep(0)
        status = self.statuses.pop(0) if self.statuses else 200
        return httpx.Response(status, request=httpx.Request("HEAD", url))

    async def get(self, url, **_kwargs):
        return httpx.Response(206, request=httpx.Request("GET", url))

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_same_key_100_concurrent_probes_issue_one_public_head():
    client = _FakeClient([200])
    service = R2PublicProbeService(client=client)

    results = await asyncio.gather(
        *(
            service.probe(
                "history/task-1/original.png",
                "https://r2.example/history/task-1/original.png",
                timeout_seconds=2.5,
            )
            for _ in range(100)
        )
    )

    assert all(results)
    assert len(client.head_calls) == 1


@pytest.mark.asyncio
async def test_positive_and_404_results_use_separate_ttls():
    now = [100.0]
    client = _FakeClient([404, 404, 200, 200])
    service = R2PublicProbeService(
        client=client,
        positive_ttl_seconds=60,
        negative_ttl_seconds=5,
        clock=lambda: now[0],
    )
    key = "history/task-1/original.png"
    url = "https://r2.example/history/task-1/original.png"

    assert await service.probe(key, url, timeout_seconds=2.5) is False
    now[0] += 4
    assert await service.probe(key, url, timeout_seconds=2.5) is False
    assert len(client.head_calls) == 1
    now[0] += 2
    assert await service.probe(key, url, timeout_seconds=2.5) is False
    assert len(client.head_calls) == 2
    now[0] += 6
    assert await service.probe(key, url, timeout_seconds=2.5) is True
    now[0] += 59
    assert await service.probe(key, url, timeout_seconds=2.5) is True
    assert len(client.head_calls) == 3
    now[0] += 2
    assert await service.probe(key, url, timeout_seconds=2.5) is True
    assert len(client.head_calls) == 4


@pytest.mark.asyncio
async def test_service_closes_reused_http_client():
    client = _FakeClient([200])
    service = R2PublicProbeService(client=client)

    await service.close()

    assert client.closed is True
