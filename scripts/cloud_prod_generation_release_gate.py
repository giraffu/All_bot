#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ops.generation_release_refund import (  # noqa: E402
    PENDING_KEY,
    RUNNING_KEY,
    build_queue_snapshot,
    cancel_backend_pending,
    load_active_tasks,
)


DEFAULT_ENV_FILE = ROOT / ".env.cloud.prod"
DEFAULT_CONTROL_HOST = "allbot-do-sgp1-control"
MAINTENANCE_SERVICES = (
    "web-api",
    "bot",
    "qqcc-bot",
    "qqcc-private-bot-worker",
)
MAINTENANCE_PROJECT = "allbot-prod"
GENERATION_MAINTENANCE_HOST_PATH = (
    "/var/lib/allbot/prod/runtime/GENERATION_MAINTENANCE"
)
GENERATION_MAINTENANCE_RUNTIME_PATH = "/app/runtime-flags/GENERATION_MAINTENANCE"
PROD_WEB_ENV_FILE = "/var/lib/allbot/config/prod/current/web-api.env"
PROD_COMPOSE_NETWORK = "allbot-prod_default"
EXACT_DIGEST_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def configure_process_env(values: dict[str, str]) -> None:
    mapping = {
        "DATABASE_URL": values.get("CLOUD_PROD_DATABASE_URL"),
        "REDIS_URL": values.get("CLOUD_PROD_REDIS_URL"),
        "WORKER_REDIS_URL": values.get("CLOUD_PROD_WORKER_REDIS_URL"),
        "API_BASE": "https://worker-central.aivison.it.com",
        "REDIS_PREFIX": "prod_bot_",
        "BOT_TYPE": "PROD",
    }
    passthrough = (
        "API_TOKEN",
        "AUTH_TOKEN",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
        "MINIO_INPUT_BUCKET",
        "MINIO_RESULT_BUCKET",
        "MINIO_TEMPLATE_BUCKET",
        "MINIO_SECURE",
        "R2_ENDPOINT",
        "R2_ACCESS_KEY",
        "R2_SECRET_KEY",
        "R2_BUCKET",
        "R2_PUBLIC_DOMAIN",
    )
    for key in passthrough:
        mapping[key] = values.get(key)
    for key, value in mapping.items():
        if value and not os.environ.get(key):
            os.environ[key] = value


def require_env(values: dict[str, str], *keys: str) -> None:
    missing = [key for key in keys if not values.get(key) and not os.environ.get(key)]
    if missing:
        raise SystemExit("missing required env keys: " + ", ".join(missing))


def run_ssh(host: str, script: str, *, execute: bool) -> None:
    if not execute:
        print(f"[dry-run] ssh {host!r} <<'REMOTE'\n{script.rstrip()}\nREMOTE")
        return
    subprocess.run(["ssh", host, "bash", "-s"], input=script, text=True, check=True)


def set_maintenance(host: str, *, enabled: bool, execute: bool) -> None:
    if enabled:
        operation = (
            f"install -d -m 700 {shlex.quote(str(Path(GENERATION_MAINTENANCE_HOST_PATH).parent))}\n"
            f"tmp={shlex.quote(GENERATION_MAINTENANCE_HOST_PATH)}.$$"
            "\nprintf '1\\n' > \"$tmp\"\nchmod 600 \"$tmp\"\n"
            f"mv \"$tmp\" {shlex.quote(GENERATION_MAINTENANCE_HOST_PATH)}"
        )
    else:
        operation = f"rm -f {shlex.quote(GENERATION_MAINTENANCE_HOST_PATH)}"
    expected_check = (
        f"test -f {GENERATION_MAINTENANCE_RUNTIME_PATH}"
        if enabled
        else f"test ! -f {GENERATION_MAINTENANCE_RUNTIME_PATH}"
    )
    script = "\n".join(
        [
            "set -euo pipefail",
            operation,
            f"for service in {' '.join(MAINTENANCE_SERVICES)}; do",
            "  container=$(docker ps -q "
            f"--filter label=com.docker.compose.project={MAINTENANCE_PROJECT} "
            "--filter label=com.docker.compose.service=\"$service\" | head -n1)",
            "  test -n \"$container\" || { echo \"$service missing\" >&2; exit 1; }",
            f"  docker exec \"$container\" sh -lc {expected_check!r}",
            "  echo \"$service maintenance verified\"",
            "done",
        ]
    )
    run_ssh(host, script, execute=execute)


def maintenance_status(host: str) -> None:
    script = "\n".join(
        [
            "set -euo pipefail",
            f"for service in {' '.join(MAINTENANCE_SERVICES)}; do",
            "  container=$(docker ps -q "
            f"--filter label=com.docker.compose.project={MAINTENANCE_PROJECT} "
            "--filter label=com.docker.compose.service=\"$service\" | head -n1)",
            "  if [ -n \"$container\" ]; then",
            f"    if docker exec \"$container\" sh -lc 'test -f {GENERATION_MAINTENANCE_RUNTIME_PATH}'; then",
            "      echo \"$service=generation_maintenance\"",
            "    else",
            "      echo \"$service=open\"",
            "    fi",
            "  else",
            "    echo \"$service=not_running\"",
            "  fi",
            "done",
        ]
    )
    subprocess.run(["ssh", host, "bash", "-s"], input=script, text=True, check=True)


def run_refund_runtime(args) -> None:
    artifact = str(args.runtime_image or "")
    revision = str(args.runtime_sha or "")
    if not EXACT_DIGEST_RE.fullmatch(artifact):
        raise SystemExit("refund-pending requires --runtime-image as an exact digest")
    if not FULL_SHA_RE.fullmatch(revision):
        raise SystemExit("refund-pending requires a full --runtime-sha")

    quoted_artifact = shlex.quote(artifact)
    runtime_args = [
        "-m",
        "src.ops.generation_release_refund",
        "--threshold",
        str(args.threshold),
    ]
    if args.allow_above_threshold:
        runtime_args.append("--allow-above-threshold")
    if args.execute:
        runtime_args.append("--execute")
    rendered_args = " ".join(shlex.quote(value) for value in runtime_args)
    script = "\n".join(
        [
            "set -euo pipefail",
            f"docker pull {quoted_artifact}",
            "labels=$(docker image inspect --format "
            "'{{index .Config.Labels \"io.allbot.release.module\"}}|"
            "{{index .Config.Labels \"org.opencontainers.image.revision\"}}' "
            f"{quoted_artifact})",
            f"test \"$labels\" = {shlex.quote('web-api|' + revision)}",
            "docker run --rm "
            f"--network {PROD_COMPOSE_NETWORK} "
            f"--env-file {PROD_WEB_ENV_FILE} "
            "--entrypoint python "
            f"{quoted_artifact} {rendered_args}",
        ]
    )
    run_ssh(
        args.control_host,
        script,
        execute=bool(args.run_runtime or args.execute),
    )


async def connect_redis(url: str):
    import redis.asyncio as redis

    return redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
        retry_on_timeout=False,
    )


async def print_status(args, values: dict[str, str]) -> None:
    app_redis = await connect_redis(os.environ["REDIS_URL"])
    worker_redis = await connect_redis(os.environ["WORKER_REDIS_URL"])
    try:
        snapshot = await build_queue_snapshot(
            worker_redis,
            app_redis,
            os.environ.get("REDIS_PREFIX", "prod_bot_"),
        )
        print(
            json.dumps(
                {
                    "pending_count": len(snapshot["pending_backend_ids"]),
                    "running_count": len(snapshot["running_backend_ids"]),
                    "active_task_count": len(snapshot["active_tasks"]),
                    "mapped_pending_count": snapshot["mapped_pending_count"],
                    "orphan_pending_count": snapshot["orphan_pending_count"],
                    "threshold": args.threshold,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await app_redis.aclose()
        await worker_redis.aclose()


async def wait_pending_below(args, values: dict[str, str]) -> None:
    deadline = time.time() + args.timeout_seconds
    app_redis = await connect_redis(os.environ["REDIS_URL"])
    worker_redis = await connect_redis(os.environ["WORKER_REDIS_URL"])
    try:
        last_count = None
        while time.time() < deadline:
            snapshot = await build_queue_snapshot(
                worker_redis,
                app_redis,
                os.environ.get("REDIS_PREFIX", "prod_bot_"),
            )
            count = len(snapshot["pending_backend_ids"])
            if count < args.threshold:
                print(f"pending_count={count} below threshold={args.threshold}")
                return
            if count != last_count:
                print(f"waiting pending_count={count} threshold={args.threshold}")
                last_count = count
            await asyncio.sleep(args.interval_seconds)
        raise SystemExit(
            f"timed out waiting for pending_count < {args.threshold}"
        )
    finally:
        await app_redis.aclose()
        await worker_redis.aclose()


async def async_main(args) -> None:
    values = load_env_file(Path(args.env_file))
    configure_process_env(values)
    require_env(
        values,
        "CLOUD_PROD_REDIS_URL",
        "CLOUD_PROD_WORKER_REDIS_URL",
        "CLOUD_PROD_DATABASE_URL",
    )
    if args.action == "status":
        await print_status(args, values)
    elif args.action == "wait-pending":
        await wait_pending_below(args, values)
    else:
        raise SystemExit(f"unsupported async action: {args.action}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cloud prod generation release gate for maintenance, queue drain and pending refunds."
    )
    parser.add_argument(
        "action",
        choices=(
            "status",
            "enable-maintenance",
            "disable-maintenance",
            "maintenance-status",
            "wait-pending",
            "refund-pending",
        ),
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--control-host", default=DEFAULT_CONTROL_HOST)
    parser.add_argument("--threshold", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--allow-above-threshold", action="store_true")
    parser.add_argument("--runtime-image")
    parser.add_argument("--runtime-sha")
    parser.add_argument(
        "--run-runtime",
        action="store_true",
        help="run an immutable refund dry-run on the control host",
    )
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.action == "enable-maintenance":
        set_maintenance(args.control_host, enabled=True, execute=args.execute)
        return 0
    if args.action == "disable-maintenance":
        set_maintenance(args.control_host, enabled=False, execute=args.execute)
        return 0
    if args.action == "maintenance-status":
        maintenance_status(args.control_host)
        return 0
    if args.action == "refund-pending":
        run_refund_runtime(args)
        return 0
    asyncio.run(async_main(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
