from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_PREFIX = "docs/archive/"
RELEASE_BATCH_PREFIX = "deploy/release-batches/"
THIS_FILE = Path(__file__).resolve()

RETIRED_MARKERS = (
    re.compile(r"\bweb-" + r"test\b", re.IGNORECASE),
    re.compile(r"\bWEB" + r"VPS\b", re.IGNORECASE),
    re.compile(re.escape("assets" + ".aivison.it.com"), re.IGNORECASE),
    re.compile(re.escape("154.17" + ".30.113")),
    re.compile(re.escape("100.88" + ".57.122")),
    re.compile(r"\bLEGACY_" + r"MINIO_", re.IGNORECASE),
)

RETIRED_FILES = (
    "all_bot_nginx.conf",
    "all_bot_nginx_cloud_prod.conf",
    "all_bot_nginx_web_test.conf",
    "frontend/.env.edge-test",
    "frontend/scripts/deploy-edge-prod.sh",
    "frontend/scripts/deploy-edge-test.sh",
    "safe_deploy_test.sh",
)


def _tracked_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw_path in result.stdout.decode().split("\0"):
        if (
            not raw_path
            or raw_path.startswith(ARCHIVE_PREFIX)
            or raw_path.startswith(RELEASE_BATCH_PREFIX)
        ):
            continue
        path = ROOT / raw_path
        if path == THIS_FILE or not path.is_file():
            continue
        paths.append(path)
    return paths


def test_retired_web_vps_entrypoints_are_deleted() -> None:
    remaining = [relative for relative in RETIRED_FILES if (ROOT / relative).exists()]
    assert remaining == []


def test_active_repository_has_no_retired_web_vps_contracts() -> None:
    matches: list[str] = []
    for path in _tracked_text_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in RETIRED_MARKERS:
            if marker.search(content):
                matches.append(f"{path.relative_to(ROOT)}: {marker.pattern}")
    assert matches == []
