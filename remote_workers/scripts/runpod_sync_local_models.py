#!/usr/bin/env python3
"""Download declared LAN-only model overrides with immutable verification."""
import argparse
import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


CHUNK_SIZE = 64 * 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash a model in bounded memory; models routinely exceed host RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()

def request_for(item):
    url = item["source_url"]
    token = os.environ.get(item.get("source_token_env", ""), "")
    if item.get("source_token_env") and not token:
        raise RuntimeError("missing source token for LAN local model override")
    if token and item.get("source_token_query_param"):
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query.append((item["source_token_query_param"], token))
        url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))
    return urllib.request.Request(url, headers={"User-Agent": "AllBotLanModelSync/1.0"})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", type=Path, required=True)
    args = parser.parse_args()
    for item in json.loads(
        os.environ.get("RUNPOD_LAN_LOCAL_MODEL_OVERRIDES", "[]")
    ):
        target = args.target_dir / item["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            target.exists()
            and target.stat().st_size == int(item["size_bytes"])
            and sha256_file(target) == item["sha256"]
        ):
            continue
        with (
            tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp,
            urllib.request.urlopen(request_for(item), timeout=120) as source,
        ):
            digest = hashlib.sha256()
            while chunk := source.read(CHUNK_SIZE):
                tmp.write(chunk)
                digest.update(chunk)
            name = tmp.name
        partial = Path(name)
        if (
            partial.stat().st_size != int(item["size_bytes"])
            or digest.hexdigest() != item["sha256"]
        ):
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"local model checksum mismatch: {item['relative_path']}")
        partial.replace(target)


if __name__ == "__main__":
    main()
