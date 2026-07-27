#!/usr/bin/env python3
"""Plan and atomically apply test release configuration from current main."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class TestConfigSyncError(RuntimeError):
    pass


def _run(args: Sequence[str], *, cwd: Path) -> str:
    inherited = os.environ.get("PYTHONPATH", "")
    env = {
        **os.environ,
        "PYTHONPATH": (
            str(cwd)
            if not inherited
            else str(cwd) + os.pathsep + inherited
        ),
    }
    result = subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise TestConfigSyncError(
            detail[-1] if detail else "test config sync command failed"
        )
    return result.stdout.strip()


def _last_json(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if not output[index + end :].strip() and isinstance(value, dict):
            return value
    raise TestConfigSyncError("test config sync returned invalid JSON")


def sync_test_config(
    repo: Path,
    source_sha: str,
    *,
    execute: bool,
) -> dict[str, Any]:
    _run(["git", "fetch", "--prune", "origin", "main"], cwd=repo)
    if _run(["git", "rev-parse", "origin/main"], cwd=repo) != source_sha:
        raise TestConfigSyncError("source SHA is not current main")
    temp_root = Path(tempfile.mkdtemp(prefix="allbot-test-config-"))
    checkout = temp_root / "checkout"
    added = False
    try:
        _run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(checkout),
                source_sha,
            ],
            cwd=repo,
        )
        added = True
        release = str(checkout / "scripts/release.py")
        plan = _last_json(
            _run(
                ["python", release, "config-plan", "--env", "test"],
                cwd=checkout,
            )
        )
        if not execute:
            return {
                "status": "planned",
                "source_sha": source_sha,
                "plan": plan,
                "environment": "test",
                "production_changed": False,
            }
        applied = _last_json(
            _run(
                [
                    "python",
                    release,
                    "config-apply",
                    "--env",
                    "test",
                    "--execute",
                ],
                cwd=checkout,
            )
        )
        return {
            "status": "applied",
            "source_sha": source_sha,
            "plan": plan,
            "result": applied,
            "environment": "test",
            "production_changed": False,
        }
    finally:
        if added:
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "remove",
                    "--force",
                    str(checkout),
                ],
                cwd=repo,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        shutil.rmtree(temp_root, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not SHA_RE.fullmatch(args.source_sha):
        parser.error("--source-sha must be a full lowercase Git SHA")
    try:
        result = sync_test_config(
            args.repo.resolve(), args.source_sha, execute=args.execute
        )
    except TestConfigSyncError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
