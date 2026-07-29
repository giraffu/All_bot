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
from urllib.parse import urlsplit, urlunsplit


VALID_KEY = re.compile(r"^[A-Z_][A-Z0-9_]*$")
DEFAULT_SLOTS = ("01", "02", "03", "04", "06", "07", "08")
SLOT_DEFAULTS: dict[str, dict[str, str]] = {
    "01": {
        "NODE_ID": "gpu-252",
        "GPU_INDEX": "1",
        "RUNTIME_PROFILE": "i2i_pro",
        "TASK_TYPES": "face_swap_v2,i2i_pro,i2i_draw,t2i-pornmaster-turbo",
        "COMFY_API_URL": "http://192.168.1.252:8191",
        "COMFY_WS_URL": "ws://192.168.1.252:8191/ws",
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
        "RUNTIME_PROFILE": "ltx_unified",
        "TASK_TYPES": (
            "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio,"
            "ltx_t2v,ltx_t2v_ic"
        ),
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
        "NODE_ID": "gpu-226",
        "GPU_INDEX": "0",
        "RUNTIME_PROFILE": "all",
        "TASK_TYPES": (
            "img2img,img2img_lora,image_to_video,wan22_video_v2,"
            "pornmaster_flux2_edit_bf16,pornmaster_flux2_multi_edit_bf16,"
            "scail2_action_transfer,scail2_action_transfer_long,"
            "scail2_video_replacement,scail2_face_swap_v2,"
            "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio,"
            "i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap,"
            "ltx_t2v,ltx_t2v_ic"
        ),
        "COMFY_API_URL": "http://192.168.1.226:8190",
        "COMFY_WS_URL": "ws://192.168.1.226:8190/ws",
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

STALE_SLOT_01_ASSIGNMENT = {
    "NODE_ID": "gpu-252",
    "GPU_INDEX": "0",
    "COMFY_API_URL": "http://192.168.1.252:8192",
    "COMFY_WS_URL": "ws://192.168.1.252:8192/ws",
}
LEGACY_CANONICAL_KEYS = {
    "AFFILIATE_MEMBERSHIP_REDEEM_ENABLED": (
        "AFFILIATE_MEMBERSHIP_REDEEM_ENABLED_TEST",
    ),
    "API_TOKEN": ("API_TOKEN_TEST",),
    "BOT_TOKEN": ("BOT_TOKEN_TEST",),
    "DATABASE_URL": ("DATABASE_URL_TEST", "CLOUD_TEST_DATABASE_URL"),
    "MEMBERSHIP_SETTLEMENT_V2_ENABLED": (
        "MEMBERSHIP_SETTLEMENT_V2_ENABLED_TEST",
    ),
    "MINI_APP_URL": ("MINI_APP_URL_TEST",),
    "MINI_APP_VERSION": ("MINI_APP_VERSION_TEST",),
    "ORDER_V2_ENABLED": ("ORDER_V2_ENABLED_TEST",),
    "QQCC_BOT_TOKEN": ("QQCC_BOT_TOKEN_TEST",),
    "REDIS_URL": ("REDIS_URL_TEST", "CLOUD_TEST_REDIS_URL"),
    "VITE_MERCHANT_ADDRESS": ("VITE_MERCHANT_ADDRESS_TEST",),
    "WORKER_REDIS_URL": ("CLOUD_TEST_WORKER_REDIS_URL",),
}


class MigrationError(RuntimeError):
    pass


def _canonicalize_legacy_keys(values: dict[str, str]) -> None:
    for canonical, aliases in LEGACY_CANONICAL_KEYS.items():
        if values.get(canonical, "").strip():
            continue
        for alias in aliases:
            if values.get(alias, "").strip():
                values[canonical] = values[alias]
                break


def _telegram_file_base_url(values: Mapping[str, str]) -> str:
    existing = values.get("TELEGRAM_FILE_BASE_URL", "").strip()
    if existing:
        return existing
    api_base = values.get("TELEGRAM_API_BASE_URL", "").strip()
    if not api_base:
        return ""
    try:
        parsed = urlsplit(api_base)
        port = parsed.port
    except ValueError as exc:
        raise MigrationError(
            "TELEGRAM_FILE_BASE_URL is required for an invalid Telegram API endpoint"
        ) from exc
    if (
        parsed.scheme == "https"
        and parsed.hostname == "api.telegram.org"
        and port is None
        and parsed.path.rstrip("/") == ""
        and not parsed.query
        and not parsed.fragment
    ):
        return "https://api.telegram.org/file/bot"
    if (
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and port == 8081
        and parsed.username is None
        and parsed.password is None
        and parsed.path.rstrip("/") == ""
        and not parsed.query
        and not parsed.fragment
    ):
        hostname = (
            f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        )
        return urlunsplit((parsed.scheme, f"{hostname}:8082", "", "", ""))
    raise MigrationError(
        "TELEGRAM_FILE_BASE_URL is required for an unrecognized Telegram API endpoint"
    )


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


def _slot_values(values: Mapping[str, str], slot: str) -> dict[str, str]:
    resolved = {
        suffix: _legacy(values, slot, suffix)
        for suffix in SLOT_DEFAULTS[slot]
    }
    if slot == "01" and all(
        resolved.get(suffix) == expected
        for suffix, expected in STALE_SLOT_01_ASSIGNMENT.items()
    ):
        for suffix in STALE_SLOT_01_ASSIGNMENT:
            resolved[suffix] = SLOT_DEFAULTS[slot][suffix]
    return resolved


def migrate_values(
    legacy: Mapping[str, str],
    slots: Sequence[str] = DEFAULT_SLOTS,
    *,
    worker_legacy: Mapping[str, str] | None = None,
    normalize_workers: bool = True,
) -> dict[str, str]:
    unknown = sorted(set(slots) - set(SLOT_DEFAULTS))
    if unknown:
        raise MigrationError("unsupported worker slots: " + ", ".join(unknown))
    worker_values = worker_legacy or legacy
    values = dict(legacy)
    _canonicalize_legacy_keys(values)
    values.update(
        {
            "ALLBOT_ENV": "test",
            "ALLBOT_ENV_FILE": "/etc/allbot/test.env",
            "ALLBOT_STATE_ROOT": "/var/lib/allbot/test",
            "QQCC_CONFIG_ADMIN_HOST": legacy.get(
                "QQCC_CONFIG_ADMIN_HOST", "qqcc-admin-test.aivison.it.com"
            ),
            "PRIVATE_QQCC_BOT_OWNER_HOST": legacy.get(
                "PRIVATE_QQCC_BOT_OWNER_HOST", "private-bot-test.aivison.it.com"
            ),
        }
    )
    telegram_file_base = _telegram_file_base_url(values)
    if telegram_file_base:
        values["TELEGRAM_FILE_BASE_URL"] = telegram_file_base
    if not normalize_workers:
        return values
    values.update(
        {
            "ALLBOT_WORKER_SERVICES": ",".join(f"worker-{slot}" for slot in slots),
            "ALLBOT_WORKER_STATE_ROOT": "/var/lib/allbot/test-worker",
            "ALLBOT_WORKER_CENTRAL_API_URL": (
                f"http://{legacy.get('CLOUD_TEST_CONTROL_HOST', '')}:8004"
            ),
            "ALLBOT_WORKER_RELAY_PORT": legacy.get(
                "CLOUD_TEST_LOCAL_RELAY_PORT",
                worker_values.get("CLOUD_TEST_LOCAL_RELAY_PORT", "8014"),
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
        slot_values = _slot_values(worker_values, slot)
        values.update(
            {
                prefix + "AGENT_ID": f"cloud_worker_test_{slot}",
                prefix + "COMFY_API_URL": slot_values["COMFY_API_URL"],
                prefix + "COMFY_WS_URL": slot_values["COMFY_WS_URL"],
                prefix + "TASK_TYPES": _normalized_task_types(
                    slot, slot_values["TASK_TYPES"]
                ),
                prefix + "NODE_ID": slot_values["NODE_ID"],
                prefix + "GPU_INDEX": slot_values["GPU_INDEX"],
                prefix + "RUNTIME_PROFILE": slot_values["RUNTIME_PROFILE"],
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
    parser.add_argument(
        "--control-plane-only",
        action="store_true",
        help="canonicalize control-plane keys without changing Worker selection or slots",
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
        if args.control_plane_only and args.worker_source:
            raise MigrationError(
                "--worker-source cannot be used with --control-plane-only"
            )
        legacy, ignored = parse_legacy(source.read_text(encoding="utf-8").splitlines())
        worker_legacy = None
        if args.worker_source:
            worker_legacy, worker_ignored = parse_legacy(
                Path(args.worker_source).read_text(encoding="utf-8").splitlines()
            )
            ignored.extend(worker_ignored)
        migrated = migrate_values(
            legacy,
            slots,
            worker_legacy=worker_legacy,
            normalize_workers=not args.control_plane_only,
        )
        if not args.control_plane_only and not migrated.get(
            "ALLBOT_WORKER_CENTRAL_API_URL", ""
        ).removeprefix("http://").removesuffix(":8004"):
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
