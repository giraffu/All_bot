from scripts.r2_history_snapshot_backup import (
    BandwidthLimiter,
    MANIFEST_SCHEMA,
    build_manifest,
    copy_one,
    extract_snapshot_references,
    normalize_snapshot_key,
)


class _Body:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, _size: int) -> bytes:
        payload, self.payload = self.payload, b""
        return payload


class _Client:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.head_calls = 0

    def head_object(self, **_kwargs):
        self.head_calls += 1
        return {"ContentLength": len(self.payload), "ETag": '"stable"'}

    def get_object(self, **_kwargs):
        return {"Body": _Body(self.payload)}


def test_snapshot_manifest_uses_input_output_and_nested_extra_paths() -> None:
    manifest = build_manifest(
        [
            {
                "id": 7,
                "input_file": "task-inputs/run-1/0.png|user-data-prod/history/a/input.jpg",
                "output_file": "https://example.invalid/user-data-prod/task-results/run-1/primary.webp?sig=x",
                "extra_outputs": {"preview": {"items": [{"path": "history/a/extra.mp4"}]}},
            }
        ],
        source_bucket="user-data-prod",
        snapshot_label="snapshot-1",
    )

    assert manifest["schema"] == MANIFEST_SCHEMA
    assert [item["key"] for item in manifest["objects"]] == [
        "history/a/extra.mp4",
        "history/a/input.jpg",
        "task-inputs/run-1/0.png",
        "task-results/run-1/primary.webp",
    ]
    assert manifest["rejected_references"] == []


def test_snapshot_manifest_deduplicates_but_keeps_all_logical_references() -> None:
    manifest = build_manifest(
        [
            {"id": 1, "input_file": "history/shared.png", "output_file": None, "extra_outputs": {}},
            {"id": 2, "input_file": None, "output_file": "history/shared.png", "extra_outputs": {}},
        ],
        source_bucket="user-data-prod",
        snapshot_label="snapshot-1",
    )

    assert len(manifest["objects"]) == 1
    assert len(manifest["objects"][0]["references"]) == 2


def test_snapshot_key_rejects_path_escape_and_preserves_bucket_relative_path() -> None:
    assert normalize_snapshot_key("user-data-prod/history/a.png", source_bucket="user-data-prod") == "history/a.png"
    assert normalize_snapshot_key("../private/key", source_bucket="user-data-prod") is None
    assert normalize_snapshot_key("", source_bucket="user-data-prod") is None
    assert normalize_snapshot_key("history/a//b.png", source_bucket="user-data-prod") is None


def test_invalid_extra_outputs_does_not_create_assets() -> None:
    assert extract_snapshot_references(
        [{"id": 8, "input_file": None, "output_file": None, "extra_outputs": "[]"}]
    ) == []


def test_copy_preserves_key_and_resumes_only_after_local_sha_verification(tmp_path) -> None:
    client = _Client(b"snapshot-media")
    root = tmp_path / "nas"
    state = tmp_path / "state" / "snapshot.sqlite3"
    limiter = BandwidthLimiter(1024 * 1024 * 1024)

    first = copy_one(
        client,
        bucket="user-data-prod",
        root=root,
        key="history/task-1/result.png",
        state_path=state,
        limiter=limiter,
    )
    second = copy_one(
        client,
        bucket="user-data-prod",
        root=root,
        key="history/task-1/result.png",
        state_path=state,
        limiter=limiter,
    )

    assert first == {"key": "history/task-1/result.png", "status": "completed", "bytes": 14}
    assert second == {"key": "history/task-1/result.png", "status": "already_verified", "bytes": 14}
    assert (root / "history/task-1/result.png").read_bytes() == b"snapshot-media"
    assert client.head_calls == 2
