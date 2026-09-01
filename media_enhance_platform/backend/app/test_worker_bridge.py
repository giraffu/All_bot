from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

import boto3
import httpx

from .config import get_settings


logger = logging.getLogger(__name__)
PROVIDER_NAME = "allbot-test-central"
VIDEO_TASK_TYPE = "video_upscale"


class PlatformAttemptInactive(RuntimeError):
    """The Clarity task was canceled or superseded while the bridge was working."""


class PlatformApi(Protocol):
    async def heartbeat(self) -> None: ...

    async def claim_task(self) -> dict | None: ...

    async def bind_provider_task(
        self, attempt_id: str, provider: str, provider_task_id: str
    ) -> None: ...

    async def report_progress(
        self, attempt_id: str, status: str, progress: int
    ) -> None: ...

    async def download_source(self, download_path: str, destination: Path) -> None: ...

    async def complete(self, attempt_id: str, result_path: Path) -> None: ...

    async def fail(
        self, attempt_id: str, error_code: str, error_detail: str, retryable: bool
    ) -> None: ...


class CentralApi(Protocol):
    async def get_status(self, task_id: str) -> dict | None: ...

    async def submit_video_upscale(self, payload: dict) -> None: ...

    async def cancel(self, task_id: str) -> None: ...

    async def download_result(self, task_id: str, destination: Path) -> None: ...


class InputStore(Protocol):
    async def upload(
        self, object_key: str, source: Path, content_type: str
    ) -> None: ...


class TestWorkerBridge:
    __test__ = False

    def __init__(
        self,
        platform: PlatformApi,
        central: CentralApi,
        input_store: InputStore,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        poll_seconds: float = 3.0,
    ) -> None:
        self.platform = platform
        self.central = central
        self.input_store = input_store
        self.sleep = sleep
        self.poll_seconds = poll_seconds

    @staticmethod
    def provider_task_id(claim: dict) -> str:
        return f"clarity-{claim['task_id']}-{claim['attempt_id']}"

    @staticmethod
    def input_object_key(claim: dict) -> str:
        return (
            f"clarity-test-inputs/{claim['task_id']}/"
            f"{claim['attempt_id']}.mp4"
        )

    async def _report_or_cancel(
        self,
        *,
        attempt_id: str,
        provider_task_id: str,
        status: str,
        progress: int,
    ) -> bool:
        try:
            await self.platform.report_progress(attempt_id, status, progress)
            return True
        except PlatformAttemptInactive:
            await self.central.cancel(provider_task_id)
            return False

    async def _prepare_and_submit(
        self, claim: dict, provider_task_id: str
    ) -> bool:
        attempt_id = claim["attempt_id"]
        if not await self._report_or_cancel(
            attempt_id=attempt_id,
            provider_task_id=provider_task_id,
            status="preprocessing",
            progress=5,
        ):
            return False
        source = claim.get("source") or {}
        download_path = str(source.get("download_path") or "")
        if not download_path:
            await self.platform.fail(
                attempt_id,
                "source_missing",
                "The source video download path is missing.",
                False,
            )
            return False
        content_type = str(source.get("mime_type") or "video/mp4")
        object_key = self.input_object_key(claim)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as source_file:
            source_path = Path(source_file.name)
            await self.platform.download_source(download_path, source_path)
            await self.input_store.upload(object_key, source_path, content_type)
        await self.central.submit_video_upscale(
            {
                "task_id": provider_task_id,
                "video": object_key,
                "prompt": "",
                "length": 5,
                "priority": 0,
            }
        )
        return True

    async def _follow_provider_task(
        self, claim: dict, provider_task_id: str, status: dict | None
    ) -> None:
        attempt_id = claim["attempt_id"]
        snapshot = status
        while True:
            if snapshot is None:
                snapshot = await self.central.get_status(provider_task_id)
                if snapshot is None:
                    await self.sleep(self.poll_seconds)
                    continue
            state = str(snapshot.get("status") or "").lower()
            progress = max(0, min(100, int(float(snapshot.get("progress") or 0))))
            if state == "pending":
                active = await self._report_or_cancel(
                    attempt_id=attempt_id,
                    provider_task_id=provider_task_id,
                    status="preprocessing",
                    progress=max(10, min(progress, 20)),
                )
            elif state == "running":
                active = await self._report_or_cancel(
                    attempt_id=attempt_id,
                    provider_task_id=provider_task_id,
                    status="running",
                    progress=max(20, min(progress, 94)),
                )
            elif state == "done":
                active = await self._report_or_cancel(
                    attempt_id=attempt_id,
                    provider_task_id=provider_task_id,
                    status="uploading",
                    progress=95,
                )
                if not active:
                    return
                with tempfile.NamedTemporaryFile(suffix=".mp4") as result_file:
                    result_path = Path(result_file.name)
                    await self.central.download_result(provider_task_id, result_path)
                    try:
                        await self.platform.complete(attempt_id, result_path)
                    except PlatformAttemptInactive:
                        await self.central.cancel(provider_task_id)
                return
            elif state in {"error", "cancelled", "canceled"}:
                await self.platform.fail(
                    attempt_id,
                    "test_worker_failed" if state == "error" else "provider_cancelled",
                    str(snapshot.get("error") or state),
                    True,
                )
                return
            else:
                active = True
            if not active:
                return
            await self.sleep(self.poll_seconds)
            snapshot = await self.central.get_status(provider_task_id)

    async def run_once(self) -> bool:
        await self.platform.heartbeat()
        claim = await self.platform.claim_task()
        if claim is None:
            return False
        if claim.get("task_type") != VIDEO_TASK_TYPE or claim.get("multiplier") != 2:
            await self.platform.fail(
                claim["attempt_id"],
                "unsupported_bridge_task",
                "The test bridge only accepts 2x video_upscale tasks.",
                False,
            )
            return True

        provider_task_id = str(
            claim.get("provider_task_id") or self.provider_task_id(claim)
        )
        if not claim.get("provider_task_id"):
            await self.platform.bind_provider_task(
                claim["attempt_id"], PROVIDER_NAME, provider_task_id
            )
        status = await self.central.get_status(provider_task_id)
        if status is None:
            if not await self._prepare_and_submit(claim, provider_task_id):
                return True
            status = await self.central.get_status(provider_task_id)
        await self._follow_provider_task(claim, provider_task_id, status)
        return True


class HttpPlatformApi:
    def __init__(
        self, base_url: str, agent_token: str, worker_id: str, client: httpx.AsyncClient
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self.client = client
        self.agent_headers = {"X-Agent-Token": agent_token}
        self.owned_headers = {**self.agent_headers, "X-Worker-Id": worker_id}

    async def heartbeat(self) -> None:
        response = await self.client.post(
            f"{self.base_url}/worker/heartbeat",
            headers=self.agent_headers,
            json={"worker_id": self.worker_id, "capabilities": [VIDEO_TASK_TYPE]},
        )
        response.raise_for_status()

    async def claim_task(self) -> dict | None:
        response = await self.client.post(
            f"{self.base_url}/worker/tasks/claim",
            headers=self.agent_headers,
            json={"worker_id": self.worker_id},
        )
        response.raise_for_status()
        return response.json()

    async def bind_provider_task(
        self, attempt_id: str, provider: str, provider_task_id: str
    ) -> None:
        response = await self.client.post(
            f"{self.base_url}/worker/attempts/{attempt_id}/provider",
            headers=self.owned_headers,
            json={"provider": provider, "provider_task_id": provider_task_id},
        )
        if response.status_code in {404, 409}:
            raise PlatformAttemptInactive
        response.raise_for_status()

    async def report_progress(self, attempt_id: str, status: str, progress: int) -> None:
        response = await self.client.post(
            f"{self.base_url}/worker/attempts/{attempt_id}/progress",
            headers=self.owned_headers,
            json={"status": status, "progress": progress},
        )
        if response.status_code in {404, 409}:
            raise PlatformAttemptInactive
        response.raise_for_status()

    async def download_source(self, download_path: str, destination: Path) -> None:
        source_url = urljoin(f"{self.base_url}/", download_path)
        async with self.client.stream(
            "GET", source_url, headers=self.agent_headers
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)

    async def complete(self, attempt_id: str, result_path: Path) -> None:
        with result_path.open("rb") as result:
            response = await self.client.post(
                f"{self.base_url}/worker/attempts/{attempt_id}/complete",
                headers=self.owned_headers,
                files={"file": ("enhanced.mp4", result, "video/mp4")},
            )
        if response.status_code in {404, 409}:
            raise PlatformAttemptInactive
        response.raise_for_status()

    async def fail(
        self, attempt_id: str, error_code: str, error_detail: str, retryable: bool
    ) -> None:
        response = await self.client.post(
            f"{self.base_url}/worker/attempts/{attempt_id}/fail",
            headers=self.owned_headers,
            json={
                "error_code": error_code,
                "error_detail": error_detail[:4000],
                "retryable": retryable,
            },
        )
        if response.status_code not in {404, 409}:
            response.raise_for_status()


class HttpCentralApi:
    def __init__(self, base_url: str, api_token: str, client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.headers = {"Authorization": f"Bearer {api_token}"}

    async def get_status(self, task_id: str) -> dict | None:
        response = await self.client.get(
            f"{self.base_url}/api/v1/tasks/{task_id}", headers=self.headers
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def submit_video_upscale(self, payload: dict) -> None:
        response = await self.client.post(
            f"{self.base_url}/api/v1/ltx25_video_upscale",
            headers=self.headers,
            json=payload,
        )
        if response.status_code != 409:
            response.raise_for_status()

    async def cancel(self, task_id: str) -> None:
        response = await self.client.delete(
            f"{self.base_url}/api/tasks/{task_id}", headers=self.headers
        )
        if response.status_code not in {404, 409}:
            response.raise_for_status()

    async def download_result(self, task_id: str, destination: Path) -> None:
        async with self.client.stream(
            "GET", f"{self.base_url}/video/{task_id}", headers=self.headers
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)


class S3TestInputStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def upload(
        self, object_key: str, source: Path, content_type: str
    ) -> None:
        await asyncio.to_thread(
            self.client.upload_file,
            str(source),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )


async def run_bridge_forever() -> None:
    settings = get_settings()
    settings.require_test_worker_bridge()
    timeout = httpx.Timeout(settings.test_worker_bridge_http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        platform = HttpPlatformApi(
            settings.test_worker_bridge_platform_url,
            settings.agent_token,
            settings.test_worker_bridge_worker_id,
            client,
        )
        central = HttpCentralApi(
            settings.test_central_url or "",
            settings.test_central_api_token or "",
            client,
        )
        input_store = S3TestInputStore(
            endpoint_url=settings.test_input_s3_endpoint_url or "",
            access_key=settings.test_input_s3_access_key or "",
            secret_key=settings.test_input_s3_secret_key or "",
            bucket=settings.test_input_s3_bucket,
            region=settings.test_input_s3_region,
        )
        bridge = TestWorkerBridge(
            platform,
            central,
            input_store,
            poll_seconds=settings.test_worker_bridge_poll_seconds,
        )
        while True:
            try:
                claimed = await bridge.run_once()
                if not claimed:
                    await asyncio.sleep(settings.test_worker_bridge_idle_seconds)
            except Exception:
                logger.exception("test worker bridge cycle failed")
                await asyncio.sleep(settings.test_worker_bridge_error_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_bridge_forever())


if __name__ == "__main__":
    main()
