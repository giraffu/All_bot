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
            width=512,
            height=768,
            duration=None,
        ),
        extra_outputs={
            "last_frame": SimpleNamespace(
                object_name="history/task-1/last_frame.png",
                content_type="image/png",
                media_type="image",
                file_data=b"extra",
                width=512,
                height=768,
                duration=None,
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
    assert spooled.primary.object_name == ("staging/worker-results/task-1/primary.png")
    assert spooled.primary.sha256 == (
        "986a1b7135f4986150aa5fa0028feeaa66cdaf3ed6a00a355dd86e042f7fb494"
    )
    assert spooled.primary.byte_size == 7
    assert spooled.primary.width == 512
    assert spooled.primary.height == 768
    assert spooled.extra_outputs["last_frame"].media_type == "image"
    assert spooled.extra_outputs["last_frame"].object_name == (
        "staging/worker-results/task-1/extras/last_frame-0.png"
    )


@pytest.mark.asyncio
async def test_spool_uses_a_hardlink_for_a_shared_comfy_output(tmp_path):
    source = tmp_path / "comfy-output" / "result.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    outputs = SimpleNamespace(
        primary=SimpleNamespace(
            object_name="result.mp4",
            content_type="video/mp4",
            file_data=b"video",
            source_path=str(source),
            width=1280,
            height=720,
            duration=5.0,
        ),
        extra_outputs={},
    )
    logger = SimpleNamespace(info=lambda *args, **kwargs: None)

    spooled = await reporting.spool_materialized_outputs(
        outputs=outputs,
        spool_dir=str(tmp_path / "spool"),
        task_id="task-1",
        logger=logger,
    )

    spool_path = Path(spooled.primary.file_path)
    assert spool_path.read_bytes() == b"video"
    assert source.stat().st_ino == spool_path.stat().st_ino


@pytest.mark.asyncio
async def test_upload_spooled_outputs_via_sidecar_returns_extra_outputs(monkeypatch):
    requests = []
    client_timeouts = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "ok",
                "result_path": "staging/worker-results/task-1/primary.png",
                "result_asset": {
                    "staging_key": "staging/worker-results/task-1/primary.png",
                    "sha256": "a" * 64,
                    "byte_size": 7,
                    "content_type": "image/png",
                },
                "extra_outputs": {
                    "last_frame": {"path": "last_frame.png", "media_type": "image"}
                },
                "extra_output_assets": {},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.base_url = kwargs.get("base_url")
            client_timeouts.append(kwargs.get("timeout"))

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
            sha256="a" * 64,
            byte_size=7,
            width=512,
            height=768,
        ),
        extra_outputs={
            "last_frame": reporting.SpooledOutputAsset(
                file_path="/app/spool/last_frame.png",
                object_name="last_frame.png",
                content_type="image/png",
                media_type="image",
                sha256="b" * 64,
                byte_size=5,
                width=512,
                height=768,
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

    assert payload["result_path"] == "staging/worker-results/task-1/primary.png"
    assert payload["result_asset"]["sha256"] == "a" * 64
    assert requests[0][0] == "/api/local/upload-result"
    assert requests[0][1]["primary"]["object_name"] == "primary.png"
    assert requests[0][1]["primary"]["sha256"] == "a" * 64
    assert requests[0][1]["primary"]["width"] == 512
    assert requests[0][1]["primary"]["height"] == 768
    assert client_timeouts[0].connect == 10.0
    assert client_timeouts[0].read is None
    assert client_timeouts[0].write == 30.0
    assert client_timeouts[0].pool == 10.0


@pytest.mark.asyncio
async def test_direct_upload_uses_staging_keys_and_reports_integrity_metadata():
    uploads = []

    class FakeMinio:
        def put_object(
            self,
            bucket,
            object_name,
            stream,
            length,
            *,
            content_type,
            metadata,
        ):
            uploads.append(
                (bucket, object_name, stream.read(), length, content_type, metadata)
            )

    outputs = SimpleNamespace(
        primary=SimpleNamespace(
            object_name="raw.png",
            content_type="image/png",
            file_data=b"primary",
            width=512,
            height=768,
            duration=None,
        ),
        extra_outputs={
            "last_frame": SimpleNamespace(
                object_name="raw_last.png",
                content_type="image/png",
                media_type="image",
                file_data=b"extra",
                width=512,
                height=768,
                duration=None,
            )
        },
    )
    logger = SimpleNamespace(info=lambda *args, **kwargs: None)

    payload = await reporting.upload_materialized_outputs(
        minio_client=FakeMinio(),
        result_bucket="user-data-prod",
        task_id="task-1",
        outputs=outputs,
        logger=logger,
    )

    assert payload["result_path"] == "staging/worker-results/task-1/primary.png"
    assert payload["extra_outputs"]["last_frame"]["path"] == (
        "staging/worker-results/task-1/extras/last_frame-0.png"
    )
    assert payload["result_asset"] == {
        "staging_key": "staging/worker-results/task-1/primary.png",
        "sha256": "986a1b7135f4986150aa5fa0028feeaa66cdaf3ed6a00a355dd86e042f7fb494",
        "byte_size": 7,
        "content_type": "image/png",
        "width": 512,
        "height": 768,
    }
    assert uploads[0][5]["sha256"] == payload["result_asset"]["sha256"]


@pytest.mark.asyncio
async def test_report_complete_forwards_staging_asset_contract():
    calls = []

    async def report_complete(task_id, result_path, **kwargs):
        calls.append((task_id, result_path, kwargs))

    payload = {
        "result_path": "staging/worker-results/task-1/primary.png",
        "extra_outputs": {},
        "result_asset": {"staging_key": "x", "sha256": "a" * 64},
        "extra_output_assets": {},
    }
    await reporting.report_materialized_outputs(
        report_complete_func=report_complete,
        task_id="task-1",
        uploaded_outputs_payload=payload,
    )

    assert calls[0][1] == payload["result_path"]
    assert calls[0][2]["result_asset"] == payload["result_asset"]
