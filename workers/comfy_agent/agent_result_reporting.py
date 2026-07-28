import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class SpooledOutputAsset:
    file_path: str
    object_name: str
    content_type: str
    media_type: str | None = None


@dataclass(frozen=True)
class SpooledTaskOutputs:
    primary: SpooledOutputAsset
    extra_outputs: dict[str, SpooledOutputAsset]


async def upload_materialized_outputs(
    *,
    minio_client,
    result_bucket: str,
    outputs,
    logger,
) -> dict[str, dict[str, Any]]:
    logger.info(
        "Uploading result %s to MinIO bucket %s",
        outputs.primary.object_name,
        result_bucket,
    )
    await asyncio.to_thread(
        minio_client.put_object,
        result_bucket,
        outputs.primary.object_name,
        io.BytesIO(outputs.primary.file_data),
        len(outputs.primary.file_data),
        content_type=outputs.primary.content_type,
    )

    extra_outputs_payload: dict[str, dict[str, Any]] = {}
    for name, extra_output in outputs.extra_outputs.items():
        await asyncio.to_thread(
            minio_client.put_object,
            result_bucket,
            extra_output.object_name,
            io.BytesIO(extra_output.file_data),
            len(extra_output.file_data),
            content_type=extra_output.content_type,
        )
        extra_outputs_payload[name] = {
            "path": extra_output.object_name,
            "media_type": extra_output.media_type,
        }
    return extra_outputs_payload


def _spool_file_name(*, task_id: str, output_name: str, suffix: str) -> str:
    safe_name = output_name.replace("/", "_").replace("\\", "_").strip("._")
    return f"{task_id}_{suffix}_{safe_name or 'output'}"


async def spool_materialized_outputs(
    *,
    outputs,
    spool_dir: str,
    task_id: str,
    logger,
) -> SpooledTaskOutputs:
    task_spool_dir = Path(spool_dir) / task_id
    task_spool_dir.mkdir(parents=True, exist_ok=True)

    primary_path = task_spool_dir / _spool_file_name(
        task_id=task_id,
        output_name=outputs.primary.object_name,
        suffix="primary",
    )
    await asyncio.to_thread(primary_path.write_bytes, outputs.primary.file_data)
    logger.info("Spooled primary result for task %s to %s", task_id, primary_path)

    extra_outputs: dict[str, SpooledOutputAsset] = {}
    for name, extra_output in outputs.extra_outputs.items():
        extra_path = task_spool_dir / _spool_file_name(
            task_id=task_id,
            output_name=extra_output.object_name,
            suffix=name,
        )
        await asyncio.to_thread(extra_path.write_bytes, extra_output.file_data)
        extra_outputs[name] = SpooledOutputAsset(
            file_path=str(extra_path),
            object_name=extra_output.object_name,
            content_type=extra_output.content_type,
            media_type=extra_output.media_type,
        )
        logger.info("Spooled extra result %s for task %s to %s", name, task_id, extra_path)

    return SpooledTaskOutputs(
        primary=SpooledOutputAsset(
            file_path=str(primary_path),
            object_name=outputs.primary.object_name,
            content_type=outputs.primary.content_type,
        ),
        extra_outputs=extra_outputs,
    )


def _spooled_asset_payload(asset: SpooledOutputAsset) -> dict[str, Any]:
    payload = {
        "file_path": asset.file_path,
        "object_name": asset.object_name,
        "content_type": asset.content_type,
    }
    if asset.media_type:
        payload["media_type"] = asset.media_type
    return payload


async def upload_spooled_outputs_via_sidecar(
    *,
    sidecar_url: str,
    result_bucket: str,
    task_id: str,
    spooled_outputs: SpooledTaskOutputs,
    logger,
    timeout_seconds: float | None = None,
) -> dict[str, dict[str, Any]]:
    payload = {
        "task_id": task_id,
        "result_bucket": result_bucket,
        "primary": _spooled_asset_payload(spooled_outputs.primary),
        "extra_outputs": {
            name: _spooled_asset_payload(asset)
            for name, asset in spooled_outputs.extra_outputs.items()
        },
    }
    logger.info("Submitting task %s result spool to upload sidecar", task_id)
    # The relay owns the bounded R2 retry policy. A read deadline here can expire
    # while the relay is still completing a valid upload, causing the agent to
    # report a false terminal failure after the objects have been delivered.
    sidecar_timeout = httpx.Timeout(
        connect=10.0,
        read=timeout_seconds,
        write=30.0,
        pool=10.0,
    )
    async with httpx.AsyncClient(
        base_url=sidecar_url,
        timeout=sidecar_timeout,
    ) as client:
        response = await client.post("/api/local/upload-result", json=payload)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Upload sidecar returned HTTP {response.status_code} for task {task_id}"
        )
    data = response.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Upload sidecar did not confirm success for task {task_id}")
    return data.get("extra_outputs") or {}


async def report_materialized_outputs(
    *,
    report_complete_func,
    task_id: str,
    result_path: str,
    extra_outputs_payload: dict[str, Any] | None = None,
) -> None:
    await report_complete_func(
        task_id,
        result_path,
        extra_outputs=extra_outputs_payload or {},
    )
