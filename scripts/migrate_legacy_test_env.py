#!/usr/bin/env python3
"""Create the immutable-release test env from the legacy local test env.

The migration is intentionally test-only.  It keeps the last valid assignment
for existing uppercase keys, drops malformed legacy lines, and adds the
versioned worker-slot contract without ever printing configuration values.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence


VALID_KEY = re.compile(r"^[A-Z_][A-Z0-9_]*$")
DEFAULT_SLOTS = ("01", "02", "03", "04", "06", "07", "08")
SLOT_DEFAULTS: dict[str, dict[str, str]] = {
    "01": {
        "NODE_ID": "gpu-252",
        "GPU_INDEX": "0",
        "RUNTIME_PROFILE": "i2i_pro",
        "TASK_TYPES": "face_swap_v2,i2i_pro,i2i_draw,t2i-pornmaster-turbo",
        "COMFY_API_URL": "http://192.168.1.252:8192",
        "COMFY_WS_URL": "ws://192.168.1.252:8192/ws",
    },
    "02": {
        "NODE_ID": "gpu-177",
        "GPU_INDEX": "0",
        "RUNTIME_PROFILE": "wan22_video_v2",
        "TASK_TYPES": "wan22_video_v2",
        "COMFY_API_URL": "http://192.168.1.177:8190",
        "COMFY_WS_URL": "ws://192.168.1.177:8190/ws",
    },
    "03": {
        "NODE_ID": "gpu-177",
        "GPU_INDEX": "1",
        "RUNTIME_PROFILE": "ltx_video",
        "TASK_TYPES": "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio",
        "COMFY_API_URL": "http://192.168.1.177:8191",
        "COMFY_WS_URL": "ws://192.168.1.177:8191/ws",
    },
    "04": {
        "NODE_ID": "gpu-252",
        "GPU_INDEX": "0",
        "RUNTIME_PROFILE": "img2img_lora",
        "TASK_TYPES": "img2img,img2img_lora",
        "COMFY_API_URL": "http://192.168.1.252:8190",
        "COMFY_WS_URL": "ws://192.168.1.252:8190/ws",
    },
    "05": {
        "NODE_ID": "gpu-252",
        "GPU_INDEX": "1",
        "RUNTIME_PROFILE": "wan22_video_v2",
        "TASK_TYPES": "wan22_video_v2",
        "COMFY_API_URL": "http://127.0.0.1:9",
        "COMFY_WS_URL": "ws://127.0.0.1:9/ws",
    },
    "06": {
        "NODE_ID": "gpu-252",
        "GPU_INDEX": "0",
        "RUNTIME_PROFILE": "img2img_lora",
        "TASK_TYPES": "img2img,img2img_lora",
        "COMFY_API_URL": "http://192.168.1.252:8190",
        "COMFY_WS_URL": "ws://192.168.1.252:8190/ws",
    },
    "07": {
        "NODE_ID": "gpu-002",
        "GPU_INDEX": "1",
        "RUNTIME_PROFILE": "image_to_video",
        "TASK_TYPES": "image_to_video,video_insert",
        "COMFY_API_URL": "http://192.168.1.2:8191",
        "COMFY_WS_URL": "ws://192.168.1.2:8191/ws",
    },
    "08": {
        "NODE_ID": "gpu-002",
        "GPU_INDEX": "0",
        "RUNTIME_PROFILE": "scail2",
        "TASK_TYPES": (
            "scail2_action_transfer,scail2_action_transfer_long,"
            "scail2_video_replacement,scail2_face_swap_v2"
        ),
        "COMFY_API_URL": "http://192.168.1.2:8190",
        "COMFY_WS_URL": "ws://192.168.1.2:8190/ws",
    },
}


class MigrationError(RuntimeError):
    pass


def parse_legacy(lines: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    ignored: list[str] = []
    for line_number, raw_line in enumerate(lines, 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            ignored.append(f"line-{line_number}")
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not VALID_KEY.fullmatch(key):
            ignored.append(f"line-{line_number}")
            continue
        values[key] = value
    return values, ignored


def _legacy(values: Mapping[str, str], slot: str, suffix: str) -> str:
    key = f"CLOUD_TEST_WORKER_{slot}_{suffix}"
    return values.get(key, SLOT_DEFAULTS[slot][suffix])


def _normalized_task_types(slot: str, value: str) -> str:
    if slot != "01":
        return value
    normalized: list[str] = []
    for raw_type in value.split(","):
        task_type = raw_type.strip()
        if task_type == "face_swap":
            task_type = "face_swap_v2"
        if task_type and task_type not in normalized:
            normalized.append(task_type)
    return ",".join(normalized)


def migrate_values(
    legacy: Mapping[str, str],
    slots: Sequence[str] = DEFAULT_SLOTS,
    *,
    worker_legacy: Mapping[str, str] | None = None,
) -> dict[str, str]:
    unknown = sorted(set(slots) - set(SLOT_DEFAULTS))
    if unknown:
        raise MigrationError("unsupported worker slots: " + ", ".join(unknown))
    worker_values = worker_legacy or legacy
    values = dict(legacy)
    values.update(
        {
            "ALLBOT_ENV": "test",
            "ALLBOT_ENV_FILE": "/etc/allbot/test.env",
            "ALLBOT_STATE_ROOT": "/var/lib/allbot/test",
            "ALLBOT_WORKER_SERVICES": ",".join(f"worker-{slot}" for slot in slots),
            "ALLBOT_WORKER_STATE_ROOT": "/var/lib/allbot/test-worker",
            "ALLBOT_WORKER_CENTRAL_API_URL": (
                f"http://{legacy.get('CLOUD_TEST_CONTROL_HOST', '')}:8004"
            ),
            "ALLBOT_WORKER_RELAY_PORT": legacy.get(
                "CLOUD_TEST_LOCAL_RELAY_PORT",
                worker_values.get("CLOUD_TEST_LOCAL_RELAY_PORT", "8014"),
            ),
            "QQCC_CONFIG_ADMIN_HOST": legacy.get(
                "QQCC_CONFIG_ADMIN_HOST", "qqcc-admin-test.aivison.it.com"
            ),
            "PRIVATE_QQCC_BOT_OWNER_HOST": legacy.get(
                "PRIVATE_QQCC_BOT_OWNER_HOST", "private-bot-test.aivison.it.com"
            ),
        }
    )
    shared_prefetch = worker_values.get(
        "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED", "false"
    )
    shared_pipeline = worker_values.get(
        "CLOUD_TEST_SHARED_AIO_PIPELINE_ENABLED", "false"
    )
    shared_max = worker_values.get(
        "CLOUD_TEST_SHARED_AIO_PIPELINE_MAX_RUNNING_TASKS", "1"
    )
    for slot in slots:
        prefix = f"ALLBOT_WORKER_{slot}_"
        values.update(
            {
                prefix + "AGENT_ID": f"cloud_worker_test_{slot}",
                prefix + "COMFY_API_URL": _legacy(
                    worker_values, slot, "COMFY_API_URL"
                ),
                prefix + "COMFY_WS_URL": _legacy(
                    worker_values, slot, "COMFY_WS_URL"
                ),
                prefix + "TASK_TYPES": _normalized_task_types(
                    slot, _legacy(worker_values, slot, "TASK_TYPES")
                ),
                prefix + "NODE_ID": _legacy(worker_values, slot, "NODE_ID"),
                prefix + "GPU_INDEX": _legacy(worker_values, slot, "GPU_INDEX"),
                prefix + "RUNTIME_PROFILE": _legacy(
                    worker_values, slot, "RUNTIME_PROFILE"
                ),
                prefix + "PREFETCH_ENABLED": (
                    worker_values.get("PREFETCH_ENABLED", "true")
                    if slot == "01"
                    else shared_prefetch
                ),
                prefix + "PIPELINE_ENABLED": (
                    worker_values.get("PIPELINE_ENABLED", "true")
                    if slot == "01"
                    else shared_pipeline
                ),
                prefix + "PIPELINE_MAX_RUNNING_TASKS": (
                    worker_values.get("PIPELINE_MAX_RUNNING_TASKS", "2")
                    if slot == "01"
                    else shared_max
                ),
            }
        )
        workflow_key = f"CLOUD_TEST_WORKER_{slot}_TASK_TYPE_WORKFLOW_OVERRIDES"
        if workflow_key in worker_values:
            values[prefix + "TASK_TYPE_WORKFLOW_OVERRIDES"] = worker_values[
                workflow_key
            ]
    if "08" in slots:
        for suffix in (
            "FACE_SWAP_V10_ENABLED",
            "FACE_SWAP_V10_FACE_SWAP_COMFY_API_URL",
            "FACE_SWAP_V10_FACE_SWAP_WORKFLOW",
        ):
            source = f"CLOUD_TEST_WORKER_08_{suffix}"
            if source in worker_values:
                values[f"ALLBOT_WORKER_08_{suffix}"] = worker_values[source]
    return values


def render_env(values: Mapping[str, str]) -> str:
    return "".join(f"{key}={values[key]}\n" for key in sorted(values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".env.cloud.test")
    parser.add_argument(
        "--worker-source",
        help="optional legacy local Worker env; control-plane values remain from --source",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--worker-services",
        default=",".join(f"worker-{slot}" for slot in DEFAULT_SLOTS),
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = Path(args.source)
        output = Path(args.output)
        slots = tuple(
            item.removeprefix("worker-").strip()
            for item in args.worker_services.split(",")
            if item.strip()
        )
        legacy, ignored = parse_legacy(source.read_text(encoding="utf-8").splitlines())
        worker_legacy = None
        if args.worker_source:
            worker_legacy, worker_ignored = parse_legacy(
                Path(args.worker_source).read_text(encoding="utf-8").splitlines()
            )
            ignored.extend(worker_ignored)
        migrated = migrate_values(legacy, slots, worker_legacy=worker_legacy)
        if not migrated.get("ALLBOT_WORKER_CENTRAL_API_URL", "").removeprefix(
            "http://"
        ).removesuffix(":8004"):
            raise MigrationError("CLOUD_TEST_CONTROL_HOST is required")
        if not args.execute:
            print(
                f"[dry-run] would write {len(migrated)} variables to {output}; "
                f"ignored malformed entries: {len(ignored)}"
            )
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.name + ".tmp")
        old_umask = os.umask(0o077)
        try:
            temp.write_text(render_env(migrated), encoding="utf-8")
            temp.chmod(0o600)
            temp.replace(output)
        finally:
            os.umask(old_umask)
        print(
            f"wrote {len(migrated)} variables to {output}; "
            f"ignored malformed entries: {len(ignored)}"
        )
        return 0
    except (OSError, MigrationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
