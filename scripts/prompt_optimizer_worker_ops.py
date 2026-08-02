#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose-prompt-optimizer-test.yml"
STATE = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state")) / "allbot/prompt-optimizer-test.json"
CONTAINER = "allbot-prompt-optimizer-test"


def _exact_image(value: str) -> str:
    if "@sha256:" not in value or len(value.rsplit("@sha256:", 1)[-1]) != 64:
        raise SystemExit("image must be pinned by an exact sha256 digest")
    return value


def _compose(image: str, env_file: str, *args: str) -> None:
    env = {
        **os.environ,
        "ALLBOT_PROMPT_OPTIMIZER_IMAGE": _exact_image(image),
        "ALLBOT_PROMPT_OPTIMIZER_ENV_FILE": env_file,
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
    STATE.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("deploy", "status", "rollback"))
    parser.add_argument("--image")
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    state = _read_state()
    if args.action == "status":
        subprocess.run(
            ["docker", "inspect", CONTAINER, "--format", "{{json .State}}"], check=True
        )
        return
    if args.action == "deploy":
        image = _exact_image(args.image or "")
        _compose(image, args.env_file, "pull", "prompt-optimizer-worker")
        _compose(image, args.env_file, "up", "-d", "prompt-optimizer-worker")
        _write_state({"current": image, "previous": state.get("current")})
        return
    previous = state.get("previous")
    if not previous:
        raise SystemExit("no previous exact image is recorded")
    _compose(previous, args.env_file, "up", "-d", "prompt-optimizer-worker")
    _write_state({"current": previous, "previous": state.get("current")})


if __name__ == "__main__":
    main()
