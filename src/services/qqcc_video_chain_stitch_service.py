from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import uuid


class QqccVideoChainStitchError(RuntimeError):
    pass


async def persist_and_send_qqcc_video_chain_result(
    *,
    context: Any,
    chat_id: int,
    telegram_user_id: int,
    username: str | None,
    plan: Any,
    video_bytes: bytes,
    segment_output_files: list[str],
    partial: bool,
) -> dict[str, Any]:
    """Persist one visible QQCC chain result and present it through Bot UI."""

    from sqlalchemy import select

    from src.database.core import AsyncSessionLocal
    from src.database.models import History
    from src.services.storage import storage
    from src.services.task_service_generation_common import resolve_internal_user_id
    from src.services.tg_task_runtime import send_result_media
    from src.services.qqcc_regenerate_metadata import (
        merge_qqcc_regenerate_context_into_extra_outputs,
    )
    from src.services.minimax_h3_history_context_service import (
        merge_minimax_h3_history_context_into_extra_outputs,
    )

    internal_user_id = await resolve_internal_user_id(telegram_user_id, username)
    delivery_key = str(getattr(plan, "delivery_key", "") or "").strip()
    task_uuid = (
        uuid.uuid5(uuid.NAMESPACE_URL, f"qqcc-video-chain:{delivery_key}")
        if delivery_key
        else uuid.uuid4()
    )
    task_id = f"qqcc_chain_{task_uuid.hex[:24]}"
    output_file = await asyncio.to_thread(
        storage.upload_bytes,
        video_bytes,
        f"task-results/{task_id}/primary.mp4",
        content_type="video/mp4",
    )
    if not output_file:
        raise QqccVideoChainStitchError("拼接视频上传失败，请稍后重试")
    last_frame_bytes = await extract_qqcc_video_last_frame(video_bytes)
    last_frame_output = await asyncio.to_thread(
        storage.upload_bytes,
        last_frame_bytes,
        f"task-results/{task_id}/last_frame.png",
        content_type="image/png",
    )
    if not last_frame_output:
        raise QqccVideoChainStitchError("拼接视频尾帧上传失败，请稍后重试")

    async with AsyncSessionLocal() as session:
        existing_result = await session.execute(
            select(History).where(
                History.user_id == internal_user_id,
                History.task_id == task_id,
            )
        )
        existing_history = existing_result.scalar_one_or_none()
        result = await session.execute(
            select(History).where(
                History.user_id == internal_user_id,
                History.output_file.in_(segment_output_files),
            )
        )
        histories_by_output = {
            str(history.output_file or ""): history for history in result.scalars().all()
        }
        segment_task_ids = [
            str(histories_by_output[output].task_id or "")
            for output in segment_output_files
            if output in histories_by_output
        ]
        segments = list(getattr(plan, "qqcc_chain_segments", ()) or ())
        completed_segments = segments[: len(segment_output_files)]
        metadata = {
            "root_scene_id": completed_segments[0].scene_id if completed_segments else "",
            "scene_kind": completed_segments[0].scene_kind if completed_segments else "video",
            "scene_ids": [segment.scene_id for segment in completed_segments],
            "segment_task_ids": segment_task_ids,
            "planned_count": len(segments),
            "completed_count": len(completed_segments),
            "partial": bool(partial),
        }
        prompt = "\n\n".join(
            f"【第 {index} 段】\n{segment.prompt_override or segment.default_prompt_text}"
            for index, segment in enumerate(completed_segments, start=1)
        )
        duration = sum(
            int(str(segment.duration).removesuffix("s") or 0)
            for segment in completed_segments
        )
        history_extra_outputs = merge_qqcc_regenerate_context_into_extra_outputs(
            extra_outputs={
                "_qqcc_video_scene_chain": metadata,
                "last_frame": {
                    "path": str(last_frame_output),
                    "media_type": "image",
                },
            },
            metadata=getattr(plan, "result_meta", None),
        )
        raw_duration = str(getattr(plan, "duration", "5") or "5").removesuffix("s")
        try:
            context_duration = int(raw_duration)
        except ValueError:
            context_duration = 5
        history_extra_outputs = merge_minimax_h3_history_context_into_extra_outputs(
            task_type=str(getattr(plan, "mode", "") or ""),
            extra_outputs=history_extra_outputs,
            metadata={
                **dict(getattr(plan, "result_meta", None) or {}),
                "minimax_h3_mode": str(getattr(plan, "mode", "") or "").removeprefix("minimax_h3_"),
                "requested_duration": context_duration,
                "minimax_h3_resolution_preset": str(getattr(plan, "resolution", "preview") or "preview"),
                "minimax_h3_aspect_ratio": "source",
                "lora_items": list(getattr(plan, "lora_items", None) or []),
            },
        )
        history = History(
            user_id=internal_user_id,
            task_id=task_id,
            type=str(getattr(plan, "mode", "") or "custom_video"),
            prompt=prompt,
            output_file=str(output_file),
            extra_outputs=history_extra_outputs,
            billing_resolution=str(getattr(plan, "resolution", "") or ""),
            duration=duration or None,
            requested_duration=duration or None,
            allow_contribute=False,
            source="bot",
        )
        if existing_history is None:
            session.add(history)
            await session.commit()

    display_name = str(getattr(plan, "display_mode_name", "") or "AI视频")
    await send_result_media(
        context=context,
        chat_id=chat_id,
        media_bytes=video_bytes,
        is_video=True,
        caption=f"✅ {display_name}生成完成" + ("（部分完成）" if partial else ""),
        task_type=str(getattr(plan, "mode", "") or "custom_video"),
        task_id=task_id,
        allow_contribute=False,
        reply_markup=None,
        prompt=prompt,
        result_meta=getattr(plan, "result_meta", None),
        lang=str(getattr(context, "lang", None) or "zh"),
    )
    return {
        "task_id": task_id,
        "output_file": str(output_file),
        "extra_outputs": history_extra_outputs,
    }


def _run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise QqccVideoChainStitchError(
            "服务器未安装 ffmpeg/ffprobe，暂时无法拼接视频"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
        raise QqccVideoChainStitchError(
            f"视频处理失败，请稍后重试。{stderr[-300:]}".strip()
        ) from exc


def _probe(path: Path) -> dict[str, Any]:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout or b"{}")


def _normalize_fps(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value or value in {"0/0", "N/A"}:
        return "24"
    return value


def _normalize_segment(
    *,
    source: Path,
    target: Path,
    width: int,
    height: int,
    fps: str,
) -> None:
    streams = _probe(source).get("streams") or []
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    command = ["ffmpeg", "-y", "-i", str(source)]
    if not has_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0" if has_audio else "1:a:0",
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p"
            ),
            "-af",
            "aresample=48000,asetpts=N/SR/TB",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    _run(command)


async def stitch_qqcc_video_segments(segments: list[bytes]) -> bytes:
    if not segments:
        raise QqccVideoChainStitchError("没有可拼接的视频片段")
    if len(segments) == 1:
        return segments[0]

    temp_dir = Path(tempfile.mkdtemp(prefix="qqcc_video_chain_"))
    try:
        sources: list[Path] = []
        for index, payload in enumerate(segments):
            if not payload:
                raise QqccVideoChainStitchError("视频片段为空")
            source = temp_dir / f"source_{index:04d}.mp4"
            source.write_bytes(payload)
            sources.append(source)

        first_streams = _probe(sources[0]).get("streams") or []
        first_video = next(
            (stream for stream in first_streams if stream.get("codec_type") == "video"),
            None,
        )
        if not first_video:
            raise QqccVideoChainStitchError("第一段视频没有可用画面")
        width = int(first_video.get("width") or 0)
        height = int(first_video.get("height") or 0)
        if width <= 0 or height <= 0:
            raise QqccVideoChainStitchError("第一段视频画布尺寸无效")
        fps = _normalize_fps(
            first_video.get("avg_frame_rate") or first_video.get("r_frame_rate")
        )

        normalized: list[Path] = []
        for index, source in enumerate(sources):
            target = temp_dir / f"normalized_{index:04d}.mp4"
            await asyncio.to_thread(
                _normalize_segment,
                source=source,
                target=target,
                width=width,
                height=height,
                fps=fps,
            )
            normalized.append(target)

        concat_file = temp_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in normalized),
            encoding="utf-8",
        )
        output = temp_dir / "stitched.mp4"
        await asyncio.to_thread(
            _run,
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ],
        )
        return output.read_bytes()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def extract_qqcc_video_last_frame(video_bytes: bytes) -> bytes:
    if not video_bytes:
        raise QqccVideoChainStitchError("视频为空，无法提取尾帧")
    temp_dir = Path(tempfile.mkdtemp(prefix="qqcc_video_last_frame_"))
    try:
        source = temp_dir / "source.mp4"
        source.write_bytes(video_bytes)
        result = await asyncio.to_thread(
            _run,
            [
                "ffmpeg",
                "-sseof",
                "-0.1",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "pipe:1",
            ],
        )
        if not result.stdout:
            raise QqccVideoChainStitchError("未能提取视频尾帧")
        return result.stdout
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
