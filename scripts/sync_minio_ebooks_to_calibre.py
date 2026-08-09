#!/usr/bin/env python3
"""Materialize verified MinIO TXT ebooks as EPUB files for Calibre-Web Automated."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import io
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import tempfile
import time
import zipfile

import boto3
from botocore.config import Config as BotoConfig


def _chunks(text: str, limit: int) -> list[str]:
    if limit < 1:
        raise ValueError("chunk_chars must be positive")
    result = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            result.append(remaining)
            break
        boundary = remaining.rfind("\n", 0, limit)
        if boundary < limit // 2:
            boundary = limit
        result.append(remaining[:boundary])
        remaining = remaining[boundary:].lstrip("\n")
    return result or [""]


def build_epub(
    *,
    book_id: str,
    title: str,
    author: str,
    text: str,
    source_sha256: str,
    chunk_chars: int = 250_000,
) -> bytes:
    if not re.fullmatch(r"\d+", book_id):
        raise ValueError("book_id must be numeric")
    pages = _chunks(text, chunk_chars)
    identifier = f"urn:allbot:diyibanzhu:{book_id}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    ]
    spine = []
    nav = []
    page_files = {}
    for index, page in enumerate(pages, start=1):
        name = f"text-{index}.xhtml"
        manifest.append(f'<item id="text-{index}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="text-{index}"/>')
        nav.append(f'<li><a href="{name}">第 {index} 部分</a></li>')
        heading = escape(title) if index == 1 else f"{escape(title)}（续 {index}）"
        page_files[f"OEBPS/{name}"] = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN"><head>'
            f"<title>{heading}</title>"
            '<style>body{line-height:1.75;margin:5%;}pre{font-family:serif;white-space:pre-wrap;word-wrap:break-word;}</style>'
            f"</head><body><h1>{heading}</h1><pre>{escape(page)}</pre></body></html>"
        ).encode("utf-8")
    package = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="book-id">{identifier}</dc:identifier>'
        f"<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator>"
        '<dc:language>zh-CN</dc:language>'
        f'<meta property="dcterms:modified">{modified}</meta>'
        f'<meta property="allbot:source-sha256">{source_sha256}</meta>'
        f"</metadata><manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>"
    ).encode("utf-8")
    nav_doc = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN">'
        f'<head><title>{escape(title)}</title></head><body><nav epub:type="toc"><h1>目录</h1><ol>{"".join(nav)}</ol></nav></body></html>'
    ).encode("utf-8")
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    ).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/package.opf", package, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav_doc, compress_type=zipfile.ZIP_DEFLATED)
        for name, payload in page_files.items():
            archive.writestr(name, payload, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def discover_ready_books(keys: list[str], prefix: str) -> list[str]:
    prefix = prefix.strip("/")
    pattern = re.compile(rf"^{re.escape(prefix)}/(\d+)\.(txt|json)$")
    formats: dict[str, set[str]] = {}
    for key in keys:
        match = pattern.fullmatch(key)
        if match:
            formats.setdefault(match.group(1), set()).add(match.group(2))
    return sorted((book_id for book_id, kinds in formats.items() if kinds == {"txt", "json"}), key=int)


def _read_object(client, bucket: str, key: str) -> bytes:
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def _init_state(connection: sqlite3.Connection) -> None:
    connection.execute(
        "create table if not exists calibre_ebook_sync "
        "(book_id text primary key, source_sha256 text not null, epub_sha256 text not null, published_at text not null)"
    )


def sync_once(*, client, bucket: str, prefix: str, book_ids: list[str], state: sqlite3.Connection, publish) -> dict:
    _init_state(state)
    published = skipped = failed = 0
    for book_id in book_ids:
        try:
            txt = _read_object(client, bucket, f"{prefix}/{book_id}.txt")
            metadata = json.loads(_read_object(client, bucket, f"{prefix}/{book_id}.json"))
            digest = hashlib.sha256(txt).hexdigest()
            if metadata.get("book_id") != book_id or metadata.get("sha256") != digest:
                raise ValueError("TXT and JSON identity or SHA-256 mismatch")
            existing = state.execute(
                "select source_sha256 from calibre_ebook_sync where book_id = ?", (book_id,)
            ).fetchone()
            if existing and existing[0] == digest:
                skipped += 1
                continue
            epub = build_epub(
                book_id=book_id,
                title=str(metadata.get("title") or book_id),
                author=str(metadata.get("author") or "未知作者"),
                text=txt.decode("utf-8"),
                source_sha256=digest,
            )
            publish(book_id, epub)
            state.execute(
                "insert into calibre_ebook_sync values (?, ?, ?, datetime('now')) "
                "on conflict(book_id) do update set source_sha256=excluded.source_sha256, "
                "epub_sha256=excluded.epub_sha256, published_at=excluded.published_at",
                (book_id, digest, hashlib.sha256(epub).hexdigest()),
            )
            state.commit()
            published += 1
        except Exception as exc:
            failed += 1
            print(json.dumps({"book_id": book_id, "status": "failed", "error": str(exc)}, ensure_ascii=False), flush=True)
    return {"published": published, "skipped": skipped, "failed": failed}


def _list_keys(client, bucket: str, prefix: str) -> list[str]:
    keys = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix.rstrip("/") + "/"}
        if token:
            kwargs["ContinuationToken"] = token
        response = client.list_objects_v2(**kwargs)
        keys.extend(item["Key"] for item in response.get("Contents", ()))
        if not response.get("IsTruncated"):
            return keys
        token = response["NextContinuationToken"]


def _publisher(ssh_alias: str, source_dir: str, ingest_dir: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ssh_alias):
        raise ValueError("invalid SSH alias")
    for path in (source_dir, ingest_dir):
        if not path.startswith("/volume1/AllBotEbooks/"):
            raise ValueError("Calibre paths must stay below /volume1/AllBotEbooks")

    def publish(book_id: str, payload: bytes) -> None:
        with tempfile.NamedTemporaryFile(suffix=".epub") as local:
            local.write(payload)
            local.flush()
            remote_part = f"{source_dir}/.{book_id}.epub.part"
            subprocess.run(["scp", "-q", local.name, f"{ssh_alias}:{remote_part}"], check=True)
            command = (
                f"mv -f {shlex.quote(remote_part)} {shlex.quote(source_dir + '/' + book_id + '.epub')} && "
                f"cp {shlex.quote(source_dir + '/' + book_id + '.epub')} {shlex.quote(ingest_dir + '/.' + book_id + '.epub.part')} && "
                f"mv -f {shlex.quote(ingest_dir + '/.' + book_id + '.epub.part')} {shlex.quote(ingest_dir + '/' + book_id + '.epub')}"
            )
            subprocess.run(["ssh", "-o", "BatchMode=yes", ssh_alias, command], check=True)

    return publish


def _resolve_env(value):
    if isinstance(value, dict):
        return {key: _resolve_env(item) for key, item in value.items()}
    if isinstance(value, str) and value.startswith("env:"):
        resolved = os.getenv(value[4:])
        if not resolved:
            raise ValueError(f"required environment value is missing: {value[4:]}")
        return resolved
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--ssh-alias", default="allbot-nas-archive")
    parser.add_argument("--source-dir", default="/volume1/AllBotEbooks/source-epub")
    parser.add_argument("--ingest-dir", default="/volume1/AllBotEbooks/ingest")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    if args.config.stat().st_mode & 0o077:
        raise SystemExit("config must be private (chmod 600)")
    config = _resolve_env(json.loads(args.config.read_text(encoding="utf-8")))
    nas = config["nas"]
    from scripts.media_archive_worker import clear_proxy_environment, validate_endpoint_route

    clear_proxy_environment()
    validate_endpoint_route(nas)
    client = boto3.client(
        "s3",
        endpoint_url=nas["endpoint"],
        aws_access_key_id=nas["access_key"],
        aws_secret_access_key=nas["secret_key"],
        verify=nas.get("ca_file") or nas.get("ca_bundle") or True,
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
    )
    args.state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = sqlite3.connect(args.state)
    publish = _publisher(args.ssh_alias, args.source_dir, args.ingest_dir)
    while True:
        keys = _list_keys(client, nas["bucket"], "ebooks/diyibanzhu")
        result = sync_once(
            client=client,
            bucket=nas["bucket"],
            prefix="ebooks/diyibanzhu",
            book_ids=discover_ready_books(keys, "ebooks/diyibanzhu"),
            state=state,
            publish=publish,
        )
        print(json.dumps({"status": "scan_complete", **result}, ensure_ascii=False), flush=True)
        if not args.watch:
            return
        time.sleep(max(args.poll_seconds, 10))


if __name__ == "__main__":
    main()
