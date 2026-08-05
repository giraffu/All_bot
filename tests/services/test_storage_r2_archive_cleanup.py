from src.services.storage_r2_cleanup import build_archive_asset_cleanup_keys
from scripts.media_archive_r2_cleanup import CANDIDATE_SQL, HOT_REFERENCE_SQL


def test_archive_cleanup_covers_input_without_deleting_output_thumbnail():
    keys = build_archive_asset_cleanup_keys(
        "task-1", "uploads/reference.png", "image", "input"
    )
    assert "history/task-1/reference.png" in keys
    assert not any(key.endswith("thumb.webp") for key in keys)


def test_archive_cleanup_output_includes_derived_thumbnail():
    keys = build_archive_asset_cleanup_keys(
        "task-1", "outputs/result.png", "image", "output"
    )
    assert "history/task-1/result.png" in keys
    assert any(key.endswith("thumb.webp") for key in keys)


def test_cleanup_query_requires_verified_all_role_receipts_and_hot_key_audit():
    assert "r.status='archived_verified'" in CANDIDATE_SQL
    assert "r.role='output'" not in CANDIDATE_SQL
    assert "input_file" in HOT_REFERENCE_SQL
    assert "extra_outputs" in HOT_REFERENCE_SQL
