import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest
from asgi_correlation_id import correlation_id

from src.services import task_service_flow
from src.services.private_bot_update_admission import (
    PrivateBotUpdateAdmissionScope,
    activate_private_bot_update_scope,
)
from src.services.private_qqcc_continuation_service import (
    PrivateQqccContinuationTaskRef,
    PrivateQqccContinuationUnavailable,
    activate_private_qqcc_continuation_task,
)
from src.services.task_service_entrypoint_support import build_bot_task_flow_context
from src.services.task_service_types import BotTaskMessageSpec, BotTaskSubmissionContext


@pytest.mark.asyncio
async def test_submit_bot_task_sets_runtime_state_and_returns_saved_inputs(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 18,
            "registry_task_id": "registry-1",
            "backend_task_id": "backend-1",
            "saved_inputs": ["input-a.png"],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    runtime_state = SimpleNamespace(
        task_submitted=False,
        actual_cost=0,
        registry_task_id=None,
        backend_task_id=None,
    )

    token = correlation_id.set(None)
    try:
        task_id, backend_task_id, saved_inputs = await task_service_flow.submit_bot_task(
            submission=BotTaskSubmissionContext(
                runtime_state=runtime_state,
                internal_user_id=456,
                username="tester",
                task_type="ltx_video",
                inputs={"prompt": "hello"},
                source_post_id=9,
                deduct_quota=False,
            ),
        )
        assert correlation_id.get() == task_id
    finally:
        correlation_id.reset(token)

    assert isinstance(task_id, str)
    assert backend_task_id == "backend-1"
    assert saved_inputs == ["input-a.png"]
    assert runtime_state.task_submitted is True
    assert runtime_state.actual_cost == 18
    assert runtime_state.registry_task_id == "registry-1"
    assert runtime_state.backend_task_id == "backend-1"
    process_submit.assert_awaited_once()
    kwargs = process_submit.await_args.kwargs
    assert kwargs["user_id"] == 456
    assert kwargs["username"] == "tester"
    assert kwargs["task_type"] == "ltx_video"
    assert kwargs["inputs"] == {"prompt": "hello"}
    assert kwargs["task_id"] == task_id
    assert kwargs["client_type"] == "bot"
    assert kwargs["source_post_id"] == 9
    assert kwargs["deduct_quota"] is False
    assert kwargs["cost_override"] is None
    assert kwargs["delivery_context"] is None
    assert kwargs["base_priority"] == 0
    assert kwargs["user_cancel_allowed"] is True


def test_select_result_saved_inputs_uses_requested_indices_with_fallback():
    saved_inputs = ["body.png", "original-face.png"]

    assert task_service_flow.select_result_saved_inputs(saved_inputs, [1]) == [
        "original-face.png"
    ]
    assert task_service_flow.select_result_saved_inputs(saved_inputs, [9]) == saved_inputs
    assert task_service_flow.select_result_saved_inputs(saved_inputs, None) == saved_inputs


def test_build_bot_task_flow_context_keeps_cost_override_for_internal_tasks():
    flow = build_bot_task_flow_context(
        context=SimpleNamespace(),
        chat_id=100,
        internal_user_id=200,
        username="qqcc",
        task_type="face_swap",
        inputs={"images": ["body.png", "face.png"]},
        prompt="internal face swap",
        is_video=False,
        message_spec=BotTaskMessageSpec(initial_status_text="提交中"),
        task_label="QQCC internal task",
        cleanup=False,
        cleanup_paths=[],
        cost_override=2,
        base_priority=100,
        allow_cancel=False,
        user_cancel_allowed=False,
    )

    assert flow.request.cost_override == 2
    assert flow.request.base_priority == 100
    assert flow.request.user_cancel_allowed is False
    assert flow.presentation.allow_cancel is False


@pytest.mark.asyncio
async def test_submit_bot_task_uses_submission_client_type(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 6,
            "registry_task_id": "registry-qqcc",
            "backend_task_id": "backend-qqcc",
            "saved_inputs": [],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)

    await task_service_flow.submit_bot_task(
        submission=BotTaskSubmissionContext(
            runtime_state=SimpleNamespace(
                task_submitted=False,
                actual_cost=0,
                registry_task_id=None,
                backend_task_id=None,
            ),
            internal_user_id=789,
            username="qqcc",
            task_type="quick_image",
            inputs={"prompt": "lazy"},
            client_type="bot:qqcc",
        ),
    )

    assert process_submit.await_args.kwargs["client_type"] == "bot:qqcc"


@pytest.mark.asyncio
async def test_submit_bot_task_passes_recovery_contract_to_registry(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 2,
            "registry_task_id": "registry-private",
            "backend_task_id": "backend-private",
            "saved_inputs": [],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)

    recovery_metadata = {
        "_bot_task_recovery": {
            "version": 1,
            "send_result": False,
            "requires_continuation": True,
        }
    }
    await task_service_flow.submit_bot_task(
        submission=BotTaskSubmissionContext(
            runtime_state=SimpleNamespace(
                task_submitted=False,
                actual_cost=0,
                registry_task_id=None,
                backend_task_id=None,
            ),
            internal_user_id=789,
            username="qqcc-private",
            task_type="edit",
            inputs={"prompt": "hidden chain step"},
            client_type="bot",
            recovery_metadata=recovery_metadata,
        ),
    )

    assert process_submit.await_args.kwargs["registry_metadata"] == recovery_metadata


def test_build_private_task_recovery_metadata_serializes_presentation_contract():
    flow = SimpleNamespace(
        request=SimpleNamespace(
            context=SimpleNamespace(lang="zh"),
            prompt="internal prompt",
            task_type="face_swap",
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(
                initial_status_text="处理中",
                completion_caption="✅ 绘图完成",
            ),
            send_result=True,
            delete_status=True,
            allow_contribute=False,
            record_history=False,
            result_task_type="edit",
            result_prompt="visible prompt",
            result_input_image_indices=[1],
            result_meta={"_qqcc_regenerate": {"kind": "quick_image"}},
        ),
    )

    metadata = task_service_flow.build_bot_task_recovery_metadata(
        flow=flow,
        client_type="bot:qqcc-private:7",
    )

    assert metadata == {
        "_bot_task_recovery": {
            "version": 1,
            "send_result": True,
            "requires_continuation": False,
            "delete_status": True,
            "allow_contribute": False,
            "record_history": False,
            "result_task_type": "edit",
            "result_prompt": "visible prompt",
            "result_input_image_indices": [1],
            "result_meta": {"_qqcc_regenerate": {"kind": "quick_image"}},
            "completion_caption": "✅ 绘图完成",
            "language_code": "zh",
        }
    }

    assert (
        task_service_flow.build_bot_task_recovery_metadata(
            flow=flow,
            client_type="bot:qqcc",
        )
        == {}
    )


def test_build_main_bot_recovery_metadata_preserves_hidden_history_policy():
    flow = SimpleNamespace(
        request=SimpleNamespace(
            context=SimpleNamespace(lang="zh"),
            prompt="internal prompt",
            task_type="pornmaster_flux2_edit_bf16",
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="处理中"),
            send_result=False,
            delete_status=False,
            allow_contribute=False,
            record_history=False,
            result_task_type=None,
            result_prompt=None,
            result_input_image_indices=None,
            result_meta=None,
        ),
    )

    metadata = task_service_flow.build_bot_task_recovery_metadata(
        flow=flow,
        client_type="bot",
    )

    assert metadata["_bot_task_recovery"]["send_result"] is False
    assert metadata["_bot_task_recovery"]["record_history"] is False


def test_build_private_task_recovery_metadata_includes_durable_continuation_ref():
    flow = SimpleNamespace(
        request=SimpleNamespace(
            context=SimpleNamespace(lang="zh"),
            prompt="hidden prompt",
            task_type="edit",
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="处理中"),
            send_result=False,
            delete_status=False,
            allow_contribute=False,
            result_task_type=None,
            result_prompt=None,
            result_input_image_indices=None,
            result_meta=None,
        ),
    )
    ref = PrivateQqccContinuationTaskRef(
        chain_id="chain-1",
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-1",
        executor_token="executor-1",
    )

    with activate_private_qqcc_continuation_task(ref):
        metadata = task_service_flow.build_bot_task_recovery_metadata(
            flow=flow,
            client_type="bot:qqcc-private:7",
        )

    assert metadata["_bot_task_recovery"]["send_result"] is False
    assert metadata["_private_qqcc_continuation"] == {
        "version": 1,
        "chain_id": "chain-1",
        "stage_index": 0,
        "submission_sequence": 0,
        "registry_task_id": "registry-1",
        "executor_token": "executor-1",
    }


@pytest.mark.asyncio
async def test_private_bot_submission_is_fenced_and_idempotent(monkeypatch):
    from src.services import private_qqcc_bot_runtime

    events = []

    @asynccontextmanager
    async def admission_lock(private_bot_id):
        events.append(("lock", private_bot_id))
        try:
            yield
        finally:
            events.append(("unlock", private_bot_id))

    async def accepts(private_bot_id):
        events.append(("check", private_bot_id))
        return True

    async def process_submit(**kwargs):
        events.append(("submit", kwargs["task_id"]))
        assert kwargs["submission_prepare_timeout_seconds"] == (
            task_service_flow.private_bot_submission_ledger.PRIVATE_BOT_PREPARATION_HARD_DEADLINE_SECONDS
        )
        await kwargs["submission_before_debit_func"](cost=6)
        await kwargs["submission_after_debit_func"](
            cost=6,
            credits_deducted=True,
        )
        assert kwargs["submission_should_compensate_func"](RuntimeError()) is True
        await kwargs["submission_before_dispatch_func"](
            registry_task_id=kwargs["task_id"],
            task_type="quick_image",
            cost=6,
            saved_inputs=["saved.png"],
        )
        assert kwargs["submission_should_compensate_func"](RuntimeError()) is False
        assert kwargs["submission_refund_idempotency_key"] == (
            f"task_refund:task:{kwargs['task_id']}"
        )
        assert kwargs["submission_refund_task_type"] == (
            "refund_private_submission"
        )
        assert kwargs["submission_concurrency_idempotency_key"] == (
            f"task_concurrency:{kwargs['task_id']}"
        )
        assert kwargs["submission_release_idempotency_key"] == (
            f"task_concurrency:{kwargs['task_id']}"
        )
        return {
            "cost": 6,
            "registry_task_id": kwargs["task_id"],
            "backend_task_id": kwargs["task_id"],
            "saved_inputs": ["saved.png"],
        }

    monkeypatch.setattr(private_qqcc_bot_runtime, "private_bot_admission_lock", admission_lock)
    monkeypatch.setattr(private_qqcc_bot_runtime, "private_bot_accepts_new_tasks", accepts)
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    expected_key = "private_bot_update:17:901:0"
    expected_task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, expected_key))
    ledger_request = SimpleNamespace(registry_task_id=expected_task_id)
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "build_private_bot_submission_request",
        Mock(return_value=ledger_request),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "reserve_private_bot_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                status="reserved",
            )
        ),
    )
    mark_dispatching = AsyncMock()
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "mark_private_bot_submission_dispatching",
        mark_dispatching,
    )
    record_cost = AsyncMock()
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "record_private_bot_submission_cost",
        record_cost,
    )
    mark_submitted = AsyncMock()
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "mark_private_bot_submission_submitted",
        mark_submitted,
    )
    claim_owner = AsyncMock(
        side_effect=lambda **_kwargs: events.append(("owner", 17))
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "claim_private_bot_submission_owner",
        claim_owner,
    )

    runtime_state = SimpleNamespace(
        task_submitted=False,
        actual_cost=0,
        registry_task_id=None,
        backend_task_id=None,
    )
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=17, update_id=901)
    with activate_private_bot_update_scope(scope):
        task_id, backend_task_id, _ = await task_service_flow.submit_bot_task(
            submission=BotTaskSubmissionContext(
                runtime_state=runtime_state,
                internal_user_id=456,
                username="visitor",
                task_type="quick_image",
                inputs={"prompt": "hello"},
                client_type="bot:qqcc-private:17",
            )
        )

    assert task_id == expected_task_id
    assert backend_task_id == expected_task_id
    assert events == [
        ("lock", 17),
        ("check", 17),
        ("owner", 17),
        ("submit", task_id),
        ("unlock", 17),
    ]
    assert runtime_state.task_submitted is True
    claim_owner.assert_awaited_once_with(
        request=ledger_request,
        owner_token=ANY,
        owner_deadline_at=ANY,
        reconcile_not_before_at=ANY,
    )
    mark_dispatching.assert_awaited_once_with(
        request=ledger_request,
        registry_task_id=expected_task_id,
        actual_cost=6,
        saved_inputs=["saved.png"],
        owner_token=ANY,
        owner_deadline_at=ANY,
        reconcile_not_before_at=ANY,
    )
    assert record_cost.await_count == 2
    for awaited in record_cost.await_args_list:
        assert awaited.kwargs == {
            "request": ledger_request,
            "actual_cost": 6,
            "owner_token": ANY,
            "owner_deadline_at": ANY,
            "reconcile_not_before_at": ANY,
        }
    mark_submitted.assert_awaited_once()


@pytest.mark.asyncio
async def test_durable_private_submission_replay_signals_upstream_to_skip_second_monitor(
    monkeypatch,
):
    from src.services import private_qqcc_bot_runtime
    from src.services.private_bot_submission_ledger import (
        PrivateBotSubmissionReplayHandled,
    )

    @asynccontextmanager
    async def admission_lock(_private_bot_id):
        yield

    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_admission_lock",
        admission_lock,
    )
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_accepts_new_tasks",
        AsyncMock(return_value=True),
    )
    process_submit = AsyncMock()
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    task_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "private_bot_update:17:901:0")
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "build_private_bot_submission_request",
        Mock(return_value=SimpleNamespace(registry_task_id=task_id)),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "reserve_private_bot_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                status="submitted",
                registry_task_id=task_id,
            )
        ),
    )

    scope = PrivateBotUpdateAdmissionScope(private_bot_id=17, update_id=901)
    with activate_private_bot_update_scope(scope):
        with pytest.raises(PrivateBotSubmissionReplayHandled) as exc_info:
            await task_service_flow.submit_bot_task(
                submission=BotTaskSubmissionContext(
                    runtime_state=SimpleNamespace(
                        task_submitted=False,
                        actual_cost=0,
                        registry_task_id=None,
                        backend_task_id=None,
                    ),
                    internal_user_id=456,
                    username="visitor",
                    task_type="quick_image",
                    inputs={"prompt": "hello"},
                    client_type="bot:qqcc-private:17",
                )
            )

    assert exc_info.value.registry_task_id == task_id
    process_submit.assert_not_awaited()

    monitor = AsyncMock()
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_submission_stage",
        AsyncMock(side_effect=exc_info.value),
    )
    monkeypatch.setattr(task_service_flow, "run_monitored_task_lifecycle", monitor)
    flow = SimpleNamespace(
        request=SimpleNamespace(
            context=object(),
            update=None,
            chat_id=1,
            status_msg_id=None,
        ),
        presentation=SimpleNamespace(
            allow_cancel=True,
            message_spec=BotTaskMessageSpec(initial_status_text="处理中"),
            submitted_status_builder=None,
        ),
        billing=SimpleNamespace(),
    )
    with pytest.raises(PrivateBotSubmissionReplayHandled):
        await task_service_flow.execute_bot_task_stages(
            flow=flow,
            execution=SimpleNamespace(),
            submission=object(),
        )
    monitor.assert_not_awaited()


@pytest.mark.asyncio
async def test_accepted_continuation_bypasses_pause_gate_but_requires_tenant(
    monkeypatch,
):
    from src.services import private_qqcc_bot_runtime
    from src.services.private_bot_submission_ledger import (
        PrivateBotSubmissionReplayHandled,
    )

    @asynccontextmanager
    async def admission_lock(_private_bot_id):
        yield

    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_admission_lock",
        admission_lock,
    )
    accepts_new = AsyncMock(return_value=False)
    tenant_exists = AsyncMock(return_value=True)
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_accepts_new_tasks",
        accepts_new,
    )
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_exists_for_continuation",
        tenant_exists,
    )
    task_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "private_bot_update:17:901:0")
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "build_private_bot_submission_request",
        Mock(return_value=SimpleNamespace(registry_task_id=task_id)),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "reserve_private_bot_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                status="submitted",
                registry_task_id=task_id,
            )
        ),
    )
    recovery_metadata = {
        "_private_qqcc_continuation": {
            "version": 1,
            "chain_id": "chain-1",
            "stage_index": 0,
            "submission_sequence": 0,
            "registry_task_id": task_id,
            "executor_token": "executor-1",
        }
    }
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=17, update_id=901)
    with activate_private_bot_update_scope(scope):
        with pytest.raises(PrivateBotSubmissionReplayHandled):
            await task_service_flow.submit_bot_task(
                submission=BotTaskSubmissionContext(
                    runtime_state=SimpleNamespace(
                        task_submitted=False,
                        actual_cost=0,
                        registry_task_id=None,
                        backend_task_id=None,
                    ),
                    internal_user_id=456,
                    username="visitor",
                    task_type="quick_image",
                    inputs={"prompt": "hello"},
                    client_type="bot:qqcc-private:17",
                    recovery_metadata=recovery_metadata,
                )
            )

    tenant_exists.assert_awaited_once_with(17)
    accepts_new.assert_not_awaited()


@pytest.mark.asyncio
async def test_accepted_continuation_stops_after_permanent_unlink(monkeypatch):
    from src.services import private_qqcc_bot_runtime

    @asynccontextmanager
    async def admission_lock(_private_bot_id):
        yield

    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_admission_lock",
        admission_lock,
    )
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_exists_for_continuation",
        AsyncMock(return_value=False),
    )
    accepts_new = AsyncMock(return_value=True)
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_accepts_new_tasks",
        accepts_new,
    )
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=17, update_id=902)
    with activate_private_bot_update_scope(scope):
        with pytest.raises(task_service_flow.CoreDomainError, match="永久解绑"):
            await task_service_flow.submit_bot_task(
                submission=BotTaskSubmissionContext(
                    runtime_state=SimpleNamespace(
                        task_submitted=False,
                        actual_cost=0,
                        registry_task_id=None,
                        backend_task_id=None,
                    ),
                    internal_user_id=456,
                    username="visitor",
                    task_type="quick_image",
                    inputs={"prompt": "hello"},
                    client_type="bot:qqcc-private:17",
                    recovery_metadata={
                        "_private_qqcc_continuation": {
                            "version": 1,
                            "chain_id": "chain-1",
                            "stage_index": 1,
                            "submission_sequence": 1,
                            "registry_task_id": "registry-1",
                            "executor_token": "executor-1",
                        }
                    },
                )
            )

    accepts_new.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_ledger_replay_only_rechecks_idempotent_refund_and_never_dispatches(
    monkeypatch,
):
    from src.services import private_qqcc_bot_runtime
    from src.services.private_bot_submission_ledger import (
        PrivateBotSubmissionReplayHandled,
    )

    @asynccontextmanager
    async def admission_lock(_private_bot_id):
        yield

    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_admission_lock",
        admission_lock,
    )
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_accepts_new_tasks",
        AsyncMock(return_value=True),
    )
    process_submit = AsyncMock()
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    task_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "private_bot_update:17:901:0")
    )
    ledger_request = SimpleNamespace(
        registry_task_id=task_id,
        deduct_quota=True,
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "build_private_bot_submission_request",
        Mock(return_value=ledger_request),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "reserve_private_bot_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                status="failed",
                registry_task_id=task_id,
                actual_cost=6,
            )
        ),
    )
    refund = AsyncMock(return_value=False)
    monkeypatch.setattr(task_service_flow, "refund_credits", refund)
    cleanup = AsyncMock()
    monkeypatch.setattr(task_service_flow, "cleanup_task_runtime_state", cleanup)
    claim = AsyncMock(return_value="compensation-lease")
    complete = AsyncMock()
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "claim_private_bot_submission_compensation",
        claim,
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "complete_private_bot_submission_compensation",
        complete,
    )

    scope = PrivateBotUpdateAdmissionScope(private_bot_id=17, update_id=901)
    with activate_private_bot_update_scope(scope):
        with pytest.raises(PrivateBotSubmissionReplayHandled):
            await task_service_flow.submit_bot_task(
                submission=BotTaskSubmissionContext(
                    runtime_state=SimpleNamespace(
                        task_submitted=False,
                        actual_cost=0,
                        registry_task_id=None,
                        backend_task_id=None,
                    ),
                    internal_user_id=456,
                    username="visitor",
                    task_type="quick_image",
                    inputs={"prompt": "hello"},
                    client_type="bot:qqcc-private:17",
                )
            )

    process_submit.assert_not_awaited()
    refund.assert_awaited_once_with(
        456,
        6,
        task_type="refund_private_submission",
        username="visitor",
        idempotency_key=f"task_refund:task:{task_id}",
    )
    cleanup.assert_awaited_once_with(
        internal_user_id=456,
        registry_task_id=task_id,
        release_lock=True,
        release_idempotency_key=f"task_concurrency:{task_id}",
        raise_on_error=True,
    )
    complete.assert_awaited_once_with(
        request=ledger_request,
        lease_token="compensation-lease",
    )


@pytest.mark.asyncio
async def test_definitively_missing_dispatch_is_failed_refunded_and_cleaned(monkeypatch):
    from src.services import private_qqcc_bot_runtime
    from src.services.private_bot_submission_ledger import (
        PrivateBotSubmissionReplayHandled,
    )

    @asynccontextmanager
    async def admission_lock(_private_bot_id):
        yield

    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_admission_lock",
        admission_lock,
    )
    monkeypatch.setattr(
        private_qqcc_bot_runtime,
        "private_bot_accepts_new_tasks",
        AsyncMock(return_value=True),
    )
    process_submit = AsyncMock()
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)
    task_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "private_bot_update:17:901:0")
    )
    ledger_request = SimpleNamespace(
        registry_task_id=task_id,
        deduct_quota=True,
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "build_private_bot_submission_request",
        Mock(return_value=ledger_request),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "reserve_private_bot_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                status="dispatching",
                registry_task_id=task_id,
                actual_cost=6,
                saved_inputs=("saved.png",),
            )
        ),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "reconcile_private_bot_dispatching_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                confirmed=False,
                definitively_missing=True,
                backend_task_id=None,
            )
        ),
    )
    mark_failed = AsyncMock(
        return_value=SimpleNamespace(
            status="failed",
            registry_task_id=task_id,
            actual_cost=6,
        )
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "mark_private_bot_submission_failed",
        mark_failed,
    )
    refund = AsyncMock(return_value=True)
    cleanup = AsyncMock()
    monkeypatch.setattr(task_service_flow, "refund_credits", refund)
    monkeypatch.setattr(task_service_flow, "cleanup_task_runtime_state", cleanup)
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "claim_private_bot_submission_compensation",
        AsyncMock(return_value="compensation-lease"),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "complete_private_bot_submission_compensation",
        AsyncMock(),
    )

    scope = PrivateBotUpdateAdmissionScope(private_bot_id=17, update_id=901)
    with activate_private_bot_update_scope(scope):
        with pytest.raises(PrivateBotSubmissionReplayHandled):
            await task_service_flow.submit_bot_task(
                submission=BotTaskSubmissionContext(
                    runtime_state=SimpleNamespace(
                        task_submitted=False,
                        actual_cost=0,
                        registry_task_id=None,
                        backend_task_id=None,
                    ),
                    internal_user_id=456,
                    username="visitor",
                    task_type="quick_image",
                    inputs={"prompt": "hello"},
                    client_type="bot:qqcc-private:17",
                )
            )

    process_submit.assert_not_awaited()
    mark_failed.assert_awaited_once_with(
        request=ledger_request,
        actual_cost=6,
        error_code="dispatch_not_found",
        error_message="Central confirmed that the deterministic dispatch is absent.",
    )
    refund.assert_awaited_once_with(
        456,
        6,
        task_type="refund_private_submission",
        username="visitor",
        idempotency_key=f"task_refund:task:{task_id}",
    )
    cleanup.assert_awaited_once_with(
        internal_user_id=456,
        registry_task_id=task_id,
        release_lock=True,
        release_idempotency_key=f"task_concurrency:{task_id}",
        raise_on_error=True,
    )


@pytest.mark.asyncio
async def test_failed_compensation_cas_prevents_replay_from_releasing_another_task(
    monkeypatch,
):
    ledger_request = SimpleNamespace(deduct_quota=True)
    submission = SimpleNamespace(internal_user_id=456, username="visitor")
    claim = AsyncMock(side_effect=["lease-token", None])
    refund = AsyncMock(return_value=True)
    cleanup = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "claim_private_bot_submission_compensation",
        claim,
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "complete_private_bot_submission_compensation",
        complete,
    )
    monkeypatch.setattr(task_service_flow, "refund_credits", refund)
    monkeypatch.setattr(task_service_flow, "cleanup_task_runtime_state", cleanup)

    first = await task_service_flow.compensate_failed_private_bot_submission(
        submission=submission,
        ledger_request=ledger_request,
        actual_cost=6,
        registry_task_id="task-a",
    )
    replay = await task_service_flow.compensate_failed_private_bot_submission(
        submission=submission,
        ledger_request=ledger_request,
        actual_cost=6,
        registry_task_id="task-a",
    )

    assert first is True
    assert replay is False
    refund.assert_awaited_once()
    cleanup.assert_awaited_once_with(
        internal_user_id=456,
        registry_task_id="task-a",
        release_lock=True,
        release_idempotency_key="task_concurrency:task-a",
        raise_on_error=True,
    )
    complete.assert_awaited_once_with(
        request=ledger_request,
        lease_token="lease-token",
    )


@pytest.mark.asyncio
async def test_late_confirmed_debit_refunds_even_after_sweep_completed_compensation(
    monkeypatch,
):
    ledger_request = SimpleNamespace(deduct_quota=True)
    submission = SimpleNamespace(internal_user_id=456, username="visitor")
    refund = AsyncMock(return_value=True)
    cleanup = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "claim_private_bot_submission_compensation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        task_service_flow.private_bot_submission_ledger,
        "complete_private_bot_submission_compensation",
        complete,
    )
    monkeypatch.setattr(task_service_flow, "refund_credits", refund)
    monkeypatch.setattr(task_service_flow, "cleanup_task_runtime_state", cleanup)

    completed = await task_service_flow.compensate_failed_private_bot_submission(
        submission=submission,
        ledger_request=ledger_request,
        actual_cost=6,
        registry_task_id="late-debit-task",
        debit_confirmed=True,
    )

    assert completed is True
    refund.assert_awaited_once_with(
        456,
        6,
        task_type="refund_private_submission",
        username="visitor",
        idempotency_key="task_refund:task:late-debit-task",
    )
    cleanup.assert_awaited_once_with(
        internal_user_id=456,
        registry_task_id="late-debit-task",
        release_lock=True,
        release_idempotency_key="task_concurrency:late-debit-task",
        raise_on_error=True,
    )
    complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_bot_task_passes_priority_and_user_cancel_lock(monkeypatch):
    process_submit = AsyncMock(
        return_value={
            "cost": 6,
            "registry_task_id": "registry-locked",
            "backend_task_id": "backend-locked",
            "saved_inputs": [],
        }
    )
    monkeypatch.setattr(task_service_flow, "process_and_submit_task", process_submit)

    await task_service_flow.submit_bot_task(
        submission=BotTaskSubmissionContext(
            runtime_state=SimpleNamespace(
                task_submitted=False,
                actual_cost=0,
                registry_task_id=None,
                backend_task_id=None,
            ),
            internal_user_id=789,
            username="qqcc",
            task_type="quick_image",
            inputs={"prompt": "lazy"},
            base_priority=100,
            user_cancel_allowed=False,
        ),
    )

    assert process_submit.await_args.kwargs["base_priority"] == 100
    assert process_submit.await_args.kwargs["user_cancel_allowed"] is False


@pytest.mark.asyncio
async def test_send_initial_task_status_uses_reply_text_when_update_present(monkeypatch):
    reply_text = AsyncMock(return_value="sent")
    monkeypatch.setattr(task_service_flow, "robust_reply_text", reply_text)

    update = SimpleNamespace(effective_message=object())
    spec = BotTaskMessageSpec(initial_status_text="正在提交")

    result = await task_service_flow.send_initial_task_status(
        context=object(),
        update=update,
        chat_id=123,
        status_msg_id=None,
        message_spec=spec,
    )

    assert result == "sent"
    reply_text.assert_awaited_once_with(update.effective_message, "正在提交")


@pytest.mark.asyncio
async def test_update_submitted_task_status_prefers_submitted_text(monkeypatch):
    edit_text = AsyncMock()
    monkeypatch.setattr(task_service_flow, "robust_edit_text", edit_text)
    cancel_markup = object()
    build_cancel_markup = Mock(return_value=cancel_markup)
    monkeypatch.setattr(
        task_service_flow,
        "build_cancel_task_markup",
        build_cancel_markup,
    )

    status_msg = object()
    spec = BotTaskMessageSpec(
        initial_status_text="正在提交",
        submitted_status_text="已提交",
        progress_wait_text="请稍候",
    )

    await task_service_flow.update_submitted_task_status(
        status_msg=status_msg,
        message_spec=spec,
        registry_task_id="registry-1",
    )

    build_cancel_markup.assert_called_once_with("registry-1")
    edit_text.assert_awaited_once_with(
        status_msg,
        "已提交",
        reply_markup=cancel_markup,
    )


@pytest.mark.asyncio
async def test_update_submitted_task_status_skips_cancel_markup_when_disallowed(
    monkeypatch,
):
    edit_text = AsyncMock()
    build_cancel_markup = Mock()
    monkeypatch.setattr(task_service_flow, "robust_edit_text", edit_text)
    monkeypatch.setattr(
        task_service_flow,
        "build_cancel_task_markup",
        build_cancel_markup,
    )

    await task_service_flow.update_submitted_task_status(
        status_msg="status-msg",
        message_spec=BotTaskMessageSpec(
            initial_status_text="正在提交",
            submitted_status_text="已提交",
        ),
        registry_task_id="registry-locked",
        allow_cancel=False,
    )

    build_cancel_markup.assert_not_called()
    edit_text.assert_awaited_once_with(
        "status-msg",
        "已提交",
        reply_markup=None,
    )


@pytest.mark.asyncio
async def test_prepare_and_submit_bot_task_updates_status_through_helpers(monkeypatch):
    send_initial = AsyncMock(return_value="status-msg")
    submit_bot_task = AsyncMock(return_value=("registry-1", "backend-1", ["input.png"]))
    update_submitted = AsyncMock()
    runtime_state = SimpleNamespace(actual_cost=18)
    spec = BotTaskMessageSpec(
        initial_status_text="正在提交",
        submitted_status_text="已提交",
        progress_wait_text="请稍候",
    )

    monkeypatch.setattr(task_service_flow, "send_initial_task_status", send_initial)
    monkeypatch.setattr(task_service_flow, "submit_bot_task", submit_bot_task)
    monkeypatch.setattr(
        task_service_flow,
        "update_submitted_task_status",
        update_submitted,
    )

    status_msg, registry_task_id, backend_task_id, saved_inputs, returned_spec = (
        await task_service_flow.prepare_and_submit_bot_task(
            context=object(),
            update=None,
            chat_id=123,
            message_spec=spec,
            submission=BotTaskSubmissionContext(
                runtime_state=runtime_state,
                internal_user_id=456,
                username="tester",
                task_type="image",
                inputs={"prompt": "hello"},
            ),
        )
    )

    assert status_msg == "status-msg"
    assert registry_task_id == "registry-1"
    assert backend_task_id == "backend-1"
    assert saved_inputs == ["input.png"]
    assert returned_spec is spec
    send_initial.assert_awaited_once()
    submit_bot_task.assert_awaited_once_with(
        submission=BotTaskSubmissionContext(
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            task_type="image",
            inputs={"prompt": "hello"},
        ),
        delivery_context={"chat_id": 123},
    )
    update_submitted.assert_awaited_once_with(
        status_msg="status-msg",
        message_spec=spec,
        registry_task_id="registry-1",
        allow_cancel=True,
    )


@pytest.mark.asyncio
async def test_prepare_and_submit_bot_task_persists_status_message_delivery_context(
    monkeypatch,
):
    send_initial = AsyncMock(return_value=SimpleNamespace(message_id=77))
    submit_bot_task = AsyncMock(return_value=("registry-1", "backend-1", []))
    update_submitted = AsyncMock()
    runtime_state = SimpleNamespace(actual_cost=2)
    spec = BotTaskMessageSpec(initial_status_text="正在提交")

    monkeypatch.setattr(task_service_flow, "send_initial_task_status", send_initial)
    monkeypatch.setattr(task_service_flow, "submit_bot_task", submit_bot_task)
    monkeypatch.setattr(
        task_service_flow,
        "update_submitted_task_status",
        update_submitted,
    )

    await task_service_flow.prepare_and_submit_bot_task(
        context=object(),
        update=None,
        chat_id=123,
        message_spec=spec,
        submission=BotTaskSubmissionContext(
            runtime_state=runtime_state,
            internal_user_id=456,
            username="tester",
            task_type="image",
            inputs={"prompt": "hello"},
        ),
    )

    assert submit_bot_task.await_args.kwargs["delivery_context"] == {
        "chat_id": 123,
        "message_id": 77,
    }


@pytest.mark.asyncio
async def test_run_bot_task_application_monitors_with_backend_task_id_and_completes_with_split_ids(
    monkeypatch,
):
    submission_stage = AsyncMock(
        return_value=(
            "status-msg",
            "registry-123",
            "backend-456",
            ["input.png"],
            BotTaskMessageSpec(initial_status_text="提交中"),
        )
    )
    monitor_stage = AsyncMock(return_value={"status": "done"})
    completion_stage = AsyncMock(return_value=(b"media", "output.png"))

    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_submission_stage",
        submission_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_monitor_stage",
        monitor_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_completion_stage",
        completion_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "cleanup_bot_task_flow",
        AsyncMock(),
    )

    flow = SimpleNamespace(
        runtime_state=SimpleNamespace(
            registry_task_id="registry-123",
            backend_task_id="backend-456",
            task_submitted=True,
            actual_cost=0,
            terminal_state_finalized=False,
        ),
        request=SimpleNamespace(
            context=SimpleNamespace(),
            update=None,
            chat_id=100,
            status_msg_id=None,
            internal_user_id=200,
            username="tester",
            task_type="txt2img",
            inputs={"prompt": "hello"},
            prompt="hello",
            is_video=False,
            source_post_id=None,
            deduct_quota=True,
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="提交中"),
            submitted_status_builder=None,
            send_result=True,
            reply_markup=None,
            result_meta=None,
            delete_status=True,
            allow_contribute=True,
            prefer_edit_status=False,
        ),
        billing=SimpleNamespace(
            billing_resolution=None,
            requested_duration=None,
            missing_output_should_refund=True,
        ),
        failure_policy=SimpleNamespace(
            unexpected_error_log_message="err {error}",
            unexpected_error_prefix="出错了",
            refund_suffix_mode="if_refunded",
            unexpected_should_refund=None,
        ),
        cleanup_policy=SimpleNamespace(
            cleanup_paths=[],
            cleanup_enabled=False,
            cleanup_files_func=lambda *_args, **_kwargs: None,
        ),
    )

    result = await task_service_flow.run_bot_task_application(flow=flow)

    assert result == (b"media", "output.png")
    monitor_stage.assert_awaited_once()
    assert monitor_stage.await_args.kwargs["backend_task_id"] == "backend-456"
    completion_stage.assert_awaited_once()
    assert completion_stage.await_args.kwargs["registry_task_id"] == "registry-123"
    assert completion_stage.await_args.kwargs["backend_task_id"] == "backend-456"


@pytest.mark.asyncio
async def test_run_bot_task_application_reads_client_type_from_bot_data(monkeypatch):
    submission_stage = AsyncMock(
        return_value=(
            "status-msg",
            "registry-qqcc",
            "backend-qqcc",
            [],
            BotTaskMessageSpec(initial_status_text="提交中"),
        )
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_submission_stage",
        submission_stage,
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_monitor_stage",
        AsyncMock(return_value={"status": "done"}),
    )
    monkeypatch.setattr(
        task_service_flow,
        "run_bot_task_completion_stage",
        AsyncMock(return_value=(b"media", "output.png")),
    )
    monkeypatch.setattr(task_service_flow, "cleanup_bot_task_flow", AsyncMock())

    flow = SimpleNamespace(
        runtime_state=SimpleNamespace(
            registry_task_id=None,
            backend_task_id=None,
            task_submitted=False,
            actual_cost=0,
            terminal_state_finalized=False,
        ),
        request=SimpleNamespace(
            context=SimpleNamespace(bot_data={"bot_client_type": "bot:qqcc"}),
            update=None,
            chat_id=100,
            status_msg_id=None,
            internal_user_id=200,
            username="tester",
            task_type="quick_image",
            inputs={"prompt": "hello"},
            prompt="hello",
            is_video=False,
            source_post_id=None,
            deduct_quota=True,
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="提交中"),
            submitted_status_builder=None,
            send_result=True,
            reply_markup=None,
            result_meta=None,
            delete_status=True,
            allow_contribute=True,
            prefer_edit_status=False,
        ),
        billing=SimpleNamespace(
            billing_resolution=None,
            requested_duration=None,
            missing_output_should_refund=True,
        ),
        failure_policy=SimpleNamespace(
            unexpected_error_log_message="err {error}",
            unexpected_error_prefix="出错了",
            refund_suffix_mode="if_refunded",
            unexpected_should_refund=None,
        ),
        cleanup_policy=SimpleNamespace(
            cleanup_paths=[],
            cleanup_enabled=False,
            cleanup_files_func=lambda *_args, **_kwargs: None,
        ),
    )

    await task_service_flow.run_bot_task_application(flow=flow)

    submission = submission_stage.await_args.kwargs["submission"]
    assert submission.client_type == "bot:qqcc"


def _private_continuation_flow():
    return SimpleNamespace(
        runtime_state=SimpleNamespace(
            registry_task_id="registry-stage",
            backend_task_id="registry-stage",
            task_submitted=True,
            actual_cost=2,
            terminal_state_finalized=False,
        ),
        request=SimpleNamespace(
            context=SimpleNamespace(
                lang="zh",
                bot_data={"bot_client_type": "bot:qqcc-private:7"},
            ),
            update=None,
            chat_id=100,
            status_msg_id=200,
            internal_user_id=300,
            username="visitor",
            task_type="edit",
            inputs={"prompt": "hidden"},
            prompt="hidden",
            is_video=False,
            source_post_id=None,
            deduct_quota=True,
            cost_override=None,
            base_priority=0,
            user_cancel_allowed=True,
        ),
        presentation=SimpleNamespace(
            message_spec=BotTaskMessageSpec(initial_status_text="处理中"),
            submitted_status_builder=None,
            send_result=False,
            reply_markup=None,
            result_meta=None,
            delete_status=False,
            allow_contribute=False,
            prefer_edit_status=False,
            result_task_type=None,
            result_prompt=None,
            result_input_image_indices=None,
        ),
        billing=SimpleNamespace(
            billing_resolution=None,
            requested_duration=None,
            missing_output_should_refund=True,
        ),
        failure_policy=SimpleNamespace(
            unexpected_error_log_message="err {error}",
            unexpected_error_prefix="出错了",
            refund_suffix_mode="if_refunded",
            unexpected_should_refund=None,
        ),
        cleanup_policy=SimpleNamespace(
            cleanup_paths=["/tmp/input.png"],
            cleanup_enabled=True,
            cleanup_files_func=Mock(),
        ),
    )


@pytest.mark.asyncio
async def test_checkpoint_outage_inside_completion_preserves_paid_runtime(monkeypatch):
    flow = _private_continuation_flow()

    async def checkpoint_outage(*, execution, **_kwargs):
        execution.registry_task_id = "registry-stage"
        execution.saved_inputs = ["inputs/original.png"]
        flow.runtime_state.task_submitted = True
        raise PrivateQqccContinuationUnavailable("redis unavailable")

    cleanup = AsyncMock()
    monkeypatch.setattr(
        task_service_flow,
        "execute_bot_task_stages",
        checkpoint_outage,
    )
    monkeypatch.setattr(task_service_flow, "cleanup_bot_task_flow", cleanup)

    with pytest.raises(PrivateQqccContinuationUnavailable):
        await task_service_flow.run_bot_task_application(flow=flow)

    cleanup.assert_awaited_once()
    assert cleanup.await_args.kwargs["cleanup_runtime_enabled"] is False


@pytest.mark.asyncio
async def test_private_monitor_shutdown_preserves_paid_registry_state(monkeypatch):
    flow = _private_continuation_flow()

    async def cancelled_after_submission(*, execution, **_kwargs):
        execution.registry_task_id = "registry-stage"
        flow.runtime_state.task_submitted = True
        raise asyncio.CancelledError

    cleanup = AsyncMock()
    monkeypatch.setattr(
        task_service_flow,
        "execute_bot_task_stages",
        cancelled_after_submission,
    )
    monkeypatch.setattr(task_service_flow, "cleanup_bot_task_flow", cleanup)

    with pytest.raises(asyncio.CancelledError):
        await task_service_flow.run_bot_task_application(flow=flow)

    cleanup.assert_awaited_once()
    assert cleanup.await_args.kwargs["cleanup_runtime_enabled"] is False
