#!/usr/bin/env python3
"""Download one immutable large build dependency with validated HTTP ranges."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _ranges(size_bytes: int, parallelism: int) -> tuple[tuple[int, int], ...]:
    if size_bytes <= 0:
        raise ValueError("size_bytes must be positive")
    count = max(1, min(parallelism, size_bytes))
    chunk_size = (size_bytes + count - 1) // count
    return tuple(
        (start, min(size_bytes - 1, start + chunk_size - 1))
        for start in range(0, size_bytes, chunk_size)
    )


def _download_range(url: str, start: int, end: int, target: Path) -> None:
    expected_size = end - start + 1
    request = urllib.request.Request(
        url,
        headers={
            "Range": f"bytes={start}-{end}",
            "User-Agent": "allbot-pinned-build-dependency/1",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                if response.status != 206:
                    raise RuntimeError(
                        f"range request returned HTTP {response.status}, expected 206"
                    )
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {start}-{end}/"):
                    raise RuntimeError(f"unexpected Content-Range: {content_range}")
                with target.open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
            if target.stat().st_size != expected_size:
                raise RuntimeError(
                    f"range size mismatch: expected {expected_size}, "
                    f"got {target.stat().st_size}"
                )
            return
        except Exception as exc:  # pragma: no branch - retry boundary
            last_error = exc
            if target.exists():
                target.unlink()
            if attempt == 5:
                break
    raise RuntimeError(f"failed to download bytes {start}-{end}") from last_error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_pinned_file(
    *,
    url: str,
    output: Path,
    size_bytes: int,
    sha256: str,
    parallelism: int = 12,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.ranges-", dir=output.parent)
    )
    assembled = temp_root / "assembled"
    try:
        ranges = _ranges(size_bytes, parallelism)
        parts = tuple(temp_root / f"part-{index:03d}" for index in range(len(ranges)))
        with ThreadPoolExecutor(max_workers=len(ranges)) as executor:
            futures = [
                executor.submit(_download_range, url, start, end, target)
                for (start, end), target in zip(ranges, parts)
            ]
            for future in futures:
                future.result()
        with assembled.open("wb") as destination:
            for part in parts:
                with part.open("rb") as source:
                    shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)
        if assembled.stat().st_size != size_bytes:
            raise RuntimeError(
                f"size mismatch: expected {size_bytes}, got {assembled.stat().st_size}"
            )
        actual_sha256 = _sha256(assembled)
        if actual_sha256 != sha256.lower():
            raise RuntimeError(
                f"SHA256 mismatch: expected {sha256.lower()}, got {actual_sha256}"
            )
        os.replace(assembled, output)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--parallelism", type=int, default=12)
    args = parser.parse_args()
    download_pinned_file(
        url=args.url,
        output=args.output,
        size_bytes=args.size,
        sha256=args.sha256,
        parallelism=args.parallelism,
    )


if __name__ == "__main__":
    main()
