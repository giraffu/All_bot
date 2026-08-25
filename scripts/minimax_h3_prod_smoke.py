#!/usr/bin/env python3
"""Submit the controlled MiniMax H3 LAN canary matrix to one expected agent."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

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


DEFAULT_WEB_URL = "https://api.aivison.it.com/api"
DEFAULT_CENTRAL_URL = "https://worker-central.aivison.it.com"
EXPECTED_TYPES = (
    "minimax_h3_t2v",
    "minimax_h3_i2v",
    "minimax_h3_flf2v",
    "minimax_h3_ref2v",
)


class MiniMaxH3SmokeError(RuntimeError):
    pass


_SIGNALSTAT_PATTERN = re.compile(
    r"lavfi\.signalstats\.(YAVG|YMAX)=([0-9]+(?:\.[0-9]+)?)"
)


def _validate_visual_content(output: str) -> dict[str, Any]:
    yavg: list[float] = []
    ymax: list[float] = []
    for name, raw_value in _SIGNALSTAT_PATTERN.findall(output):
        value = float(raw_value)
        if name == "YAVG":
            yavg.append(value)
        else:
            ymax.append(value)
    if len(yavg) < 2 or len(ymax) < 2:
        raise MiniMaxH3SmokeError("missing frame luma signalstats")
    max_yavg = max(yavg)
    max_ymax = max(ymax)
    if max_yavg <= 20.0 and max_ymax <= 32.0:
        raise MiniMaxH3SmokeError(
            "all-black video: every analyzed frame remains below the luma gate"
        )
    return {
        "frames_analyzed": len(yavg),
        "min_yavg": min(yavg),
        "max_yavg": max_yavg,
        "max_ymax": max_ymax,
    }


def _signalstats(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-vf",
            "signalstats,metadata=print:file=-",
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return _validate_visual_content(result.stdout + "\n" + result.stderr)


def build_control_config(
    *, central_url: str, web_user_id: int, web_pwd_ver: int
) -> RunPodControlConfig:
    return RunPodControlConfig(
        central_url=central_url,
        web_user_id=web_user_id,
        web_pwd_ver=web_pwd_ver,
        web_bearer_token=os.getenv("RUNPOD_CANARY_WEB_BEARER_TOKEN", ""),
        agent_token="",
        jwt_channel="runpod_canary",
    )


def build_cases(*, image_key: str, end_image_key: str) -> list[dict[str, Any]]:
    prompt = "cinematic natural motion, consistent adult subject, high detail"

    def task(
        label: str,
        task_type: str,
        *,
        duration: int = 5,
        resolution_preset: str = "preview",
        images: list[str] | None = None,
        main_model: str | None = None,
    ) -> dict[str, Any]:
        inputs: dict[str, Any] = {
            "duration": duration,
            "resolution_preset": resolution_preset,
            "aspect_ratio": (
                "source"
                if task_type in {"minimax_h3_i2v", "minimax_h3_flf2v"}
                else "16:9"
            ),
            "seed": 20260804,
            "extract_last_frame": True,
        }
        if images is not None:
            inputs["images"] = images
        if main_model is not None:
            inputs["main_model"] = main_model
        return {
            "label": label,
            "expected_central_task_type": task_type,
            "expected_duration": duration,
            "payload": {
                "task_type": task_type,
                "inputs": inputs,
                "prompt": prompt,
                "priority": 0,
            },
        }

    return [
        task("minimax_h3_t2v_5s_preview", "minimax_h3_t2v"),
        task(
            "minimax_h3_i2v_5s_preview",
            "minimax_h3_i2v",
            images=[image_key],
        ),
        task(
            "minimax_h3_flf2v_5s_preview",
            "minimax_h3_flf2v",
            images=[image_key, end_image_key],
        ),
        task(
            "minimax_h3_ref2v_10eros_5s_preview",
            "minimax_h3_ref2v",
            images=[image_key],
            main_model="10eros",
        ),
        task(
            "minimax_h3_ref2v_official_5s_preview",
            "minimax_h3_ref2v",
            images=[image_key],
            main_model="official",
        ),
        task(
            "minimax_h3_t2v_10s_standard",
            "minimax_h3_t2v",
            duration=10,
            resolution_preset="standard",
        ),
    ]


def _ffprobe(path: Path, *, expected_duration: int) -> dict[str, Any]:
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
        raise MiniMaxH3SmokeError(f"{path.name}: missing video stream")
    numerator, denominator = str(video.get("avg_frame_rate") or "0/1").split(
        "/", 1
    )
    fps = float(numerator) / float(denominator)
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if abs(fps - 24.0) > 0.1 or abs(duration - expected_duration) > 1.0:
        raise MiniMaxH3SmokeError(
            f"{path.name}: expected 24fps/{expected_duration}s, got {fps}/{duration}"
        )
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise MiniMaxH3SmokeError(f"{path.name}: missing native audio stream")
    return {
        "fps": fps,
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": True,
        "visual_content": _signalstats(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.prod"))
    parser.add_argument("--expected-agent-id", required=True)
    parser.add_argument(
        "--image-object-key",
        default=os.getenv("MINIMAX_H3_CANARY_IMAGE_OBJECT_KEY", ""),
    )
    parser.add_argument(
        "--end-image-object-key",
        default=os.getenv("MINIMAX_H3_CANARY_END_IMAGE_OBJECT_KEY", ""),
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
            os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state"))
        )
        / "allbot/minimax-h3-smoke",
    )
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False)
    image_key = args.image_object_key.strip()
    end_key = args.end_image_object_key.strip() or image_key
    if not image_key:
        raise MiniMaxH3SmokeError("image object key is required")
    cases = build_cases(image_key=image_key, end_image_key=end_key)
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
                            "duration": case["expected_duration"],
                        }
                        for case in cases
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    http = RunPodHttpClient(error_type=MiniMaxH3SmokeError)
    control = RunPodControlClient(
        build_control_config(
            central_url=args.central_url,
            web_user_id=args.web_user_id,
            web_pwd_ver=args.web_pwd_ver,
        ),
        http_json_func=http.json,
        error_type=MiniMaxH3SmokeError,
    )
    worker = next(
        (
            item
            for item in control.fetch_workers()
            if str(item.get("agent_id") or "") == args.expected_agent_id
        ),
        None,
    )
    if not worker:
        raise MiniMaxH3SmokeError("expected MiniMax H3 agent is not registered")
    supported = {
        value.strip()
        for value in str(worker.get("types") or "").split(",")
        if value.strip()
    }
    if not set(EXPECTED_TYPES) <= supported:
        raise MiniMaxH3SmokeError("agent does not advertise all three public H3 types")

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

    config = RunPodCloudTestCanaryConfig(
        task_type="minimax_h3",
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
    executor = RunPodCloudTestCanaryExecutor(
        config,
        http_json_func=http.json,
        http_request_func=http.request,
        web_auth_headers_func=control.web_auth_headers,
        fetch_workers_func=control.fetch_workers,
        sleep_func=time.sleep,
        phase_func=phase,
        error_type=MiniMaxH3SmokeError,
    )
    for case in cases:
        result = executor.run_task_case(case, worker, summary)
        downloaded = Path(str(result.get("downloaded_file") or ""))
        if not downloaded.is_file():
            raise MiniMaxH3SmokeError(f"{case['label']}: result was not downloaded")
        result["media"] = _ffprobe(
            downloaded,
            expected_duration=int(case["expected_duration"]),
        )
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
