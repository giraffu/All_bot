from dashboard.backend.services.runpod_admin_operation import (
    RunPodAdminOperation,
    append_operation_log,
    normalized_stored_operation_payload,
    operation_payload,
)


def test_operation_payload_marks_attached_add_operation_terminable():
    operation = RunPodAdminOperation(
        id="op-attached",
        action="add",
        profile="img2img",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
        status="running",
        process=object(),
    )

    payload = operation_payload(operation)

    assert payload["id"] == "op-attached"
    assert payload["attached"] is True
    assert payload["can_terminate"] is True
    assert payload["can_terminate_reason"] is None


def test_operation_payload_explains_detached_running_operation():
    operation = RunPodAdminOperation(
        id="op-detached",
        action="add",
        profile="img2img",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
        owner_id="old-host:123:abc",
        status="running",
    )

    payload = operation_payload(operation)

    assert payload["attached"] is False
    assert payload["can_terminate"] is False
    assert "detached" in payload["can_terminate_reason"]


def test_append_log_redacts_sensitive_text_and_deduplicates_cleanup_slots():
    operation = RunPodAdminOperation(
        id="op-log",
        action="add",
        profile="wan22_video_v2",
        command=["bash", "scripts/runpod_prod_ops.sh", "add"],
    )

    append_operation_log(
        operation,
        "Authorization: Bearer abc.def token=secret runpod_create_pod_03: running",
    )
    append_operation_log(
        operation,
        "x-amz-signature=123 runpod_create_pod_03: ok",
    )

    assert operation.cleanup_slots == ["03"]
    log_tail = "\n".join(operation.log_lines)
    assert "abc.def" not in log_tail
    assert "token=secret" not in log_tail
    assert "x-amz-signature=123" not in log_tail
    assert "<redacted>" in log_tail


def test_normalized_stored_payload_is_detached_and_not_terminable():
    payload = normalized_stored_operation_payload(
        {
            "id": "op-store",
            "action": "add",
            "profile": "img2img",
            "status": "running",
            "terminate_requested": False,
            "owner_id": "old-host:123:abc",
            "attached": True,
            "can_terminate": True,
        }
    )

    assert payload["attached"] is False
    assert payload["can_terminate"] is False
    assert "detached" in payload["can_terminate_reason"]


def test_normalized_stored_payload_keeps_finished_reason_specific():
    payload = normalized_stored_operation_payload(
        {
            "id": "op-done",
            "action": "add",
            "profile": "img2img",
            "status": "succeeded",
            "terminate_requested": False,
        }
    )

    assert payload["can_terminate"] is False
    assert payload["can_terminate_reason"] == "RunPod operation is already succeeded"
