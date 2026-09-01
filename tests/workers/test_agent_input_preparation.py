import json
import logging
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from workers.comfy_agent.agent_input_preparation import (
    prepare_h3_reference_video_tail,
    prepare_ltx25_video_upscale_input,
    prepare_task_inputs,
    process_single_input_asset,
)


def test_prepare_ltx25_upscale_video_locks_24fps_121_frames_and_div32(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "ffprobe":
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": b'{"streams":[{"codec_type":"video"},{"codec_type":"audio"}],"format":{"duration":"5.0"}}',
                    "stderr": b"",
                },
            )()
        Path(command[-1]).write_bytes(b"normalized-video")
        return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr(
        "workers.comfy_agent.agent_input_preparation.subprocess.run", run
    )
    result = prepare_ltx25_video_upscale_input("video", str(source))

    ffmpeg = commands[1]
    assert ffmpeg[ffmpeg.index("-frames:v") + 1] == "121"
    video_filter = ffmpeg[ffmpeg.index("-vf") + 1]
    assert "fps=24" in video_filter
    assert "round(iw/32)*32" in video_filter
    assert "round(ih/32)*32" in video_filter
    assert ffmpeg[ffmpeg.index("-map") + 1] == "0:v:0"
    assert "0:a:0" in ffmpeg
    assert ffmpeg[ffmpeg.index("-af") + 1] == "apad"
    assert Path(result).read_bytes() == b"normalized-video"


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for the media boundary regression",
)
def test_prepare_ltx25_upscale_keeps_boundary_frame_with_five_second_audio(
    tmp_path,
):
    source = tmp_path / "five-seconds-with-audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=64x64:rate=24:duration=5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=32000:duration=5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )

    normalized = prepare_ltx25_video_upscale_input("video", str(source))
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,nb_read_frames",
            "-of",
            "json",
            normalized,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    video = next(item for item in streams if item["codec_type"] == "video")
    audio = next(item for item in streams if item["codec_type"] == "audio")

    assert video["nb_read_frames"] == "121"
    assert int(audio["nb_read_frames"]) > 0


def test_prepare_ltx25_upscale_video_rejects_more_than_five_seconds(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")

    def run(command, **_kwargs):
        assert command[0] == "ffprobe"
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": b'{"streams":[{"codec_type":"video"}],"format":{"duration":"5.3"}}',
                "stderr": b"",
            },
        )()

    monkeypatch.setattr(
        "workers.comfy_agent.agent_input_preparation.subprocess.run", run
    )

    with pytest.raises(RuntimeError, match="5 second limit"):
        prepare_ltx25_video_upscale_input("video", str(source))


def test_prepare_ltx25_upscale_accepts_h3_encoding_tail_and_trims_to_121_frames(
    tmp_path, monkeypatch
):
    source = tmp_path / "h3-beta4.mp4"
    source.write_bytes(b"source-video")
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[0] == "ffprobe":
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": b'{"streams":[{"codec_type":"video"},{"codec_type":"audio"}],"format":{"duration":"5.166667"}}',
                    "stderr": b"",
                },
            )()
        Path(command[-1]).write_bytes(b"normalized-video")
        return type("Result", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(
        "workers.comfy_agent.agent_input_preparation.subprocess.run", run
    )

    result = prepare_ltx25_video_upscale_input("video", str(source))

    ffmpeg = commands[1]
    assert ffmpeg[ffmpeg.index("-frames:v") + 1] == "121"
    assert ffmpeg[ffmpeg.index("-t") + 1] == "5.1"
    assert Path(result).read_bytes() == b"normalized-video"


def test_prepare_h3_reference_video_tail_uses_last_five_seconds(tmp_path, monkeypatch):
    source = tmp_path / "previous.mp4"
    source.write_bytes(b"source-video")

    def run(command, **kwargs):
        assert command[command.index("-sseof") + 1] == "-5"
        assert command[command.index("-t") + 1] == "5"
        assert kwargs["timeout"] == 120
        Path(command[-1]).write_bytes(b"tail-video")
        return type("Result", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(
        "workers.comfy_agent.agent_input_preparation.subprocess.run",
        run,
    )

    result = prepare_h3_reference_video_tail("reference_video", str(source))

    assert result.endswith("__tail5s.mp4")
    assert Path(result).read_bytes() == b"tail-video"


def test_prepare_h3_reference_video_tail_leaves_other_inputs_unchanged(tmp_path):
    source = tmp_path / "voice.m4a"
    assert prepare_h3_reference_video_tail("reference_audio", str(source)) == str(source)


def test_prepare_h3_reference_video_tail_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / "previous.mp4"
    source.write_bytes(b"source-video")
    monkeypatch.setattr(
        "workers.comfy_agent.agent_input_preparation.subprocess.run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"returncode": 1, "stderr": b"invalid video"}
        )(),
    )

    with pytest.raises(RuntimeError, match="invalid video"):
        prepare_h3_reference_video_tail("reference_video", str(source))

    assert not (tmp_path / "previous__tail5s.mp4").exists()


async def _noop_upload(**_kwargs):
    return None


def _never_normalize(_param_key, _object_name):
    return False


def _identity_normalize(path):
    return path


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_character_sheet_reference():
    calls = []

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))

    await prepare_task_inputs(
        params={"character_sheet": "bucket/private-character.png"},
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [("character_sheet", "bucket/private-character.png")]


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_ordered_character_panels():
    calls = []
    params = {
        "character_sheets": [
            "bucket/wang-panel.png",
            "bucket/man-panel.png",
        ]
    }

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))
        kwargs["params"][kwargs["param_key"]] = f"local-{kwargs['param_key']}.png"

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("character_sheet_1", "bucket/wang-panel.png"),
        ("character_sheet_2", "bucket/man-panel.png"),
    ]
    assert params["character_sheets"] == [
        "local-character_sheet_1.png",
        "local-character_sheet_2.png",
    ]


@pytest.mark.asyncio
async def test_prepare_task_inputs_preserves_five_ordered_images():
    calls = []
    params = {"images": [f"bucket/reference-{index}.png" for index in range(1, 6)]}

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("image", "bucket/reference-1.png"),
        ("image2", "bucket/reference-2.png"),
        ("image3", "bucket/reference-3.png"),
        ("image4", "bucket/reference-4.png"),
        ("image5", "bucket/reference-5.png"),
    ]


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_ltx_character_background():
    calls = []
    params = {"background_image": "web_uploads/user/scene.jpeg"}

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))
        kwargs["params"][kwargs["param_key"]] = "local-background.png"

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("background_image", "web_uploads/user/scene.jpeg"),
    ]
    assert params["background_image"] == "local-background.png"


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_single_reference_audio():
    calls = []
    params = {"reference_audio": "web_uploads/user/voice.m4a"}

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))
        kwargs["params"][kwargs["param_key"]] = "prepared-voice.m4a"

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [("reference_audio", "web_uploads/user/voice.m4a")]
    assert params["reference_audio"] == "prepared-voice.m4a"


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_extension_reference_video():
    calls = []
    params = {"reference_video": "task-inputs/extension/previous.mp4"}

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))
        kwargs["params"][kwargs["param_key"]] = "prepared-tail.mp4"

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("reference_video", "task-inputs/extension/previous.mp4"),
    ]
    assert params["reference_video"] == "prepared-tail.mp4"


@pytest.mark.asyncio
async def test_process_single_input_asset_times_out_download(tmp_path):
    def slow_download(_object_name, _local_path):
        time.sleep(0.2)

    with pytest.raises(RuntimeError, match="Failed to prepare video input"):
        await process_single_input_asset(
            params={},
            downloaded_input_paths=[],
            img_filename="uploads/demo.mp4",
            param_key="video",
            comfy_input_dir=str(tmp_path),
            download_input_func=slow_download,
            should_normalize_image_input_func=_never_normalize,
            normalize_input_image_func=_identity_normalize,
            upload_prepared_input_func=_noop_upload,
            logger=logging.getLogger("test"),
            download_timeout_seconds=0.01,
            download_retry_attempts=1,
            download_retry_delay_seconds=0,
        )


@pytest.mark.asyncio
async def test_process_single_input_asset_cleans_partial_download_on_failure(tmp_path):
    def failing_download(_object_name, local_path):
        (tmp_path / "uploads_demo.mp4.abc.part.minio").write_bytes(b"partial")
        raise OSError("broken stream")

    with pytest.raises(RuntimeError, match="Failed to prepare video input"):
        await process_single_input_asset(
            params={},
            downloaded_input_paths=[],
            img_filename="uploads/demo.mp4",
            param_key="video",
            comfy_input_dir=str(tmp_path),
            download_input_func=failing_download,
            should_normalize_image_input_func=_never_normalize,
            normalize_input_image_func=_identity_normalize,
            upload_prepared_input_func=_noop_upload,
            logger=logging.getLogger("test"),
            download_timeout_seconds=1,
            download_retry_attempts=1,
            download_retry_delay_seconds=0,
        )

    assert not list(tmp_path.glob("*.part.minio"))


@pytest.mark.asyncio
async def test_process_single_input_asset_records_the_exact_comfy_input_artifact(
    tmp_path,
):
    uploaded_input_artifacts = []

    def download(_object_name, local_path):
        with open(local_path, "wb") as handle:
            handle.write(b"image")

    async def upload(**_kwargs):
        assert _kwargs["upload_name"] == "task-1_uploads_demo.png"
        return {
            "name": "task-1_uploads_demo.png",
            "subfolder": "",
            "type": "input",
        }

    await process_single_input_asset(
        params={},
        downloaded_input_paths=[],
        uploaded_input_artifacts=uploaded_input_artifacts,
        comfy_filename_prefix="task-1",
        img_filename="uploads/demo.png",
        param_key="image",
        comfy_input_dir=str(tmp_path),
        download_input_func=download,
        should_normalize_image_input_func=_never_normalize,
        normalize_input_image_func=_identity_normalize,
        upload_prepared_input_func=upload,
        logger=logging.getLogger("test"),
    )

    assert len(uploaded_input_artifacts) == 1
    artifact = uploaded_input_artifacts[0]
    assert artifact.kind == "input"
    assert artifact.filename == "task-1_uploads_demo.png"
    assert artifact.subfolder == ""
