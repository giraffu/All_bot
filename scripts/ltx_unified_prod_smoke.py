#!/usr/bin/env python3
"""Submit the five production LTX golden tasks to one expected LAN agent."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.runpod_cloud_test_canary import (  # noqa: E402
    RunPodCloudTestCanaryConfig,
    RunPodCloudTestCanaryExecutor,
)
from ops.gpu_pool_controller.runpod_control import (  # noqa: E402
    RunPodControlClient,
    RunPodControlConfig,
)
from ops.gpu_pool_controller.runpod_http import RunPodHttpClient  # noqa: E402


DEFAULT_WEB_URL = "https://web-api.aivison.it.com"
DEFAULT_CENTRAL_URL = "https://worker-central.aivison.it.com"
EXPECTED_TYPES = (
    "ltx_video",
    "ltx_video_flf2v",
    "ltx_video_v2v_audio",
    "ltx_t2v",
    "ltx_t2v_ic",
)


class LtxUnifiedSmokeError(RuntimeError):
    pass


def build_cases(
    *,
    image_key: str,
    end_image_key: str,
    video_key: str,
    character_sheet_key: str,
) -> list[dict[str, Any]]:
    common = {"duration": 5, "duration_seconds": 5, "seed": 20260729}
    prompt = "cinematic natural motion, consistent subject, high detail"
    negative = "low quality, artifacts, text, watermark"
    return [
        {
            "label": "ltx_video_i2v_5s",
            "expected_central_task_type": "ltx_video",
            "payload": {
                "task_type": "ltx_video",
                "inputs": {
                    **common,
                    "images": [image_key],
                    "image": image_key,
                    "resolution": "1280x704",
                    "extract_last_frame": True,
                    "ltx_mode": "i2v",
                },
                "prompt": prompt,
                "negative_prompt": negative,
                "priority": 0,
            },
        },
        {
            "label": "ltx_video_flf2v_5s",
            "expected_central_task_type": "ltx_video_flf2v",
            "payload": {
                "task_type": "ltx_video",
                "inputs": {
                    **common,
                    "images": [image_key, end_image_key],
                    "image": image_key,
                    "end_image": end_image_key,
                    "resolution": "1280x704",
                    "extract_last_frame": True,
                    "ltx_mode": "flf2v",
                },
                "prompt": prompt,
                "negative_prompt": negative,
                "priority": 0,
            },
        },
        {
            "label": "ltx_video_v2v_audio_5s",
            "expected_central_task_type": "ltx_video_v2v_audio",
            "payload": {
                "task_type": "ltx_video_v2v_audio",
                "inputs": {
                    **common,
                    "video": video_key,
                    "images": [video_key],
                    "resolution": "1280x704",
                    "extract_last_frame": True,
                },
                "prompt": prompt,
                "negative_prompt": negative,
                "priority": 0,
            },
        },
        {
            "label": "ltx_t2v_sulphur_5s",
            "expected_central_task_type": "ltx_t2v",
            "payload": {
                "task_type": "ltx_t2v",
                "inputs": {**common, "resolution": "1280x704"},
                "prompt": prompt,
                "negative_prompt": negative,
                "priority": 0,
            },
        },
        {
            "label": "ltx_t2v_ic_ingredients_5s",
            "expected_central_task_type": "ltx_t2v_ic",
            "payload": {
                "task_type": "ltx_t2v_ic",
                "inputs": {
                    **common,
                    "resolution": "768x448",
                    "character_sheet": character_sheet_key,
                },
                "prompt": (
                    prompt
                    + ", preserve the supplied identity; never show a contact sheet"
                ),
                "negative_prompt": (
                    negative + ", contact sheet, split screen, tiled image, collage"
                ),
                "priority": 0,
            },
        },
    ]


def _ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,avg_frame_rate,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if not video:
        raise LtxUnifiedSmokeError(f"{path.name}: missing video stream")
    rate = str(video.get("avg_frame_rate") or "0/1").split("/", 1)
    fps = float(rate[0]) / float(rate[1])
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if abs(fps - 24.0) > 0.1 or not 4.5 <= duration <= 6.5:
        raise LtxUnifiedSmokeError(
            f"{path.name}: expected 24fps and about 5 seconds, got {fps}/{duration}"
        )
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise LtxUnifiedSmokeError(f"{path.name}: missing audio stream")
    return {
        "fps": fps,
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-agent-id", required=True)
    parser.add_argument(
        "--image-object-key",
        default=os.getenv("LTX_UNIFIED_CANARY_IMAGE_OBJECT_KEY", ""),
    )
    parser.add_argument(
        "--end-image-object-key",
        default=os.getenv("LTX_UNIFIED_CANARY_END_IMAGE_OBJECT_KEY", ""),
    )
    parser.add_argument(
        "--video-object-key",
        default=os.getenv("LTX_UNIFIED_CANARY_VIDEO_OBJECT_KEY", ""),
    )
    parser.add_argument(
        "--character-sheet-object-key",
        default=os.getenv("LTX_UNIFIED_CANARY_CHARACTER_SHEET_OBJECT_KEY", ""),
    )
    parser.add_argument("--web-api-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--central-url", default=DEFAULT_CENTRAL_URL)
    parser.add_argument("--web-user-id", type=int, default=3)
    parser.add_argument("--web-pwd-ver", type=int, default=0)
    parser.add_argument("--task-timeout", type=float, default=3600)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            os.getenv(
                "XDG_STATE_HOME",
                str(Path.home() / ".local/state"),
            )
        )
        / "allbot/ltx-unified-smoke",
    )
    args = parser.parse_args()
    image_key = args.image_object_key.strip()
    end_key = args.end_image_object_key.strip() or image_key
    video_key = args.video_object_key.strip()
    character_key = args.character_sheet_object_key.strip() or image_key
    if not image_key or not video_key:
        raise LtxUnifiedSmokeError(
            "image and video object keys are required; pass flags or the "
            "LTX_UNIFIED_CANARY_* environment variables"
        )
    cases = build_cases(
        image_key=image_key,
        end_image_key=end_key,
        video_key=video_key,
        character_sheet_key=character_key,
    )
    if not args.execute:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "expected_agent_id": args.expected_agent_id,
                    "cases": [
                        {
                            "label": case["label"],
                            "task_type": case["expected_central_task_type"],
                        }
                        for case in cases
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    http = RunPodHttpClient(error_type=LtxUnifiedSmokeError)
    control = RunPodControlClient(
        RunPodControlConfig(
            central_url=args.central_url,
            web_user_id=args.web_user_id,
            web_pwd_ver=args.web_pwd_ver,
            web_bearer_token=os.getenv("RUNPOD_CANARY_WEB_BEARER_TOKEN", ""),
            agent_token="",
            jwt_channel="runpod_canary",
        ),
        http_json_func=http.json,
        error_type=LtxUnifiedSmokeError,
    )
    workers = control.fetch_workers()
    worker = next(
        (
            item
            for item in workers
            if str(item.get("agent_id") or "") == args.expected_agent_id
        ),
        None,
    )
    if not worker:
        raise LtxUnifiedSmokeError("expected unified agent is not registered")
    supported = {
        value.strip()
        for value in str(worker.get("types") or "").split(",")
        if value.strip()
    }
    if not set(EXPECTED_TYPES) <= supported:
        raise LtxUnifiedSmokeError("unified agent does not advertise all five types")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "expected_agent_id": args.expected_agent_id,
        "tasks": [],
    }

    def phase(
        _: dict[str, Any],
        name: str,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        print(
            json.dumps(
                {"phase": name, "status": status, "detail": detail or {}},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    def executor(task_type: str) -> RunPodCloudTestCanaryExecutor:
        config = RunPodCloudTestCanaryConfig(
            task_type=task_type,
            web_api_url=args.web_api_url,
            central_url=args.central_url,
            input_object_key=image_key,
            scail2_reference_object_key="",
            scail2_motion_video_object_key="",
            output_dir=args.output_dir,
            download_results_dir=args.output_dir,
            task_timeout_seconds=args.task_timeout,
            task_poll_interval_seconds=args.poll_interval,
            prompt="",
            negative_prompt="",
            result_bucket="user-data-prod",
        )
        return RunPodCloudTestCanaryExecutor(
            config,
            http_json_func=http.json,
            http_request_func=http.request,
            web_auth_headers_func=control.web_auth_headers,
            fetch_workers_func=control.fetch_workers,
            sleep_func=time.sleep,
            phase_func=phase,
            error_type=LtxUnifiedSmokeError,
        )

    for case in cases:
        group = (
            "ltx_t2v"
            if case["expected_central_task_type"] in {"ltx_t2v", "ltx_t2v_ic"}
            else "ltx_video"
        )
        result = executor(group).run_task_case(case, worker, summary)
        downloaded = Path(str(result.get("downloaded_file") or ""))
        if not downloaded.is_file():
            raise LtxUnifiedSmokeError(f"{case['label']}: result was not downloaded")
        result["media"] = _ffprobe(downloaded)
        summary["tasks"].append(result)

    summary["ok"] = True
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    evidence = args.output_dir / "evidence.json"
    evidence.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
