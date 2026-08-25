from types import SimpleNamespace

from src.core.media_archive import (
    ARCHIVE_BUCKET,
    archive_blob_key,
    plan_archive_asset_restore_keys,
    plan_archive_thumbnail_restore_keys,
    extract_history_media_assets,
    media_manifest_hash,
    receipts_cover_assets,
)


def test_restore_key_planning_uses_source_ref_without_runtime_config():
    originals = plan_archive_asset_restore_keys(
        task_id="task-1",
        source_ref="bot-data/outputs/result.png",
    )
    thumbnails = plan_archive_thumbnail_restore_keys(
        task_id="task-1",
        source_ref="bot-data/outputs/result.png",
        history_type="image",
    )

    assert "history/task-1/original.png" in originals
    assert "result.png" in originals
    assert thumbnails == {
        "history/task-1/thumb.webp",
        "result_thumb.webp",
    }


def test_restore_key_planning_only_rehydrates_canonical_durable_targets():
    originals = plan_archive_asset_restore_keys(
        task_id="registry-1",
        source_ref="user-data-prod/task-results/backend-1/primary.png",
    )
    thumbnails = plan_archive_thumbnail_restore_keys(
        task_id="registry-1",
        source_ref="task-results/backend-1/primary.png",
        history_type="image",
    )
    inputs = plan_archive_asset_restore_keys(
        task_id="registry-1",
        source_ref="task-inputs/registry-1/0.png",
    )

    assert originals == {"task-results/backend-1/primary.png"}
    assert thumbnails == {"task-results/backend-1/primary_thumb.webp"}
    assert inputs == {"task-inputs/registry-1/0.png"}


def test_extract_history_media_assets_handles_multi_input_and_nested_extra_paths():
    history = SimpleNamespace(
        id=42,
        input_file="users/1/a.png|https://cdn.example/b.jpg||users/1/a.png",
        output_file="users/1/result.mp4",
        extra_outputs={
            "last_frame": {"path": "users/1/last.png", "width": 720},
            "variants": [
                {"path": "users/1/v1.png"},
                {"url": "https://cdn.example/ignored.png"},
            ],
        },
    )

    assets = extract_history_media_assets(history)

    assert [(asset.role, asset.ordinal, asset.source_ref) for asset in assets] == [
        ("input", 0, "users/1/a.png"),
        ("input", 1, "https://cdn.example/b.jpg"),
        ("input", 2, "users/1/a.png"),
        ("output", 0, "users/1/result.mp4"),
        ("extra:last_frame", 0, "users/1/last.png"),
        ("extra:variants", 0, "users/1/v1.png"),
    ]


def test_archive_blob_key_is_content_addressed_and_normalizes_extension():
    digest = "ab" + "cd" + "1" * 60
    assert archive_blob_key(digest, ".JPEG") == f"blobs/sha256/ab/cd/{digest}.jpg"
    assert ARCHIVE_BUCKET == "allbot-media-archive-v1"


def test_receipts_must_cover_every_logical_asset_with_verified_hash():
    assets = extract_history_media_assets(
        SimpleNamespace(
            id=7,
            input_file="in.png",
            output_file="out.png",
            extra_outputs=None,
        )
    )
    partial = [
        SimpleNamespace(
            role="input", ordinal=0, status="archived_verified", sha256="a" * 64
        )
    ]
    complete = partial + [
        SimpleNamespace(
            role="output", ordinal=0, status="archived_verified", sha256="b" * 64
        )
    ]

    assert receipts_cover_assets(assets, partial) is False
    assert receipts_cover_assets(assets, complete) is True


def test_media_manifest_hash_is_stable_and_changes_with_asset_identity():
    first = extract_history_media_assets(
        SimpleNamespace(
            id=1, input_file="a.png|b.png", output_file="c.png", extra_outputs=None
        )
    )
    same = extract_history_media_assets(
        SimpleNamespace(
            id=1, input_file="a.png|b.png", output_file="c.png", extra_outputs=None
        )
    )
    changed = extract_history_media_assets(
        SimpleNamespace(
            id=1, input_file="b.png|a.png", output_file="c.png", extra_outputs=None
        )
    )

    assert media_manifest_hash(first) == media_manifest_hash(same)
    assert media_manifest_hash(first) != media_manifest_hash(changed)
