import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from src.services import wan22_video_v2_extension_service as stitch_service


def _require_ffmpeg_tools() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required for stitching media regression tests")


def _create_video_with_audio(path, *, color: str, frequency: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=160x90:r=10:d=0.5",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration=0.5",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _has_audio_stream(path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    streams = json.loads(result.stdout or "{}").get("streams") or []
    return bool(streams)


@pytest.mark.asyncio
async def test_stitch_history_videos_preserves_audio_when_segments_have_audio(
    monkeypatch,
    tmp_path,
):
    _require_ffmpeg_tools()
    first_segment = tmp_path / "first.mp4"
    second_segment = tmp_path / "second.mp4"
    _create_video_with_audio(first_segment, color="red", frequency=440)
    _create_video_with_audio(second_segment, color="blue", frequency=660)
    assert _has_audio_stream(first_segment)
    assert _has_audio_stream(second_segment)

    sources = {
        "first-output.mp4": first_segment,
        "second-output.mp4": second_segment,
    }

    def fake_download_output_to_local_file(*, output_file: str, target_path):
        shutil.copyfile(sources[output_file], target_path)

    monkeypatch.setattr(
        stitch_service,
        "_download_output_to_local_file",
        fake_download_output_to_local_file,
    )

    stitched_bytes = await stitch_service.stitch_history_videos(
        [
            SimpleNamespace(output_file="first-output.mp4"),
            SimpleNamespace(output_file="second-output.mp4"),
        ]
    )
    stitched_path = tmp_path / "stitched.mp4"
    stitched_path.write_bytes(stitched_bytes)

    assert _has_audio_stream(stitched_path)
