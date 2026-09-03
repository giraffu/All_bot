import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock
from types import SimpleNamespace

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app import routes_archive


@pytest.mark.asyncio
async def test_archive_browser_fails_closed_when_local_login_is_disabled(monkeypatch):
    monkeypatch.delenv("LOCAL_ANALYTICS_AUTH_ENABLED", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/archive/assets/1")

    assert response.status_code == 503
    assert "requires configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_archive_content_rejects_cloudflare_tunnel_before_database_access(
    monkeypatch,
):
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_PASSWORD_HASH", "unused")
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/archive/assets/1/content",
            headers={"CF-Ray": "abc-SJC", "CF-Connecting-IP": "203.0.113.2"},
        )

    assert response.status_code == 403
    assert "LAN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_archive_status_exposes_progress_backlog_capacity_and_alerts(monkeypatch):
    fetchrow = AsyncMock(
        side_effect=[
            {
                "logical_assets": 10,
                "verified_assets": 7,
                "offline_assets": 1,
                "provisional_missing": 1,
                "confirmed_lost": 0,
                "checksum_errors": 1,
                "pending_assets": 0,
            },
            {"blob_count": 6, "archived_bytes": 80},
            {
                "run_type": "archive",
                "status": "running",
                "stats": '{"bytes_per_second": 5}',
                "error": None,
            },
            {"present": True},
            {
                "backlog": 3,
                "leased": 1,
                "manual_review": 0,
                "oldest_backlog_seconds": 90000,
            },
            {
                "snapshot_id": "snapshot-1",
                "status_counts": '{"backed_up":7,"file_missing":2}',
            },
        ]
    )
    monkeypatch.setattr(routes_archive, "_fetchrow", fetchrow)
    monkeypatch.setattr(routes_archive, "_fetch", AsyncMock(return_value=[]))
    monkeypatch.setenv("NAS_ARCHIVE_CAPACITY_BYTES", "100")

    result = await routes_archive.archive_status()

    assert result["usage_ratio"] == 0.8
    assert result["pause_reason"] == "nas_usage_80_stop_cold"
    assert result["outbox"]["backlog"] == 3
    assert result["snapshot_backup"]["status_counts"]["backed_up"] == 7
    assert result["latest_run"]["stats"] == {"bytes_per_second": 5}
    assert result["throughput_bytes_per_second"] == 5
    assert result["alerts"]["checksum_error"] is True
    assert result["alerts"]["archive_critical"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role_group", "expected_fragment"),
    [("input", "a.role='input'"), ("output", "a.role<>'input'"), ("all", "true")],
)
async def test_history_media_filters_role_groups_and_only_exposes_verified_local_urls(
    monkeypatch, role_group, expected_fragment
):
    monkeypatch.setattr(
        routes_archive,
        "_fetchrow",
        AsyncMock(
            return_value={
                "id": 42,
                "task_id": "task-42",
                "user_id": 7,
                "type": "edit",
                "created_at": "2026-08-06T00:00:00Z",
            }
        ),
    )
    official_assets = [
            {
                "id": 101,
                "role": "input",
                "ordinal": 0,
                "original_ref": "web_uploads/input.png",
                "status": "archived_verified",
                "sha256": "a" * 64,
                "byte_size": 12,
                "mime_type": "image/png",
                "nas_bucket": "private-bucket",
                "nas_key": "blobs/private-key.png",
            },
            {
                "id": 102,
                "role": "output",
                "ordinal": 0,
                "original_ref": "task-results/task-42/primary.png",
                "status": "pending_probe",
                "sha256": None,
                "byte_size": None,
                "mime_type": None,
                "nas_bucket": None,
                "nas_key": None,
            },
        ]
    fetch = AsyncMock(side_effect=[[], official_assets])
    monkeypatch.setattr(routes_archive, "_fetch", fetch)

    result = await routes_archive.history_media(42, role_group=role_group)

    assert expected_fragment in " ".join(fetch.await_args_list[1].args[0].split())
    assert result["role_group"] == role_group
    assert result["assets"][0]["local_available"] is True
    assert result["assets"][0]["content_url"] == "/api/archive/assets/101/content"
    assert result["assets"][1]["local_available"] is False
    assert result["assets"][1]["content_url"] is None
    assert "nas_bucket" not in result["assets"][0]
    assert "nas_key" not in result["assets"][0]


@pytest.mark.asyncio
async def test_archive_content_returns_service_unavailable_when_nas_read_fails(monkeypatch):
    monkeypatch.setattr(
        routes_archive,
        "_fetchrow",
        AsyncMock(
            return_value={
                "original_ref": "task-results/task/primary.mp4",
                "status": "archived_verified",
                "byte_size": 99,
                "mime_type": "video/mp4",
                "nas_bucket": "archive",
                "nas_key": "blobs/a.mp4",
            }
        ),
    )
    failing_client = SimpleNamespace(
        get_object=lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("offline"))
    )
    monkeypatch.setattr(routes_archive, "_nas_client", lambda: failing_client)

    with pytest.raises(Exception) as exc_info:
        await routes_archive.archive_asset_content(101, range_header="bytes=0-31")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "NAS archive content is temporarily unavailable"


@pytest.mark.asyncio
async def test_archive_content_forwards_valid_video_range_headers(monkeypatch):
    monkeypatch.setattr(
        routes_archive,
        "_fetchrow",
        AsyncMock(
            return_value={
                "original_ref": "task-results/task/primary.mp4",
                "status": "archived_verified",
                "byte_size": 100,
                "mime_type": "video/mp4",
                "nas_bucket": "archive",
                "nas_key": "blobs/a.mp4",
            }
        ),
    )

    class Body:
        def iter_chunks(self, chunk_size):
            assert chunk_size == 1024 * 1024
            yield b"video"

        def close(self):
            return None

    client = SimpleNamespace(
        get_object=lambda **kwargs: {
            "Body": Body(),
            "ContentRange": "bytes 0-31/100",
            "ContentLength": 32,
            "request": kwargs,
        }
    )
    monkeypatch.setattr(routes_archive, "_nas_client", lambda: client)

    response = await routes_archive.archive_asset_content(101, range_header="bytes=0-31")

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-31/100"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.media_type == "video/mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["bytes=-", "bytes=20-10", "items=0-10"])
async def test_archive_content_rejects_invalid_ranges_before_nas_access(monkeypatch, value):
    monkeypatch.setattr(
        routes_archive,
        "_fetchrow",
        AsyncMock(
            return_value={
                "original_ref": "x.mp4",
                "status": "archived_verified",
                "byte_size": 100,
                "mime_type": "video/mp4",
                "nas_bucket": "archive",
                "nas_key": "blob",
            }
        ),
    )
    monkeypatch.setattr(
        routes_archive,
        "_nas_client",
        lambda: (_ for _ in ()).throw(AssertionError("NAS should not be accessed")),
    )

    with pytest.raises(Exception) as exc_info:
        await routes_archive.archive_asset_content(1, range_header=value)

    assert exc_info.value.status_code == 416


@pytest.mark.asyncio
async def test_history_media_prefers_snapshot_status_rows(monkeypatch):
    monkeypatch.setattr(
        routes_archive,
        "_fetchrow",
        AsyncMock(
            return_value={
                "id": 42,
                "task_id": "task-42",
                "user_id": 7,
                "type": "edit",
                "created_at": "2026-08-06T00:00:00Z",
            }
        ),
    )
    monkeypatch.setattr(
        routes_archive,
        "_fetch",
        AsyncMock(
            side_effect=[
                [
                    {
                        "id": 501,
                        "role": "input",
                        "ordinal": 0,
                        "original_ref": "100/input_images/a.png",
                        "object_key": "100/input_images/a.png",
                        "backup_status": "backed_up",
                        "batch_number": 12,
                        "sha256": "b" * 64,
                        "byte_size": 25,
                        "snapshot_label": "snapshot-1",
                    },
                    {
                        "id": 502,
                        "role": "output",
                        "ordinal": 0,
                        "original_ref": "100/output_images/missing.png",
                        "object_key": "100/output_images/missing.png",
                        "backup_status": "file_missing",
                        "batch_number": None,
                        "sha256": None,
                        "byte_size": None,
                        "snapshot_label": "snapshot-1",
                    },
                ],
                [],
            ]
        ),
    )

    result = await routes_archive.history_media(42, role_group="all")

    assert result["media_source"] == "snapshot_backup"
    assert result["assets"][0]["status"] == "backed_up"
    assert result["assets"][0]["local_available"] is True
    assert result["assets"][0]["content_url"] == "/api/snapshot-assets/501/content"
    assert result["assets"][1]["status"] == "file_missing"
    assert result["assets"][1]["content_url"] is None


@pytest.mark.asyncio
async def test_snapshot_content_proxies_only_verified_batch_receipts(monkeypatch):
    monkeypatch.setattr(
        routes_archive,
        "_fetchrow",
        AsyncMock(
            return_value={
                "original_ref": "100/output_images/a.mp4",
                "object_key": "100/output_images/a.mp4",
                "backup_status": "backed_up",
                "batch_number": 12,
                "byte_size": 100,
            }
        ),
    )
    monkeypatch.setattr(
        routes_archive,
        "_snapshot_gateway_response",
        lambda **kwargs: {
            "body": iter([b"video"]),
            "content_length": 32,
            "content_range": "bytes 0-31/100",
        },
    )

    response = await routes_archive.snapshot_asset_content(
        501, range_header="bytes=0-31"
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-31/100"
    assert response.media_type == "video/mp4"
