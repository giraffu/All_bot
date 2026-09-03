#!/usr/bin/env python3
"""Loopback-only, token-protected gateway for immutable NAS snapshot batches."""

from __future__ import annotations

import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import PurePosixPath
import re
import shlex
import subprocess
from urllib.parse import unquote, urlsplit


RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
REQUEST_PATTERN = re.compile(r"^/v1/batches/(\d{6})/objects/(.+)$")
REMOTE_STREAM_SCRIPT = r"""
import json, os, stat, sys
path, raw_start, raw_end = sys.argv[1:4]
try:
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise FileNotFoundError(path)
    size = metadata.st_size
    if raw_start.startswith('-'):
        suffix = int(raw_start[1:])
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(raw_start) if raw_start else 0
        end = int(raw_end) if raw_end else size - 1
    if size <= 0:
        start, end = 0, -1
    if start < 0 or end < start or start >= size:
        print(json.dumps({'status': 416, 'size': size}), flush=True)
        raise SystemExit(0)
    end = min(end, size - 1)
    print(json.dumps({'status': 200, 'size': size, 'start': start, 'end': end}), flush=True)
    remaining = end - start + 1
    with open(path, 'rb', buffering=0) as stream:
        stream.seek(start)
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            remaining -= len(chunk)
except (FileNotFoundError, PermissionError, OSError):
    print(json.dumps({'status': 404}), flush=True)
"""


def safe_remote_object_path(root: str, batch_number: int, object_key: str) -> str:
    root_path = PurePosixPath(root)
    key_path = PurePosixPath(object_key)
    if (
        root_path.is_absolute()
        or not root_path.parts
        or any(part in {"", ".", ".."} for part in root_path.parts)
        or key_path.is_absolute()
        or not key_path.parts
        or any(part in {"", ".", ".."} for part in object_key.split("/"))
        or batch_number < 1
    ):
        raise ValueError("unsafe snapshot object path")
    return (
        root_path / f"batch-{batch_number:06d}" / key_path
    ).as_posix()


def parse_byte_range(value: str | None, *, size: int) -> tuple[int, int]:
    if size < 1:
        if value:
            raise ValueError("range is invalid for an empty file")
        return 0, -1
    if not value:
        return 0, size - 1
    match = RANGE_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("invalid byte range")
    raw_start, raw_end = match.groups()
    if not raw_start and not raw_end:
        raise ValueError("invalid byte range")
    if not raw_start:
        suffix = int(raw_end)
        if suffix < 1:
            raise ValueError("invalid byte range")
        return max(0, size - suffix), size - 1
    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    if start >= size or end < start:
        raise ValueError("invalid byte range")
    return start, min(end, size - 1)


class SnapshotGatewayHandler(BaseHTTPRequestHandler):
    server_version = "AllBotSnapshotGateway/1"

    def do_GET(self) -> None:  # noqa: N802
        server = self.server
        token = self.headers.get("X-AllBot-Snapshot-Token", "")
        if not hmac.compare_digest(token, server.gateway_token):
            self.send_error(403)
            return
        match = REQUEST_PATTERN.fullmatch(urlsplit(self.path).path)
        if not match:
            self.send_error(404)
            return
        batch_number = int(match.group(1))
        object_key = unquote(match.group(2))
        try:
            remote_path = safe_remote_object_path(
                server.nas_batches_root, batch_number, object_key
            )
        except ValueError:
            self.send_error(400)
            return
        range_header = self.headers.get("Range")
        raw_start = raw_end = ""
        if range_header:
            range_match = RANGE_PATTERN.fullmatch(range_header)
            if not range_match or (not range_match.group(1) and not range_match.group(2)):
                self.send_error(416)
                return
            raw_start, raw_end = range_match.groups()
            # Suffix ranges need the remote size, so the remote helper receives a marker.
            if not raw_start:
                raw_start = f"-{raw_end}"
                raw_end = ""
        command = " ".join(
            [
                "python3",
                "-c",
                shlex.quote(REMOTE_STREAM_SCRIPT),
                shlex.quote(remote_path),
                shlex.quote(raw_start),
                shlex.quote(raw_end),
            ]
        )
        process = subprocess.Popen(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                server.nas_ssh_alias,
                command,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert process.stdout is not None
        try:
            raw_metadata = process.stdout.readline(4096)
            metadata = json.loads(raw_metadata)
            if metadata.get("status") == 404:
                self.send_error(404)
                return
            if metadata.get("status") == 416:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{metadata['size']}")
                self.end_headers()
                return
            size = int(metadata["size"])
            start = int(metadata["start"])
            end = int(metadata["end"])
            partial = bool(range_header)
            self.send_response(206 if partial else 200)
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            while chunk := process.stdout.read(1024 * 1024):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (json.JSONDecodeError, KeyError, OSError, ValueError):
            if not self.wfile.closed:
                self.send_error(502)
        finally:
            process.terminate()
            process.wait(timeout=5)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18099)
    parser.add_argument("--nas-ssh-alias", required=True)
    parser.add_argument("--nas-batches-root", required=True)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1"}:
        raise SystemExit("snapshot gateway must bind to loopback")
    token = os.getenv("SNAPSHOT_MEDIA_GATEWAY_TOKEN", "")
    if not token:
        session_secret = os.getenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", "")
        if session_secret:
            token = hashlib.sha256(
                f"allbot-snapshot-gateway:{session_secret}".encode()
            ).hexdigest()
    if len(token) < 32:
        raise SystemExit("SNAPSHOT_MEDIA_GATEWAY_TOKEN must contain at least 32 characters")
    server = ThreadingHTTPServer((args.host, args.port), SnapshotGatewayHandler)
    server.gateway_token = token
    server.nas_ssh_alias = args.nas_ssh_alias
    server.nas_batches_root = args.nas_batches_root
    server.serve_forever()


if __name__ == "__main__":
    main()
