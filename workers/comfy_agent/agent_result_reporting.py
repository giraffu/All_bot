import asyncio
import io
from typing import Any


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
