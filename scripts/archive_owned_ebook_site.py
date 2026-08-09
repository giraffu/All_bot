#!/usr/bin/env python3
"""Archive an owned diyibanzhu-compatible ebook site into private NAS MinIO.

The command is read-only unless ``--execute`` is supplied. Runtime credentials live
in a 0600 JSON config and may be expressed as ``env:VARIABLE_NAME`` values.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html import unescape
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import urljoin, urlparse

import boto3
from botocore.config import Config as BotoConfig
import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_CATALOG_PAGE_RE = re.compile(r'href=["\'](/book/\d+_(\d+)\.html)["\']', re.I)
_BOOK_RE = re.compile(r'href=["\'](/list/(\d+)\.html)["\']', re.I)
_BOOK_PAGE_RE = re.compile(r'href=["\'](/list/(\d+)_(\d+)\.html)["\']', re.I)
_CHAPTER_RE = re.compile(r'href=["\'](/view/(?:\d+|\d+_\w+)\.html)["\']', re.I)


@dataclass(frozen=True)
class Book:
    book_id: str
    source_path: str
    title: str
    author: str
    intro: str
    chapter_paths: tuple[str, ...]


@dataclass(frozen=True)
class Chapter:
    source_path: str
    title: str
    text: str


def _clean_fragment(fragment: str) -> str:
    fragment = re.sub(r"<\s*br\s*/?\s*>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"</?p(?:\s[^>]*)?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    text = unescape(fragment).replace("\r", "")
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _first_group(pattern: str, html: str, default: str = "") -> str:
    match = re.search(pattern, html, re.I | re.S)
    return _clean_fragment(match.group(1)) if match else default


def discover_catalog_pages(html: str) -> list[str]:
    last_page = max((int(match.group(2)) for match in _CATALOG_PAGE_RE.finditer(html)), default=1)
    prefix_match = _CATALOG_PAGE_RE.search(html)
    if last_page == 1 or not prefix_match:
        return ["/book/index.html"]
    prefix = prefix_match.group(1).rsplit("_", 1)[0]
    return ["/book/index.html", *[f"{prefix}_{page}.html" for page in range(2, last_page + 1)]]


def parse_catalog_books(html: str) -> list[str]:
    return list(dict.fromkeys(match.group(1) for match in _BOOK_RE.finditer(html)))


def discover_book_pages(book_id: str, html: str) -> list[str]:
    last_page = max(
        (int(match.group(3)) for match in _BOOK_PAGE_RE.finditer(html) if match.group(2) == book_id),
        default=1,
    )
    return [f"/list/{book_id}.html", *[f"/list/{book_id}_{page}.html" for page in range(2, last_page + 1)]]


def parse_book_page(source_path: str, html: str) -> Book:
    book_id_match = re.search(r"/list/(\d+)", source_path)
    if not book_id_match:
        raise ValueError(f"invalid book path: {source_path}")
    title = _first_group(r"<h1\b[^>]*>(.*?)</h1>", html)
    if not title:
        title = _first_group(r"<title>(.*?)</title>", html).split("_")[0].strip()
    author = _first_group(r'<a\b[^>]*class=["\'][^"\']*author[^"\']*["\'][^>]*>(.*?)</a>', html)
    if not author:
        author = _first_group(r"作者\s*[：:]\s*([^<\r\n]+)", html, "未知作者")
    intro = _first_group(
        r'class=["\'][^"\']*book-intro[^"\']*["\'][^>]*>.*?class=["\'][^"\']*bd[^"\']*["\'][^>]*>(.*?)</div>',
        html,
    )
    chapter_sections = re.findall(
        r'<div\b[^>]*class=["\'][^"\']*chapter-list[^"\']*["\'][^>]*>(.*?)(?=<div\b[^>]*class=["\'][^"\']*(?:mod\b|tuijian\b)|</body>|\Z)',
        html,
        re.I | re.S,
    )
    chapter_paths = tuple(
        dict.fromkeys(match.group(1) for section in chapter_sections for match in _CHAPTER_RE.finditer(section))
    )
    return Book(book_id_match.group(1), source_path, title, author, intro, chapter_paths)


def parse_chapter(source_path: str, html: str) -> Chapter:
    title = _first_group(r'<h1\b[^>]*class=["\'][^"\']*page-title[^"\']*["\'][^>]*>(.*?)</h1>', html)
    body = _first_group(r'<div\b[^>]*id=["\']nr1["\'][^>]*>(.*?)</div>', html)
    if not title or not body:
        raise ValueError(f"chapter markup not recognized: {source_path}")
    return Chapter(source_path, title, body)


def build_ebook_text(title: str, author: str, intro: str, chapters: list[Chapter]) -> str:
    parts = [title, f"作者：{author}"]
    if intro:
        parts.extend(["简介", intro])
    for chapter in chapters:
        parts.extend([chapter.title, chapter.text])
    return "\n\n".join(parts).rstrip() + "\n"


def _resolve_env(value):
    if isinstance(value, dict):
        return {key: _resolve_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if isinstance(value, str) and value.startswith("env:"):
        name = value[4:]
        resolved = os.getenv(name)
        if not resolved:
            raise ValueError(f"required environment value is missing: {name}")
        return resolved
    return value


class SiteClient:
    def __init__(self, base_url: str, *, timeout: float, delay: float):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("base_url must be an https origin")
        self.base_url = base_url.rstrip("/") + "/"
        self.hostname = parsed.hostname
        self.delay = max(delay, 0.0)
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "AllBotOwnedSiteArchive/1.0 (+private-backup)"},
        )

    def get(self, path: str) -> str:
        url = urljoin(self.base_url, path)
        if urlparse(url).hostname != self.hostname:
            raise ValueError(f"cross-origin URL rejected: {url}")
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                if self.delay:
                    time.sleep(self.delay)
                return response.text
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(2**attempt)
        raise RuntimeError(f"fetch failed after retries: {url}") from last_error


def _open_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "create table if not exists archived_books "
        "(book_id text primary key, sha256 text not null, object_key text not null, archived_at text not null)"
    )
    return connection


def _s3_client(config: dict):
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        verify=config.get("ca_bundle") or config.get("ca_file") or True,
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
    )


def put_verified(client, bucket: str, key: str, payload: bytes, *, content_type: str, metadata: dict | None = None) -> None:
    expected = hashlib.sha256(payload).hexdigest()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType=content_type,
        Metadata=metadata or {},
    )
    response = client.get_object(Bucket=bucket, Key=key)
    actual_hash = hashlib.sha256()
    for chunk in response["Body"].iter_chunks():
        actual_hash.update(chunk)
    if actual_hash.hexdigest() != expected:
        raise RuntimeError(f"NAS read-back checksum mismatch: {key}")


def _archive_book(site: SiteClient, source_path: str) -> tuple[Book, bytes]:
    first_html = site.get(source_path)
    first = parse_book_page(source_path, first_html)
    chapter_paths = list(first.chapter_paths)
    for page_path in discover_book_pages(first.book_id, first_html)[1:]:
        page = parse_book_page(page_path, site.get(page_path))
        chapter_paths.extend(page.chapter_paths)
    chapter_paths = list(dict.fromkeys(chapter_paths))
    if not chapter_paths:
        raise RuntimeError(f"book has no chapters: {source_path}")
    chapters = [parse_chapter(path, site.get(path)) for path in chapter_paths]
    payload = build_ebook_text(first.title, first.author, first.intro, chapters).encode("utf-8")
    return first, payload


def run(config: dict, *, state_path: Path, execute: bool, limit_books: int | None) -> dict:
    site = SiteClient(
        config.get("base_url", "https://www.diyibanzhu.quest"),
        timeout=float(config.get("timeout_seconds", 30)),
        delay=float(config.get("request_delay_seconds", 0.25)),
    )
    first_catalog = site.get("/book/index.html")
    catalog_pages = discover_catalog_pages(first_catalog)
    if config.get("max_catalog_pages"):
        catalog_pages = catalog_pages[: int(config["max_catalog_pages"])]
    book_paths = parse_catalog_books(first_catalog)
    catalog_pages_scanned = 1
    for page in catalog_pages[1:]:
        if limit_books is not None and len(book_paths) >= limit_books:
            break
        book_paths.extend(parse_catalog_books(site.get(page)))
        catalog_pages_scanned += 1
    book_paths = list(dict.fromkeys(book_paths))
    if limit_books is not None:
        book_paths = book_paths[:limit_books]
    if not execute:
        return {"mode": "dry-run", "catalog_pages": catalog_pages_scanned, "books_discovered": len(book_paths)}

    nas = config["nas"]
    from scripts.media_archive_worker import clear_proxy_environment, validate_endpoint_route

    clear_proxy_environment()
    validate_endpoint_route(nas)
    client = _s3_client(nas)
    state = _open_state(state_path)
    uploaded = skipped = failed = 0
    prefix = str(nas.get("prefix", "ebooks/diyibanzhu")).strip("/")
    for source_path in book_paths:
        book_id = re.search(r"/list/(\d+)", source_path).group(1)  # type: ignore[union-attr]
        try:
            book, payload = _archive_book(site, source_path)
            digest = hashlib.sha256(payload).hexdigest()
            existing = state.execute("select sha256 from archived_books where book_id = ?", (book_id,)).fetchone()
            if existing and existing[0] == digest:
                skipped += 1
                continue
            object_key = f"{prefix}/{book_id}.txt"
            put_verified(
                client,
                nas["bucket"],
                object_key,
                payload,
                content_type="text/plain; charset=utf-8",
                metadata={"sha256": digest, "source-book-id": book_id},
            )
            metadata = json.dumps(
                {"book_id": book_id, "title": book.title, "author": book.author, "source": urljoin(site.base_url, source_path), "sha256": digest},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            put_verified(client, nas["bucket"], f"{prefix}/{book_id}.json", metadata, content_type="application/json")
            state.execute(
                "insert into archived_books values (?, ?, ?, datetime('now')) "
                "on conflict(book_id) do update set sha256=excluded.sha256, object_key=excluded.object_key, archived_at=excluded.archived_at",
                (book_id, digest, object_key),
            )
            state.commit()
            uploaded += 1
        except Exception as exc:  # Continue the corpus while reporting individual failures.
            failed += 1
            print(json.dumps({"book_id": book_id, "status": "failed", "error": str(exc)}, ensure_ascii=False))
    return {"mode": "execute", "books_discovered": len(book_paths), "uploaded": uploaded, "skipped": skipped, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit-books", type=int)
    args = parser.parse_args()
    if args.config.stat().st_mode & 0o077:
        raise SystemExit("config must be private (chmod 600)")
    config = _resolve_env(json.loads(args.config.read_text(encoding="utf-8")))
    result = run(config, state_path=args.state, execute=args.execute, limit_books=args.limit_books)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
