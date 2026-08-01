#!/usr/bin/env python3
"""Run an isolated Ingredients versus Sulphur+Ingredients ComfyUI A/B canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.comfy_agent.workflow_patcher import WorkflowPatcher  # noqa: E402


BASELINE_WORKFLOW = (
    "ops/gpu_pool_controller/validation_workflows/ltx_t2v/"
    "03_dev_distilled_ingredients_t2v.json"
)
SULPHUR_WORKFLOW = (
    "ops/gpu_pool_controller/validation_workflows/ltx_t2v/"
    "04_dev_distilled_sulphur_ingredients_t2v.json"
)
REQUIRED_NODE_TYPES = {
    "CheckpointLoaderSimple",
    "GetICLoRAParameters",
    "KSampler",
    "LoraLoaderModelOnly",
    "LTXVAddGuide",
    "LTXVCropGuides",
}


class AbCanaryError(RuntimeError):
    pass


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_cases(
    *,
    repo_root: Path,
    character_sheet_name: str,
    character_description: str,
    prompt: str,
    seed: int,
    durations: tuple[int, ...],
) -> list[dict[str, Any]]:
    if not character_sheet_name.strip():
        raise AbCanaryError("character sheet filename is required")
    if not character_description.strip():
        raise AbCanaryError("character description is required")
    if not prompt.strip():
        raise AbCanaryError("target prompt is required")
    if seed < 0:
        raise AbCanaryError("seed must be non-negative")
    if not durations or any(duration not in {5, 10} for duration in durations):
        raise AbCanaryError("A/B durations must contain only 5 and/or 10 seconds")

    variants = (
        ("ingredients", False, repo_root / BASELINE_WORKFLOW),
        ("sulphur_ingredients", True, repo_root / SULPHUR_WORKFLOW),
    )
    patcher = WorkflowPatcher(str(repo_root / "workers/comfy_agent/workflows"))
    cases: list[dict[str, Any]] = []
    for duration in durations:
        for variant, sulphur, path in variants:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            workflow = patcher.patch_workflow(
                "ltx_t2v_ic",
                workflow,
                {
                    "prompt": prompt,
                    "duration": duration,
                    "character_sheet": character_sheet_name,
                    "character_description": character_description,
                    "seed": seed,
                },
            )
            cases.append(
                {
                    "label": f"{variant}_{duration}s",
                    "duration": duration,
                    "seed": seed,
                    "sulphur": sulphur,
                    "source_workflow": str(path.relative_to(repo_root)),
                    "workflow": workflow,
                }
            )
    return cases


def case_evidence_metadata(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": case["label"],
        "duration_seconds": case["duration"],
        "seed": case["seed"],
        "sulphur": case["sulphur"],
        "source_workflow": case["source_workflow"],
        "workflow_sha256": hashlib.sha256(
            _canonical_json_bytes(case["workflow"])
        ).hexdigest(),
        "model_chain": (
            ["checkpoint:127", "sulphur:258", "ingredients:195", "ic_params:196"]
            if case["sulphur"]
            else ["checkpoint:127", "ingredients:195", "ic_params:196"]
        ),
    }


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 30,
) -> Any:
    data = None
    headers = {"User-Agent": "allbot-ltx-ic-ab-canary/1.0"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8")) if body else {}


def _upload_image(*, comfy_url: str, path: Path, remote_name: str) -> str:
    boundary = f"----allbot-{uuid.uuid4().hex}"
    image_bytes = path.read_bytes()
    fields = [
        ("overwrite", b"true"),
        ("type", b"input"),
    ]
    body = bytearray()
    for name, value in fields:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value + b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="image"; filename="{remote_name}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
    )
    body.extend(image_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        f"{comfy_url.rstrip('/')}/upload/image",
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "allbot-ltx-ic-ab-canary/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    uploaded_name = str(result.get("name") or "").strip()
    if not uploaded_name:
        raise AbCanaryError("ComfyUI image upload did not return a filename")
    subfolder = str(result.get("subfolder") or "").strip("/")
    return f"{subfolder}/{uploaded_name}" if subfolder else uploaded_name


def validate_runtime_models(object_info: dict[str, Any]) -> None:
    missing = sorted(node for node in REQUIRED_NODE_TYPES if node not in object_info)
    if missing:
        raise AbCanaryError("missing ComfyUI node types: " + ", ".join(missing))
    loras = (
        object_info.get("LoraLoaderModelOnly", {})
        .get("input", {})
        .get("required", {})
        .get("lora_name", [[]])[0]
    )
    checkpoints = (
        object_info.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    required_loras = {
        "ltx2.3/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
        "ltx2.3/sulphur_lora_rank_768.safetensors",
    }
    missing_loras = sorted(required_loras - set(loras))
    if missing_loras:
        raise AbCanaryError("missing required LoRA models: " + ", ".join(missing_loras))
    checkpoint = "LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors"
    if checkpoint not in checkpoints:
        raise AbCanaryError("missing required Ingredients checkpoint")


def _collect_video_outputs(history_entry: dict[str, Any]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for node_output in (history_entry.get("outputs") or {}).values():
        for output_key in ("gifs", "videos", "images"):
            for item in node_output.get(output_key) or []:
                if str(item.get("filename") or "").lower().endswith(".mp4"):
                    videos.append(item)
    return videos


def submit_and_wait(
    *,
    comfy_url: str,
    workflow: dict[str, Any],
    timeout_seconds: float,
    poll_seconds: float,
    http_json_func: Callable[..., Any] = _http_json,
    sleep_func: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    submit = http_json_func(
        "POST",
        f"{comfy_url.rstrip('/')}/prompt",
        {"prompt": workflow, "client_id": f"allbot-ab-{uuid.uuid4().hex}"},
    )
    prompt_id = str(submit.get("prompt_id") or "").strip()
    if not prompt_id:
        raise AbCanaryError("ComfyUI did not return a prompt_id")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        history = http_json_func(
            "GET", f"{comfy_url.rstrip('/')}/history/{prompt_id}"
        )
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status") or {}
            if status.get("completed") is False or status.get("status_str") == "error":
                raise AbCanaryError(
                    f"ComfyUI execution failed for prompt_id={prompt_id}"
                )
            videos = _collect_video_outputs(entry)
            if not videos:
                raise AbCanaryError(
                    f"ComfyUI completed without MP4 output for prompt_id={prompt_id}"
                )
            return {"prompt_id": prompt_id, "history": entry, "videos": videos}
        sleep_func(poll_seconds)
    raise TimeoutError(f"timed out waiting for prompt_id={prompt_id}")


def _download_output(*, comfy_url: str, output: dict[str, Any], target: Path) -> None:
    query = urllib.parse.urlencode(
        {
            "filename": output.get("filename", ""),
            "subfolder": output.get("subfolder", ""),
            "type": output.get("type", "output"),
        }
    )
    request = urllib.request.Request(
        f"{comfy_url.rstrip('/')}/view?{query}",
        headers={"User-Agent": "allbot-ltx-ic-ab-canary/1.0"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = response.read()
    if not payload:
        raise AbCanaryError("ComfyUI returned an empty MP4 output")
    target.write_bytes(payload)


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
    return json.loads(result.stdout)


def validate_media_contract(
    probe: dict[str, Any], *, expected_duration: int
) -> dict[str, Any]:
    streams = probe.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video:
        raise AbCanaryError("MP4 output is missing a video stream")
    rate = str(video.get("avg_frame_rate") or "0/1").split("/", 1)
    fps = float(rate[0]) / float(rate[1])
    duration = float((probe.get("format") or {}).get("duration") or 0)
    if int(video.get("width") or 0) != 768 or int(video.get("height") or 0) != 448:
        raise AbCanaryError("MP4 output resolution is not 768x448")
    if abs(fps - 24.0) > 0.1:
        raise AbCanaryError("MP4 output frame rate is not 24fps")
    if abs(duration - expected_duration) > 1.0:
        raise AbCanaryError("MP4 output duration is outside the allowed tolerance")
    if not any(item.get("codec_type") == "audio" for item in streams):
        raise AbCanaryError("MP4 output is missing an audio stream")
    return {
        "duration_seconds": duration,
        "fps": fps,
        "width": int(video["width"]),
        "height": int(video["height"]),
        "has_audio": True,
    }


def _make_contact_sheet(*, video: Path, target: Path, duration: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"fps=5/{duration},scale=384:-1,tile=5x1",
            "-frames:v",
            "1",
            str(target),
        ],
        check=True,
    )


def _gpu_stats(*, ssh_host: str, gpu_index: int) -> dict[str, Any]:
    query = (
        "nvidia-smi --query-gpu=index,memory.total,memory.used,utilization.gpu,"
        "temperature.gpu --format=csv,noheader,nounits"
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", ssh_host, query],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if fields and int(fields[0]) == gpu_index:
            return {
                "index": gpu_index,
                "memory_total_mib": int(fields[1]),
                "memory_used_mib": int(fields[2]),
                "utilization_percent": int(fields[3]),
                "temperature_c": int(fields[4]),
            }
    raise AbCanaryError(f"GPU index {gpu_index} was not reported by nvidia-smi")


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--comfy-url", default="http://192.168.1.177:8191")
    parser.add_argument("--character-sheet", type=Path, required=True)
    parser.add_argument("--character-description-file", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--durations", type=int, nargs="+", default=[5, 10])
    parser.add_argument("--gpu-ssh-host", default="allbot-gpu-177")
    parser.add_argument("--gpu-index", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    description = args.character_description_file.read_text(encoding="utf-8").strip()
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    remote_name = f"allbot-ltx-ic-ab-{run_id}.png"
    cases = build_cases(
        repo_root=ROOT,
        character_sheet_name=remote_name,
        character_description=description,
        prompt=prompt,
        seed=args.seed,
        durations=tuple(args.durations),
    )
    dry_run = {
        "ok": True,
        "dry_run": not args.execute,
        "seed": args.seed,
        "durations": list(args.durations),
        "cases": [case_evidence_metadata(case) for case in cases],
    }
    if not args.execute:
        print(json.dumps(dry_run, ensure_ascii=False, indent=2))
        return 0

    output_dir = args.output_dir or (
        Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "allbot/ltx-ic-sulphur-ab"
        / run_id
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    evidence: dict[str, Any] = {
        **dry_run,
        "dry_run": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "results": [],
    }
    _write_json(output_dir / "evidence.json", evidence)
    try:
        object_info = _http_json("GET", f"{args.comfy_url.rstrip('/')}/object_info")
        validate_runtime_models(object_info)
        uploaded_name = _upload_image(
            comfy_url=args.comfy_url,
            path=args.character_sheet,
            remote_name=remote_name,
        )
        for case in cases:
            case["workflow"]["270"]["inputs"]["image"] = uploaded_name
            before = _gpu_stats(ssh_host=args.gpu_ssh_host, gpu_index=args.gpu_index)
            started = time.monotonic()
            result = submit_and_wait(
                comfy_url=args.comfy_url,
                workflow=case["workflow"],
                timeout_seconds=args.timeout_seconds,
                poll_seconds=args.poll_seconds,
            )
            elapsed = time.monotonic() - started
            video_path = output_dir / f"{case['label']}.mp4"
            _download_output(
                comfy_url=args.comfy_url,
                output=result["videos"][0],
                target=video_path,
            )
            media = validate_media_contract(
                _ffprobe(video_path), expected_duration=case["duration"]
            )
            contact_sheet = output_dir / f"{case['label']}-contact.png"
            _make_contact_sheet(
                video=video_path,
                target=contact_sheet,
                duration=case["duration"],
            )
            after = _gpu_stats(ssh_host=args.gpu_ssh_host, gpu_index=args.gpu_index)
            evidence["results"].append(
                {
                    **case_evidence_metadata(case),
                    "prompt_id": result["prompt_id"],
                    "elapsed_seconds": round(elapsed, 3),
                    "video_file": video_path.name,
                    "contact_sheet_file": contact_sheet.name,
                    "media": media,
                    "gpu_before": before,
                    "gpu_after": after,
                }
            )
            _write_json(output_dir / "evidence.json", evidence)
        evidence["status"] = "passed"
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output_dir / "evidence.json", evidence)
    except Exception as exc:
        evidence["status"] = "failed"
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
        evidence["error_type"] = type(exc).__name__
        _write_json(output_dir / "evidence.json", evidence)
        raise
    print(json.dumps({"ok": True, "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
