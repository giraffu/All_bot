from pathlib import Path

import pytest

from app.test_worker_bridge import PlatformAttemptInactive, TestWorkerBridge


CLAIM = {
    "task_id": "task-1",
    "attempt_id": "attempt-1",
    "attempt_number": 1,
    "task_type": "video_upscale",
    "multiplier": 2,
    "provider_task_id": None,
    "source": {
        "mime_type": "video/mp4",
        "download_path": "/api/worker/files/source-1",
    },
}


class FakePlatform:
    def __init__(self, claim: dict | None = CLAIM) -> None:
        self.claim = dict(claim) if claim else None
        self.heartbeats = 0
        self.bindings: list[tuple[str, str, str]] = []
        self.progress: list[tuple[str, str, int]] = []
        self.completed: list[tuple[str, bytes]] = []
        self.failures: list[tuple[str, str, bool]] = []
        self.inactive_status: str | None = None

    async def heartbeat(self) -> None:
        self.heartbeats += 1

    async def claim_task(self) -> dict | None:
        return self.claim

    async def bind_provider_task(
        self, attempt_id: str, provider: str, provider_task_id: str
    ) -> None:
        self.bindings.append((attempt_id, provider, provider_task_id))

    async def report_progress(self, attempt_id: str, status: str, progress: int) -> None:
        if status == self.inactive_status:
            raise PlatformAttemptInactive
        self.progress.append((attempt_id, status, progress))

    async def download_source(self, download_path: str, destination: Path) -> None:
        assert download_path == "/api/worker/files/source-1"
        destination.write_bytes(b"source-video")

    async def complete(self, attempt_id: str, result_path: Path) -> None:
        self.completed.append((attempt_id, result_path.read_bytes()))

    async def fail(
        self, attempt_id: str, error_code: str, error_detail: str, retryable: bool
    ) -> None:
        self.failures.append((attempt_id, error_code, retryable))


class FakeCentral:
    def __init__(self, statuses: list[dict | None]) -> None:
        self.statuses = list(statuses)
        self.submissions: list[dict] = []
        self.cancellations: list[str] = []

    async def get_status(self, task_id: str) -> dict | None:
        assert task_id == "clarity-task-1-attempt-1"
        return self.statuses.pop(0)

    async def submit_video_upscale(self, payload: dict) -> None:
        self.submissions.append(payload)

    async def cancel(self, task_id: str) -> None:
        self.cancellations.append(task_id)

    async def download_result(self, task_id: str, destination: Path) -> None:
        destination.write_bytes(b"enhanced-video")


class FakeInputStore:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []

    async def upload(self, object_key: str, source: Path, content_type: str) -> None:
        self.uploads.append((object_key, source.read_bytes(), content_type))


async def no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_bridge_submits_test_central_task_and_returns_video() -> None:
    platform = FakePlatform()
    central = FakeCentral(
        [
            None,
            {"status": "pending", "progress": 0},
            {"status": "running", "progress": 54},
            {"status": "done", "progress": 100},
        ]
    )
    inputs = FakeInputStore()
    bridge = TestWorkerBridge(platform, central, inputs, sleep=no_sleep)

    assert await bridge.run_once() is True

    provider_id = "clarity-task-1-attempt-1"
    object_key = "clarity-test-inputs/task-1/attempt-1.mp4"
    assert platform.heartbeats == 1
    assert platform.bindings == [("attempt-1", "allbot-test-central", provider_id)]
    assert inputs.uploads == [(object_key, b"source-video", "video/mp4")]
    assert central.submissions == [
        {
            "task_id": provider_id,
            "video": object_key,
            "prompt": "",
            "length": 5,
            "priority": 0,
        }
    ]
    assert ("attempt-1", "running", 54) in platform.progress
    assert platform.completed == [("attempt-1", b"enhanced-video")]
    assert platform.failures == []


@pytest.mark.asyncio
async def test_bridge_resumes_bound_provider_task_without_duplicate_submission() -> None:
    claim = {**CLAIM, "provider_task_id": "clarity-task-1-attempt-1"}
    platform = FakePlatform(claim)
    central = FakeCentral(
        [
            {"status": "running", "progress": 70},
            {"status": "done", "progress": 100},
        ]
    )
    inputs = FakeInputStore()

    assert await TestWorkerBridge(
        platform, central, inputs, sleep=no_sleep
    ).run_once()
    assert platform.bindings == []
    assert inputs.uploads == []
    assert central.submissions == []
    assert platform.completed == [("attempt-1", b"enhanced-video")]


@pytest.mark.asyncio
async def test_bridge_propagates_provider_failure_to_platform() -> None:
    platform = FakePlatform()
    central = FakeCentral(
        [None, {"status": "error", "error": "GPU out of memory"}]
    )

    assert await TestWorkerBridge(
        platform, central, FakeInputStore(), sleep=no_sleep
    ).run_once()
    assert platform.completed == []
    assert platform.failures == [("attempt-1", "test_worker_failed", True)]


@pytest.mark.asyncio
async def test_bridge_cancels_provider_when_platform_attempt_is_inactive() -> None:
    platform = FakePlatform()
    platform.inactive_status = "running"
    central = FakeCentral(
        [None, {"status": "running", "progress": 20}]
    )

    assert await TestWorkerBridge(
        platform, central, FakeInputStore(), sleep=no_sleep
    ).run_once()
    assert central.cancellations == ["clarity-task-1-attempt-1"]
    assert platform.completed == []
    assert platform.failures == []
