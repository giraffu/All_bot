import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile


from scripts.sync_minio_ebooks_to_calibre import _publisher, build_epub, discover_ready_books, sync_once


def test_cwa_skips_recursive_library_chown_for_nas_bind_mount():
    compose = (Path(__file__).parents[2] / "ops/calibre_web_nas/docker-compose.yml").read_text()

    assert 'NETWORK_SHARE_MODE: "true"' in compose


def test_build_epub_contains_metadata_and_valid_container():
    payload = build_epub(
        book_id="42",
        title="测试书",
        author="测试作者",
        text="第一章\n\n正文 & 内容",
        source_sha256="a" * 64,
        chunk_chars=8,
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.infolist()[0].compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
        package = archive.read("OEBPS/package.opf").decode()
        assert "测试书" in package
        assert "测试作者" in package
        assert len([name for name in archive.namelist() if name.startswith("OEBPS/text-")]) > 1


def test_discovery_requires_txt_and_json_pair():
    keys = [
        "ebooks/diyibanzhu/1.txt",
        "ebooks/diyibanzhu/1.json",
        "ebooks/diyibanzhu/2.txt",
        "ebooks/diyibanzhu/not-an-id.json",
    ]

    assert discover_ready_books(keys, "ebooks/diyibanzhu") == ["1"]


def test_sync_is_idempotent_and_rejects_mismatched_source_digest():
    good_text = "书名\n\n作者：作者\n\n正文".encode()
    objects = {
        "ebooks/diyibanzhu/1.txt": good_text,
        "ebooks/diyibanzhu/1.json": json.dumps(
            {
                "book_id": "1",
                "title": "书名",
                "author": "作者",
                "sha256": hashlib.sha256(good_text).hexdigest(),
            }
        ).encode(),
        "ebooks/diyibanzhu/2.txt": b"changed",
        "ebooks/diyibanzhu/2.json": json.dumps(
            {"book_id": "2", "title": "坏书", "author": "作者", "sha256": "0" * 64}
        ).encode(),
    }

    class FakeS3:
        def get_object(self, *, Bucket, Key):
            return {"Body": io.BytesIO(objects[Key])}

    connection = sqlite3.connect(":memory:")
    published = []
    kwargs = dict(
        client=FakeS3(),
        bucket="archive",
        prefix="ebooks/diyibanzhu",
        book_ids=["1", "2"],
        state=connection,
        publish=lambda book_id, payload: published.append((book_id, payload)),
    )

    first = sync_once(**kwargs)
    second = sync_once(**kwargs)

    assert first == {"published": 1, "skipped": 0, "failed": 1}
    assert second == {"published": 0, "skipped": 1, "failed": 1}
    assert [item[0] for item in published] == ["1"]


def test_nas_publisher_uses_legacy_scp_for_shell_visible_volume_paths(monkeypatch):
    commands = []
    monkeypatch.setattr(
        "scripts.sync_minio_ebooks_to_calibre.subprocess.run",
        lambda command, **kwargs: commands.append(command),
    )

    publish = _publisher(
        "allbot-nas-archive",
        "/volume1/AllBotEbooks/source-epub",
        "/volume1/AllBotEbooks/ingest",
    )
    publish("42", b"epub")

    assert commands[0][:3] == ["scp", "-O", "-q"]
    assert commands[1][:4] == ["ssh", "-o", "BatchMode=yes", "allbot-nas-archive"]
