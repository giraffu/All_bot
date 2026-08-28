#!/usr/bin/env python3
"""Validate the local company-operations vault without exposing its contents."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Sequence


REQUIRED_FILES = (
    "credentials.json",
    "hardware-secrets.json",
    "identity.json",
    "operations.json",
)
REQUIRED_DIRECTORIES = ("evidence", "ledger")


def default_root() -> Path:
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    )
    return config_home / "allbot" / "company-operations"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _is_owned_by_current_user(path: Path) -> bool:
    return path.lstat().st_uid == os.geteuid()


def _validate_json_file(root: Path, name: str, issues: list[str]) -> str:
    path = root / name
    if path.is_symlink():
        issues.append(f"{name} must be a regular file, not a symlink")
        return "invalid"
    if not path.is_file():
        issues.append(f"missing required file: {name}")
        return "missing"
    if not _is_owned_by_current_user(path):
        issues.append(f"{name} must be owned by the current user")
        return "invalid"
    if _mode(path) != 0o600:
        issues.append(f"{name} must have mode 0600")
        return "invalid"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        issues.append(f"{name} must contain a valid JSON object")
        return "invalid"
    if not isinstance(payload, dict):
        issues.append(f"{name} must contain a valid JSON object")
        return "invalid"
    return "present"


def _validate_nested_entries(root: Path, issues: list[str]) -> None:
    for directory_name in REQUIRED_DIRECTORIES:
        directory = root / directory_name
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                issues.append(f"{relative} must not be a symlink")
            elif path.is_dir():
                if not _is_owned_by_current_user(path):
                    issues.append(f"{relative}/ must be owned by the current user")
                if _mode(path) != 0o700:
                    issues.append(f"{relative}/ must have mode 0700")
            elif path.is_file():
                if not _is_owned_by_current_user(path):
                    issues.append(f"{relative} must be owned by the current user")
                if _mode(path) != 0o600:
                    issues.append(f"{relative} must have mode 0600")
            else:
                issues.append(f"{relative} must be a regular file or directory")


def check(root: Path) -> tuple[dict[str, object], int]:
    issues: list[str] = []
    files: dict[str, str] = {}

    if root.is_symlink():
        issues.append("vault root must be a directory, not a symlink")
    elif not root.is_dir():
        issues.append("vault root is missing")
    else:
        if not _is_owned_by_current_user(root):
            issues.append("vault root must be owned by the current user")
        if _mode(root) != 0o700:
            issues.append("vault root must have mode 0700")

    if root.is_dir() and not root.is_symlink():
        for name in REQUIRED_FILES:
            files[name] = _validate_json_file(root, name, issues)
        for name in REQUIRED_DIRECTORIES:
            path = root / name
            if path.is_symlink() or not path.is_dir():
                issues.append(f"{name}/ must be a real directory")
            else:
                if not _is_owned_by_current_user(path):
                    issues.append(f"{name}/ must be owned by the current user")
                if _mode(path) != 0o700:
                    issues.append(f"{name}/ must have mode 0700")
        _validate_nested_entries(root, issues)

    payload: dict[str, object] = {
        "root": str(root),
        "status": "error" if issues else "ok",
        "files": files,
    }
    if issues:
        payload["issues"] = issues
    return payload, 1 if issues else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the local company-operations vault without printing values."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--root", type=Path, default=default_root())
    check_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "check":
        raise AssertionError("unreachable")
    payload, returncode = check(args.root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"company operations vault: {payload['status']}")
        for issue in payload.get("issues", []):
            print(f"- {issue}")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
