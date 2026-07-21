from __future__ import annotations

import json
import subprocess

import pytest

from src.services.qqcc_video_chain_stitch_service import (
    extract_qqcc_video_last_frame,
    stitch_qqcc_video_segments,
)


def _video(*, width: int, height: int, color: str, audio: bool) -> bytes:
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"color=c={color}:s={width}x{height}:d=0.4:r=12",
    ]
    if audio:
        command.extend(["-f", "lavfi", "-i", "sine=frequency=440:duration=0.4"])
    command.extend([
        "-map", "0:v:0", *( ["-map", "1:a:0"] if audio else [] ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        *( ["-c:a", "aac"] if audio else [] ),
        "-movflags", "frag_keyframe+empty_moov",
        "-f", "mp4", "pipe:1",
    ])
    return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def _probe(payload: bytes, tmp_path) -> dict:
    path = tmp_path / "result.mp4"
    path.write_bytes(payload)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_stitch_video_segments_normalizes_later_segments_to_first_canvas(tmp_path):
    first = _video(width=320, height=180, color="red", audio=True)
    second = _video(width=180, height=320, color="blue", audio=False)

    stitched = await stitch_qqcc_video_segments([first, second])

    streams = _probe(stitched, tmp_path)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    assert (video["width"], video["height"]) == (320, 180)
    assert any(stream["codec_type"] == "audio" for stream in streams)


@pytest.mark.asyncio
async def test_extract_video_last_frame_returns_png():
    frame = await extract_qqcc_video_last_frame(
        _video(width=160, height=90, color="green", audio=False)
    )

    assert frame.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_stitch_single_segment_is_lossless_fast_path():
    video = _video(width=160, height=90, color="green", audio=False)
    assert await stitch_qqcc_video_segments([video]) == video
