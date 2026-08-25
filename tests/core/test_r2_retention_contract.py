from shared.r2_retention_contract import (
    build_staged_user_upload_key,
    build_staged_worker_result_key,
    build_task_input_key,
    build_task_result_key,
    normalize_durable_media_key,
)


def test_worker_result_keys_separate_staging_from_durable_namespace():
    assert build_staged_worker_result_key(
        task_id="backend-1",
        source_name="raw result.png",
        role="primary",
    ) == "staging/worker-results/backend-1/primary.png"
    assert build_staged_worker_result_key(
        task_id="backend-1",
        source_name="frames/last frame.png",
        role="last/frame",
        ordinal=2,
    ) == "staging/worker-results/backend-1/extras/last-frame-2.png"

    assert build_task_result_key(
        task_id="backend-1",
        source_name="raw result.png",
        role="primary",
    ) == "task-results/backend-1/primary.png"
    assert build_task_result_key(
        task_id="backend-1",
        source_name="frames/last frame.png",
        role="last/frame",
        ordinal=2,
    ) == "task-results/backend-1/extras/last-frame-2.png"


def test_user_upload_and_task_input_keys_are_explicitly_separated():
    assert build_staged_user_upload_key(
        user_id=42,
        upload_id="upload-1",
        filename="my face.PNG",
    ) == "staging/user-uploads/42/upload-1.png"
    assert build_task_input_key(
        task_id="registry-1",
        ordinal=1,
        source_name="staging/user-uploads/42/upload-1.png",
    ) == "task-inputs/registry-1/1.png"


def test_durable_media_keys_normalize_plain_bucket_prefixed_and_url_references():
    assert (
        normalize_durable_media_key("task-results/backend-1/primary.png")
        == "task-results/backend-1/primary.png"
    )
    assert (
        normalize_durable_media_key(
            "user-data-prod/task-inputs/registry-1/0.png"
        )
        == "task-inputs/registry-1/0.png"
    )
    assert (
        normalize_durable_media_key(
            "https://objects.example/user-data-prod/task-results/backend-1/primary.png?sig=x"
        )
        == "task-results/backend-1/primary.png"
    )
    assert normalize_durable_media_key("123/output_images/legacy.png") is None


def test_key_contract_rejects_path_traversal_and_empty_ids():
    for builder, kwargs in (
        (
            build_staged_worker_result_key,
            {"task_id": "", "source_name": "a.png", "role": "primary"},
        ),
        (
            build_staged_user_upload_key,
            {"user_id": 1, "upload_id": "../bad", "filename": "a.png"},
        ),
        (
            build_task_input_key,
            {"task_id": "../bad", "ordinal": 0, "source_name": "a.png"},
        ),
    ):
        try:
            builder(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe key input must be rejected")
