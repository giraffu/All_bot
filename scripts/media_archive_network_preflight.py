#!/usr/bin/env python3
"""Fail-closed archive route checks and small direct-download benchmarks."""

from __future__ import annotations

import argparse
import json
import subprocess
import time

from scripts.media_archive_worker import clear_proxy_environment, validate_direct_route


def benchmark(url: str, *, interface: str | None, max_bytes: int) -> dict:
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--connect-timeout",
        "10",
        "--max-time",
        "60",
        "--range",
        f"0-{max_bytes - 1}",
        "--output",
        "/dev/null",
        "--write-out",
        "%{size_download} %{time_total} %{remote_ip}",
    ]
    if interface:
        command.extend(["--interface", interface])
    command.append(url)
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    if result.returncode:
        return {"ok": False, "error": result.stderr.strip()[:300], "elapsed": elapsed}
    size, curl_elapsed, remote_ip = result.stdout.split(maxsplit=2)
    seconds = max(float(curl_elapsed), 0.001)
    return {
        "ok": True,
        "bytes": int(float(size)),
        "seconds": seconds,
        "mib_per_second": int(float(size)) / seconds / 1024**2,
        "remote_ip": remote_ip,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--interface")
    parser.add_argument("--max-bytes", type=int, default=8 * 1024**2)
    parser.add_argument("--route-host", action="append", default=[])
    args = parser.parse_args()
    clear_proxy_environment()
    for host in args.route_host:
        validate_direct_route(host)
    print(
        json.dumps(
            {
                url: benchmark(url, interface=args.interface, max_bytes=args.max_bytes)
                for url in args.url
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
