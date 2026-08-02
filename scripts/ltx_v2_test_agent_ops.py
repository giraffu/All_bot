#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose-ltx-v2-test-agent.yml"
STATE = (
    Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state"))
    / "allbot/ltx-v2-test-agent.json"
)
SERVICE = "ltx-v2-test-agent"
CONTAINER = "cloud-comfy-agent-test-ltx-v2-01"
EXACT_IMAGE = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")


def _exact_image(value: str) -> str:
    if not EXACT_IMAGE.fullmatch(value):
        raise SystemExit("image must be pinned by an exact sha256 digest")
    return value


def _compose(image: str, env_file: str, state_root: str, *args: str) -> None:
    env = {
        **os.environ,
        "ALLBOT_LTX_V2_TEST_AGENT_IMAGE": _exact_image(image),
        "ALLBOT_LTX_V2_TEST_AGENT_ENV_FILE": str(Path(env_file).resolve()),
        "ALLBOT_LTX_V2_TEST_AGENT_STATE_ROOT": str(Path(state_root).resolve()),
    }
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), *args],
        cwd=ROOT,
        env=env,
        check=True,
    )


def _read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def _write_state(payload: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(STATE)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("deploy", "status", "rollback"))
    parser.add_argument("--image")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--state-root", default="/var/lib/allbot/test-worker")
    args = parser.parse_args()
    state = _read_state()

    if args.action == "status":
        subprocess.run(
            ["docker", "inspect", CONTAINER, "--format", "{{json .State}}"],
            check=True,
        )
        return

    if args.action == "deploy":
        image = _exact_image(args.image or "")
        _compose(image, args.env_file, args.state_root, "pull", SERVICE)
        _compose(image, args.env_file, args.state_root, "up", "-d", SERVICE)
        _write_state(
            {
                "current": image,
                "previous": state.get("current"),
                "env_file": str(Path(args.env_file).resolve()),
                "state_root": str(Path(args.state_root).resolve()),
            }
        )
        return

    previous = state.get("previous")
    if not previous:
        raise SystemExit("no previous exact image is recorded")
    _compose(previous, args.env_file, args.state_root, "up", "-d", SERVICE)
    _write_state(
        {
            "current": previous,
            "previous": state.get("current"),
            "env_file": str(Path(args.env_file).resolve()),
            "state_root": str(Path(args.state_root).resolve()),
        }
    )


if __name__ == "__main__":
    main()
