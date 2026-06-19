#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_ENV_FILE = ROOT / ".env.cloud.test"
DEFAULT_OUTPUT_ROOT = ROOT / "logs" / "scail2_audio_workflow_smoke"
DEFAULT_API_BASE_URL = "https://web-test.aivison.it.com/api"
DEFAULT_PASSWORD = "scail2-audio-smoke-password"
DEFAULT_USER_ID = 920260620001
DEFAULT_USERNAME = "scail2_audio_smoke"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}


@dataclass(frozen=True)
class ObjectCandidate:
    key: str
    size: int
    last_modified: str | None


def load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)

    if os.getenv("CLOUD_TEST_DATABASE_URL"):
        os.environ["DATABASE_URL"] = os.environ["CLOUD_TEST_DATABASE_URL"]
    if os.getenv("CLOUD_TEST_REDIS_URL"):
        os.environ["REDIS_URL"] = os.environ["CLOUD_TEST_REDIS_URL"]


def http_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> Any:
    body = None
    headers = {"User-Agent": "allbot-scail2-audio-smoke/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc
    return json.loads(text) if text else {}


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return url
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, "", "")
    )


def object_extension(key: str) -> str:
    return Path(urllib.parse.urlsplit(key).path).suffix.lower()


def object_score(key: str) -> int:
    score = 0
    lowered = key.lower()
    if lowered.startswith(("web_uploads/", "uploads/", "user_uploads/")):
        score += 100
    if "input" in lowered or "upload" in lowered:
        score += 25
    if lowered.startswith("history/"):
        score -= 25
    if "thumb" in lowered or "thumbnail" in lowered:
        score -= 100
    return score


def build_s3_client():
    import boto3
    from botocore.config import Config

    endpoint = os.environ["MINIO_ENDPOINT"]
    if not endpoint.startswith(("http://", "https://")):
        secure = os.getenv("MINIO_SECURE", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        endpoint = f"{'https' if secure else 'http'}://{endpoint}"

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        region_name=os.getenv("MINIO_REGION") or "auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 2},
            connect_timeout=10,
            read_timeout=60,
        ),
    )


def list_candidates(
    client,
    *,
    bucket: str,
    extensions: set[str],
    max_size: int,
    min_size: int,
    max_objects: int,
) -> list[ObjectCandidate]:
    paginator = client.get_paginator("list_objects_v2")
    candidates: list[ObjectCandidate] = []
    scanned = 0
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            scanned += 1
            if scanned > max_objects:
                return candidates
            key = str(item.get("Key") or "")
            size = int(item.get("Size") or 0)
            if object_extension(key) not in extensions:
                continue
            if size < min_size or size > max_size:
                continue
            modified = item.get("LastModified")
            candidates.append(
                ObjectCandidate(
                    key=key,
                    size=size,
                    last_modified=modified.isoformat() if modified else None,
                )
            )
    return candidates


def choose_candidate(candidates: list[ObjectCandidate]) -> ObjectCandidate:
    if not candidates:
        raise RuntimeError("No matching R2 fixture object was found")
    return sorted(
        candidates,
        key=lambda item: (
            object_score(item.key),
            item.last_modified or "",
            -item.size,
        ),
        reverse=True,
    )[0]


def download_s3_object(client, *, bucket: str, key: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as file:
        client.download_fileobj(bucket, key, file)


def download_url(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "allbot-scail2-audio-smoke/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        with destination.open("wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "asset"


def extension_for_url(url: str) -> str:
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if ext:
        return ext
    guessed = mimetypes.guess_extension("video/mp4")
    return guessed or ".mp4"


def probe_media(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "reason": "missing"}
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError:
        return {"available": False, "reason": "ffprobe_not_found"}
    except subprocess.SubprocessError as exc:
        return {"available": False, "reason": str(exc)}
    payload = json.loads(completed.stdout or "{}")
    streams = payload.get("streams") or []
    return {
        "available": True,
        "streams": streams,
        "audio_streams": [
            stream for stream in streams if stream.get("codec_type") == "audio"
        ],
        "video_streams": [
            stream for stream in streams if stream.get("codec_type") == "video"
        ],
        "format": payload.get("format") or {},
    }


async def ensure_smoke_user(*, user_id: int, username: str, password: str) -> int:
    from sqlalchemy import func, or_, select

    from src.core.auth_core_password_hash import get_password_hash_sync
    from src.database.core import AsyncSessionLocal
    from src.database.models import User
    from src.quota import QuotaManager

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(
                or_(
                    User.id == user_id,
                    func.lower(User.username) == username.lower(),
                )
            )
        )
        user = result.scalar_one_or_none()
        hashed_password = get_password_hash_sync(password)
        if user is None:
            user = User(
                id=user_id,
                username=username,
                full_name="SCAIL2 Audio Smoke",
                hashed_password=hashed_password,
                password_version=1,
                credits=6,
                user_group="\u7ec3\u6c14\u671f",
                current_identity="\u5185\u95e8\u5f1f\u5b50",
                is_channel_member=True,
            )
            session.add(user)
        else:
            user.username = username
            user.full_name = "SCAIL2 Audio Smoke"
            user.hashed_password = hashed_password
            user.password_version = int(user.password_version or 1) + 1
            user.user_group = "\u7ec3\u6c14\u671f"
            user.current_identity = "\u5185\u95e8\u5f1f\u5b50"
            user.is_channel_member = True
        await session.commit()
        actual_user_id = int(user.id)

    quota = QuotaManager()
    current = await quota.get_credits(actual_user_id)
    target_credits = int(os.getenv("SCAIL2_AUDIO_SMOKE_TARGET_CREDITS", "500"))
    if current < target_credits:
        await quota.add_credits(
            actual_user_id,
            target_credits - current,
            username=username,
            task_type="scail2_audio_smoke_seed",
            extra_info={"script": "smoke_web_scail2_audio_workflow.py"},
        )
    return actual_user_id


async def load_history_snapshot(task_id: str, user_id: int) -> dict[str, Any] | None:
    from sqlalchemy import select

    from src.database.core import AsyncSessionLocal
    from src.database.models import History

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(History).where(History.task_id == task_id, History.user_id == user_id)
        )
        hist = result.scalar_one_or_none()
        if hist is None:
            return None
        return {
            "task_id": hist.task_id,
            "type": hist.type,
            "input_file": hist.input_file,
            "output_file": hist.output_file,
            "source": hist.source,
            "requested_duration": hist.requested_duration,
            "duration": hist.duration,
            "extra_outputs": hist.extra_outputs,
            "allow_contribute": hist.allow_contribute,
        }


def login(api_base_url: str, *, username: str, password: str) -> str:
    payload = http_json(
        "POST",
        f"{api_base_url}/auth/login",
        payload={"username": username, "password": password},
    )
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Password login did not return an access token")
    return str(token)


def submit_task(
    api_base_url: str,
    *,
    token: str,
    task_type: str,
    reference_key: str,
    motion_key: str,
    prompt: str,
    negative_prompt: str,
    duration: int,
) -> dict[str, Any]:
    return http_json(
        "POST",
        f"{api_base_url}/tasks/generate",
        token=token,
        payload={
            "task_type": task_type,
            "inputs": {
                "images": [reference_key, motion_key],
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "duration": duration,
            },
            "priority": 0,
            "is_template": False,
        },
    )


def poll_result(
    api_base_url: str,
    *,
    token: str,
    task_id: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        last_payload = http_json(
            "GET",
            f"{api_base_url}/tasks/{urllib.parse.quote(task_id)}/result",
            token=token,
            timeout=60,
        )
        status = str(last_payload.get("status") or "").lower()
        if status in {"done", "success"} and last_payload.get("result_url"):
            return last_payload
        if status in {"error", "failed", "cancelled"}:
            raise RuntimeError(f"Task {task_id} ended with {status}: {last_payload}")
        time.sleep(interval_seconds)
    raise TimeoutError(
        f"Timed out waiting for task {task_id}; last={json.dumps(last_payload, ensure_ascii=False)}"
    )


def build_case_dir(output_root: Path, case_label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return output_root / f"{stamp}_{safe_filename(case_label)}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one Web API SCAIL-2 workflow smoke and save input/output media."
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-base-url", default=os.getenv("CLOUD_TEST_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--case-label", required=True)
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--expected-workflow", required=True)
    parser.add_argument("--reference-key")
    parser.add_argument("--motion-key")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-interval-seconds", type=int, default=10)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--user-id", type=int, default=DEFAULT_USER_ID)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=os.getenv("SCAIL2_AUDIO_SMOKE_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--token", help="Existing Web API bearer token. Skips password login when set.")
    parser.add_argument(
        "--skip-user-seed",
        action="store_true",
        help="Do not create or top up the smoke user from this process.",
    )
    parser.add_argument("--r2-list-max-objects", type=int, default=5000)
    return parser.parse_args()


async def amain() -> int:
    args = parse_args()
    load_env_file(args.env_file)

    user_id = args.user_id
    if not args.skip_user_seed:
        user_id = await ensure_smoke_user(
            user_id=args.user_id,
            username=args.username,
            password=args.password,
        )
    token = args.token or login(
        args.api_base_url.rstrip("/"),
        username=args.username,
        password=args.password,
    )

    bucket = os.getenv("MINIO_INPUT_BUCKET") or os.getenv("MINIO_BUCKET")
    if not bucket:
        raise RuntimeError("MINIO_INPUT_BUCKET or MINIO_BUCKET is required")
    client = build_s3_client()

    reference = (
        ObjectCandidate(args.reference_key, 0, None)
        if args.reference_key
        else choose_candidate(
            list_candidates(
                client,
                bucket=bucket,
                extensions=IMAGE_EXTENSIONS,
                max_size=10 * 1024 * 1024,
                min_size=1024,
                max_objects=args.r2_list_max_objects,
            )
        )
    )
    motion = (
        ObjectCandidate(args.motion_key, 0, None)
        if args.motion_key
        else choose_candidate(
            list_candidates(
                client,
                bucket=bucket,
                extensions=VIDEO_EXTENSIONS,
                max_size=40 * 1024 * 1024,
                min_size=32 * 1024,
                max_objects=args.r2_list_max_objects,
            )
        )
    )

    case_dir = build_case_dir(args.output_root, args.case_label)
    input_dir = case_dir / "inputs"
    output_dir = case_dir / "outputs"
    report_dir = case_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    reference_path = input_dir / f"reference{object_extension(reference.key) or '.img'}"
    motion_path = input_dir / f"motion{object_extension(motion.key) or '.video'}"
    download_s3_object(client, bucket=bucket, key=reference.key, destination=reference_path)
    download_s3_object(client, bucket=bucket, key=motion.key, destination=motion_path)

    prompt = f"cloud-test scail2 audio workflow smoke {args.case_label}"
    submission = submit_task(
        args.api_base_url.rstrip("/"),
        token=token,
        task_type=args.task_type,
        reference_key=reference.key,
        motion_key=motion.key,
        prompt=prompt,
        negative_prompt="low quality, blur",
        duration=args.duration,
    )
    task_id = str(submission["task_id"])
    result = poll_result(
        args.api_base_url.rstrip("/"),
        token=token,
        task_id=task_id,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.poll_interval_seconds,
    )

    result_url = str(result["result_url"])
    result_ext = extension_for_url(result_url)
    output_path = output_dir / f"{safe_filename(args.case_label)}_{task_id}{result_ext}"
    download_url(result_url, output_path)

    try:
        history = await load_history_snapshot(task_id, user_id)
    except Exception as exc:
        history = {"unavailable": True, "reason": str(exc)}
    probes = {
        "reference": probe_media(reference_path),
        "motion": probe_media(motion_path),
        "output": probe_media(output_path),
    }
    report = {
        "case_label": args.case_label,
        "task_type": args.task_type,
        "expected_workflow": args.expected_workflow,
        "task_id": task_id,
        "submission": submission,
        "result": {
            **result,
            "result_url": sanitize_url(result.get("result_url")),
        },
        "history": history,
        "fixtures": {
            "bucket": bucket,
            "reference_key": reference.key,
            "motion_key": motion.key,
            "reference_size": reference.size,
            "motion_size": motion.size,
        },
        "files": {
            "reference": str(reference_path),
            "motion": str(motion_path),
            "output": str(output_path),
        },
        "media_probe": probes,
    }
    report_path = report_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "case_label": args.case_label,
                "task_id": task_id,
                "case_dir": str(case_dir),
                "output_path": str(output_path),
                "report_path": str(report_path),
                "input_has_audio": bool(probes["motion"].get("audio_streams")),
                "output_has_audio": bool(probes["output"].get("audio_streams")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
