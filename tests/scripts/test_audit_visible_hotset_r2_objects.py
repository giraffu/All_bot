from scripts.audit_visible_hotset_r2_objects import (
    HistoryAuditResult,
    InputAuditResult,
    build_missing_records,
    summarize_audit_results,
)


def _audit_result(
    *,
    history_id=1,
    media_type="image",
    source_labels=None,
    media_standard_status="exists",
    media_runtime_status="exists",
    media_runtime_found_key="history/task-1/original.png",
    thumbnail_standard_status="exists",
    thumbnail_runtime_status="exists",
    thumbnail_runtime_found_key="history/task-1/thumb.webp",
    input_results=None,
):
    return HistoryAuditResult(
        history_id=history_id,
        user_id=100 + history_id,
        username=f"user-{history_id}",
        task_id=f"task-{history_id}",
        history_type="txt2img" if media_type == "image" else "custom_video",
        history_source="web",
        media_type=media_type,
        output_file=f"100/output_images/task-{history_id}.png",
        created_at="2026-06-17T00:00:00",
        is_favorited=False,
        source_labels=source_labels or ["all_gallery_posts"],
        media_standard_key=f"history/task-{history_id}/original.png",
        media_standard_status=media_standard_status,
        media_runtime_status=media_runtime_status,
        media_runtime_found_key=media_runtime_found_key,
        media_candidate_keys=[
            f"history/task-{history_id}/original.png",
            f"100/output_images/task-{history_id}.png",
        ],
        thumbnail_standard_key=f"history/task-{history_id}/thumb.webp",
        thumbnail_standard_status=thumbnail_standard_status,
        thumbnail_runtime_status=thumbnail_runtime_status,
        thumbnail_runtime_found_key=thumbnail_runtime_found_key,
        thumbnail_candidate_keys=[
            f"history/task-{history_id}/thumb.webp",
            f"100/output_images/task-{history_id}_thumb.webp",
        ],
        input_results=input_results or [],
    )


def test_summarize_audit_results_separates_runtime_and_standard_missing():
    results = [
        _audit_result(history_id=1),
        _audit_result(
            history_id=2,
            media_standard_status="missing",
            media_runtime_status="exists",
            media_runtime_found_key="100/output_images/task-2.png",
        ),
        _audit_result(
            history_id=3,
            media_standard_status="missing",
            media_runtime_status="missing",
            media_runtime_found_key=None,
            thumbnail_standard_status="missing",
            thumbnail_runtime_status="missing",
            thumbnail_runtime_found_key=None,
            input_results=[
                InputAuditResult(
                    file_path="bot-data/web_uploads/input.png",
                    r2_key="web_uploads/input.png",
                    status="missing",
                )
            ],
        ),
    ]

    summary = summarize_audit_results(
        results,
        selected_count=3,
        source_counts={"all_gallery_posts": {"raw": 3, "added": 3}},
        include_input_files=True,
    )

    assert summary["scanned_histories"] == 3
    assert summary["object_counts"]["media_runtime_exists"] == 2
    assert summary["object_counts"]["media_runtime_missing"] == 1
    assert summary["object_counts"]["media_standard_missing"] == 2
    assert summary["object_counts"]["thumbnail_runtime_missing"] == 1
    assert summary["object_counts"]["input_missing"] == 1
    assert summary["by_media_type"]["image"]["media_runtime_missing"] == 1
    assert summary["by_source_label"]["all_gallery_posts"][
        "any_runtime_or_input_missing"
    ] == 1


def test_build_missing_records_includes_standard_fallback_and_runtime_missing():
    result_with_fallback = _audit_result(
        history_id=10,
        media_standard_status="missing",
        media_runtime_status="exists",
        media_runtime_found_key="100/output_images/task-10.png",
    )
    result_runtime_missing = _audit_result(
        history_id=11,
        thumbnail_standard_status="missing",
        thumbnail_runtime_status="missing",
        thumbnail_runtime_found_key=None,
    )

    records = build_missing_records([result_with_fallback, result_runtime_missing])

    assert [
        (record.history_id, record.object_kind, record.audit_scope, record.status)
        for record in records
    ] == [
        (10, "media", "standard", "missing"),
        (11, "thumbnail", "runtime", "missing"),
    ]
    assert records[0].runtime_found_key == "100/output_images/task-10.png"
