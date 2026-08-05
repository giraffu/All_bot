import asyncio
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from shared.r2_retention_contract import build_staged_worker_result_key


@dataclass(frozen=True)
class SpooledOutputAsset:
    file_path: str
    object_name: str
    content_type: str
    media_type: str | None = None
    sha256: str = ""
    byte_size: int = 0


@dataclass(frozen=True)
class SpooledTaskOutputs:
    primary: SpooledOutputAsset
    extra_outputs: dict[str, SpooledOutputAsset]


async def upload_materialized_outputs(
    *,
    minio_client,
    result_bucket: str,
    task_id: str,
    outputs,
    logger,
) -> dict[str, Any]:
    primary_key = build_staged_worker_result_key(
        task_id=task_id,
        source_name=outputs.primary.object_name,
        role="primary",
    )
    primary_sha256 = hashlib.sha256(outputs.primary.file_data).hexdigest()
    logger.info(
        "Uploading result %s to MinIO bucket %s",
        primary_key,
        result_bucket,
    )
    await asyncio.to_thread(
        minio_client.put_object,
        result_bucket,
        primary_key,
        io.BytesIO(outputs.primary.file_data),
        len(outputs.primary.file_data),
        content_type=outputs.primary.content_type,
        metadata={"sha256": primary_sha256},
    )

    extra_outputs_payload: dict[str, dict[str, Any]] = {}
    extra_output_assets: dict[str, dict[str, Any]] = {}
    for ordinal, (name, extra_output) in enumerate(outputs.extra_outputs.items()):
        staging_key = build_staged_worker_result_key(
            task_id=task_id,
            source_name=extra_output.object_name,
            role=name,
            ordinal=ordinal,
        )
        sha256 = hashlib.sha256(extra_output.file_data).hexdigest()
        await asyncio.to_thread(
            minio_client.put_object,
            result_bucket,
            staging_key,
            io.BytesIO(extra_output.file_data),
            len(extra_output.file_data),
            content_type=extra_output.content_type,
            metadata={"sha256": sha256},
        )
        extra_outputs_payload[name] = {
            "path": staging_key,
            "media_type": extra_output.media_type,
        }
        extra_output_assets[name] = {
            "staging_key": staging_key,
            "sha256": sha256,
            "byte_size": len(extra_output.file_data),
            "content_type": extra_output.content_type,
            "media_type": extra_output.media_type,
            "ordinal": ordinal,
        }
    return {
        "result_path": primary_key,
        "result_asset": {
            "staging_key": primary_key,
            "sha256": primary_sha256,
            "byte_size": len(outputs.primary.file_data),
            "content_type": outputs.primary.content_type,
        },
        "extra_outputs": extra_outputs_payload,
        "extra_output_assets": extra_output_assets,
    }


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

    primary_key = build_staged_worker_result_key(
        task_id=task_id,
        source_name=outputs.primary.object_name,
        role="primary",
    )
    primary_sha256 = hashlib.sha256(outputs.primary.file_data).hexdigest()
    staged_extra_outputs: dict[str, SpooledOutputAsset] = {}
    for ordinal, (name, asset) in enumerate(extra_outputs.items()):
        staged_extra_outputs[name] = SpooledOutputAsset(
            file_path=asset.file_path,
            object_name=build_staged_worker_result_key(
                task_id=task_id,
                source_name=asset.object_name,
                role=name,
                ordinal=ordinal,
            ),
            content_type=asset.content_type,
            media_type=asset.media_type,
            sha256=hashlib.sha256(outputs.extra_outputs[name].file_data).hexdigest(),
            byte_size=len(outputs.extra_outputs[name].file_data),
        )
    return SpooledTaskOutputs(
        primary=SpooledOutputAsset(
            file_path=str(primary_path),
            object_name=primary_key,
            content_type=outputs.primary.content_type,
            sha256=primary_sha256,
            byte_size=len(outputs.primary.file_data),
        ),
        extra_outputs=staged_extra_outputs,
    )


def _spooled_asset_payload(asset: SpooledOutputAsset) -> dict[str, Any]:
    payload = {
        "file_path": asset.file_path,
        "object_name": asset.object_name,
        "content_type": asset.content_type,
    }
    if asset.media_type:
        payload["media_type"] = asset.media_type
    payload["sha256"] = asset.sha256
    payload["byte_size"] = asset.byte_size
    return payload


async def upload_spooled_outputs_via_sidecar(
    *,
    sidecar_url: str,
    result_bucket: str,
    task_id: str,
    spooled_outputs: SpooledTaskOutputs,
    logger,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
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
    return {
        "result_path": data.get("result_path") or spooled_outputs.primary.object_name,
        "result_asset": data.get("result_asset") or {},
        "extra_outputs": data.get("extra_outputs") or {},
        "extra_output_assets": data.get("extra_output_assets") or {},
    }


async def report_materialized_outputs(
    *,
    report_complete_func,
    task_id: str,
    uploaded_outputs_payload: dict[str, Any],
    result_path: str | None = None,
) -> None:
    durable_candidate = uploaded_outputs_payload.get("result_path") or result_path
    if not durable_candidate:
        raise ValueError("uploaded result path is required")
    await report_complete_func(
        task_id,
        durable_candidate,
        extra_outputs=uploaded_outputs_payload.get("extra_outputs") or {},
        result_asset=uploaded_outputs_payload.get("result_asset") or None,
        extra_output_assets=(
            uploaded_outputs_payload.get("extra_output_assets") or None
        ),
    )
