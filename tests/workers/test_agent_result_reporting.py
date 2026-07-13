import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = ROOT / "workers" / "comfy_agent"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import agent_result_reporting as reporting  # noqa: E402


@pytest.mark.asyncio
async def test_spool_materialized_outputs_writes_primary_and_extra_files(tmp_path):
    outputs = SimpleNamespace(
        primary=SimpleNamespace(
            object_name="history/task-1/original.png",
            content_type="image/png",
            file_data=b"primary",
        ),
        extra_outputs={
            "last_frame": SimpleNamespace(
                object_name="history/task-1/last_frame.png",
                content_type="image/png",
                media_type="image",
                file_data=b"extra",
            )
        },
    )
    logger = SimpleNamespace(info=lambda *args, **kwargs: None)

    spooled = await reporting.spool_materialized_outputs(
        outputs=outputs,
        spool_dir=str(tmp_path),
        task_id="task-1",
        logger=logger,
    )

    assert Path(spooled.primary.file_path).read_bytes() == b"primary"
    assert Path(spooled.extra_outputs["last_frame"].file_path).read_bytes() == b"extra"
    assert spooled.primary.object_name == "history/task-1/original.png"
    assert spooled.extra_outputs["last_frame"].media_type == "image"


@pytest.mark.asyncio
async def test_upload_spooled_outputs_via_sidecar_returns_extra_outputs(monkeypatch):
    requests = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "ok",
                "extra_outputs": {
                    "last_frame": {"path": "last_frame.png", "media_type": "image"}
                },
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.base_url = kwargs.get("base_url")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, path, json):
            requests.append((path, json))
            return FakeResponse()

    monkeypatch.setattr(reporting.httpx, "AsyncClient", FakeClient)
    logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    spooled = reporting.SpooledTaskOutputs(
        primary=reporting.SpooledOutputAsset(
            file_path="/app/spool/primary.png",
            object_name="primary.png",
            content_type="image/png",
        ),
        extra_outputs={
            "last_frame": reporting.SpooledOutputAsset(
                file_path="/app/spool/last_frame.png",
                object_name="last_frame.png",
                content_type="image/png",
                media_type="image",
            )
        },
    )

    payload = await reporting.upload_spooled_outputs_via_sidecar(
        sidecar_url="http://127.0.0.1:8013",
        result_bucket="user-data-prod",
        task_id="task-1",
        spooled_outputs=spooled,
        logger=logger,
    )

    assert payload == {"last_frame": {"path": "last_frame.png", "media_type": "image"}}
    assert requests[0][0] == "/api/local/upload-result"
    assert requests[0][1]["primary"]["object_name"] == "primary.png"
