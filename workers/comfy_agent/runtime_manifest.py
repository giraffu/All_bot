from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


_IGNORED_SUFFIXES = {".pyc", ".pyo"}


def hash_runtime_package(package_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*")):
        if not path.is_file() or path.suffix in _IGNORED_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        relative_path = path.relative_to(package_root).as_posix().encode("utf-8")
        digest.update(len(relative_path).to_bytes(8, "big"))
        digest.update(relative_path)
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def build_runtime_manifest(package_root: Path, *, git_sha: str) -> dict[str, str]:
    package_root = package_root.resolve()
    mapping_path = package_root / "workflows" / "mappings.json"
    if not mapping_path.is_file():
        raise FileNotFoundError(f"workflow mapping not found: {mapping_path}")
    return {
        "git_sha": str(git_sha).strip(),
        "runtime_package_sha256": hash_runtime_package(package_root),
        "workflow_mapping_sha256": hashlib.sha256(
            mapping_path.read_bytes()
        ).hexdigest(),
    }


def load_runtime_manifest() -> dict[str, Any]:
    manifest = build_runtime_manifest(
        Path(__file__).resolve().parent,
        git_sha=os.getenv("ALLBOT_GIT_SHA", "").strip(),
    )
    expected_fields = {
        "runtime_package_sha256": os.getenv(
            "ALLBOT_RUNTIME_PACKAGE_SHA256", ""
        ).strip(),
        "workflow_mapping_sha256": os.getenv(
            "ALLBOT_WORKFLOW_MAPPING_SHA256", ""
        ).strip(),
    }
    for field, expected in expected_fields.items():
        if expected and manifest[field] != expected:
            raise RuntimeError(
                f"worker runtime manifest mismatch for {field}: "
                f"expected {expected}, got {manifest[field]}"
            )
    return manifest
