#!/usr/bin/env python3
"""Publish an already verified release approval through a packages:write identity."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Sequence

try:
    from scripts.release_promotion_v2 import (
        PromotionError,
        validate_candidate_approval,
    )
except ModuleNotFoundError:
    from release_promotion_v2 import (  # type: ignore[no-redef]
        PromotionError,
        validate_candidate_approval,
    )


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ApprovalPublishError(RuntimeError):
    """An approval cannot be safely published."""


def publish_existing_approval(
    *,
    source_sha: str,
    candidate_index_path: Path,
    candidate_bundle_digest: str,
    approval_path: Path,
    publish_ref: str,
) -> str:
    if not FULL_SHA_RE.fullmatch(source_sha):
        raise ApprovalPublishError("source_sha must be a full lowercase Git SHA")
    if not publish_ref.endswith(f":{source_sha}"):
        raise ApprovalPublishError("publish ref must use the exact candidate SHA")
    try:
        validate_candidate_approval(
            candidate_index_path=candidate_index_path,
            approval_path=approval_path,
            candidate_sha=source_sha,
            candidate_bundle_digest=candidate_bundle_digest,
        )
    except PromotionError as exc:
        raise ApprovalPublishError(str(exc)) from exc
    existing = subprocess.run(
        ["oras", "manifest", "fetch", "--descriptor", publish_ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if existing.returncode == 0:
        with tempfile.TemporaryDirectory(prefix="allbot-approval-") as temp:
            pulled = subprocess.run(
                ["oras", "pull", publish_ref, "-o", temp],
                text=True,
                capture_output=True,
                check=False,
            )
            remote_files = list(Path(temp).rglob("*.json"))
            if pulled.returncode != 0 or len(remote_files) != 1:
                raise ApprovalPublishError("existing promotion approval cannot be verified")
            if remote_files[0].read_bytes() != approval_path.read_bytes():
                raise ApprovalPublishError(
                    "promotion approval tag already contains different bytes"
                )
        return "no-change"
    subprocess.run(
        [
            "oras",
            "push",
            publish_ref,
            f"{approval_path.name}:application/vnd.allbot.release-approval.v1+json",
        ],
        cwd=approval_path.parent,
        check=True,
    )
    return "published"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--candidate-index", type=Path, required=True)
    parser.add_argument("--candidate-bundle-digest", required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--publish-ref", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = publish_existing_approval(
            source_sha=args.source_sha,
            candidate_index_path=args.candidate_index,
            candidate_bundle_digest=args.candidate_bundle_digest,
            approval_path=args.approval,
            publish_ref=args.publish_ref,
        )
    except (ApprovalPublishError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
