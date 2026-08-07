import hashlib
import os
import sqlite3

from scripts.refresh_r2_temp_cleanup_inventory import refresh_inventory


class FakePaginator:
    def paginate(self, **_kwargs):
        return [
            {
                "Contents": [
                    {
                        "Key": "task-results/a/primary.png",
                        "Size": 12,
                        "ETag": '"etag-a"',
                        "LastModified": "2026-08-07T00:00:00Z",
                    },
                    {
                        "Key": "root.png",
                        "Size": 4,
                        "ETag": '"etag-b"',
                        "LastModified": "2026-08-07T00:01:00Z",
                    },
                ]
            }
        ]


class FakeClient:
    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator()


class FailingClient:
    class _Paginator:
        def paginate(self, **_kwargs):
            raise RuntimeError("offline")

    def get_paginator(self, _name):
        return self._Paginator()


def test_inventory_refresh_publishes_a_private_atomic_current_snapshot(tmp_path):
    result = refresh_inventory(
        state_root=tmp_path,
        client=FakeClient(),
        bucket="user-data-prod",
        generated_at="20260807T000000Z",
    )

    current = tmp_path / "current.sqlite3"
    assert current.is_symlink()
    target = current.resolve()
    assert target.name == "inventory-20260807T000000Z.sqlite3"
    assert target.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as db:
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert db.execute("select count(*),sum(size) from objects").fetchone() == (2, 16)
    assert result["object_count"] == 2
    assert result["bytes"] == 16
    assert result["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert os.readlink(current) == target.name


def test_failed_refresh_does_not_replace_the_last_good_current_snapshot(tmp_path):
    old = tmp_path / "inventory-old.sqlite3"
    old.write_bytes(b"old")
    (tmp_path / "current.sqlite3").symlink_to(old.name)

    try:
        refresh_inventory(
            state_root=tmp_path,
            client=FailingClient(),
            generated_at="20260807T000001Z",
        )
    except RuntimeError as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("offline inventory refresh must fail")

    assert os.readlink(tmp_path / "current.sqlite3") == old.name
    assert not list(tmp_path.glob(".*.tmp"))
