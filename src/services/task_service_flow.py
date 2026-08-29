import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from asgi_correlation_id import correlation_id

from src.core.billing_core import get_user_priority_and_identity, refund_credits
from src.core.task_application import TaskApplication
from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
)
from src.core.task_core_types import (
    SubmissionJournal,
    TaskSubmissionCommand,
    TaskSubmissionPolicy,
)
from src.core.task_core_runtime import cleanup_task_runtime_state
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services import task_service_completion as task_service_completion_helpers
from src.services import task_service_finalize as task_service_finalize_helpers
from src.services.task_service_message_support import (
    resolve_context_lang,
    with_submitted_status,
)
from src.services.task_service_types import (
    BotTaskCancelled,
    BotTaskCompletionContext,
    BotTaskFlowContext,
    BotTaskMessageSpec,
    BotTaskSubmissionContext,
)
from src.services.tg_task_runtime import (
    get_or_send_status_message,
    build_cancel_task_markup,
)
from src.services.tg_task_progress_presentation import build_running_status_text
from src.services.task_lifecycle_runner import run_monitored_task_lifecycle
from src.services.private_bot_update_admission import (
    mark_private_bot_task_durable,
    next_private_bot_submission_key,
)
from src.services.private_qqcc_bot_service import parse_private_bot_client_type
from src.services import private_bot_submission_ledger
from src.services.private_bot_submission_journal import PrivateBotSubmissionJournal
from src.services.task_registry import TaskRegistry
from src.services.task_recovery_contract import build_bot_task_recovery_contract
from src.services.minimax_h3_history_context_service import (
    merge_minimax_h3_input_assets_into_metadata,
)
from src.services.task_bot_submission_journal import BotRecoverySubmissionJournal
from src.task_application_runtime import get_task_application
from src.services.private_bot_task_monitor_lease import (
    PrivateBotTaskMonitorLeaseError,
)
from src.services.private_qqcc_continuation_service import (
    PrivateQqccContinuationError,
    build_private_qqcc_continuation_registry_metadata,
    normalize_private_qqcc_continuation_task_ref,
)
from src.utils import robust_edit_text, robust_reply_text


@dataclass
class _BotTaskExecutionState:
    status_msg: object | None = None
    registry_task_id: str | None = None
    backend_task_id: str | None = None
    saved_inputs: list[str] | None = None
    message_spec: BotTaskMessageSpec | None = None
    preserve_runtime_state: bool = False
    monitor_lease_stack: contextlib.AsyncExitStack | None = None


def mark_task_submission_succeeded(runtime_state, result: dict) -> list[str]:
    runtime_state.task_submitted = True
    runtime_state.actual_cost = result["cost"]
    runtime_state.registry_task_id = result["registry_task_id"]
    runtime_state.backend_task_id = (
        result.get("backend_task_id") or result["registry_task_id"]
    )
    return result["saved_inputs"]


def build_bot_delivery_context(*, chat_id, status_msg) -> dict:
    delivery_context = {"chat_id": chat_id}
    message_id = getattr(status_msg, "message_id", None)
    if message_id is not None:
        delivery_context["message_id"] = message_id
    return delivery_context


async def compensate_failed_private_bot_submission(
    *,
    submission: BotTaskSubmissionContext,
    ledger_request,
    actual_cost: int,
    registry_task_id: str,
    debit_confirmed: bool = False,
) -> bool:
    """Lease and replay failed-submission effects through idempotent seams."""

    lease_error: Exception | None = None
    try:
        lease_token = await (
            private_bot_submission_ledger.claim_private_bot_submission_compensation(
                request=ledger_request,
            )
        )
    except Exception as exc:
        lease_token = None
        lease_error = exc
    if lease_token is None and not debit_confirmed:
        if lease_error is not None:
            raise lease_error
        return False

    try:
        if (
            ledger_request.deduct_quota
            and actual_cost
            and (debit_confirmed or lease_token is not None)
        ):
            await refund_credits(
                submission.internal_user_id,
                int(actual_cost),
                task_type="refund_private_submission",
                username=submission.username,
                idempotency_key=(
                    private_bot_submission_ledger.private_bot_submission_refund_idempotency_key(
                        registry_task_id
                    )
                ),
            )
        await cleanup_task_runtime_state(
            internal_user_id=submission.internal_user_id,
            registry_task_id=registry_task_id,
            release_lock=True,
            release_idempotency_key=(
                private_bot_submission_ledger.private_bot_submission_release_idempotency_key(
                    registry_task_id
                )
            ),
            raise_on_error=True,
        )
        if lease_token is not None:
            await private_bot_submission_ledger.complete_private_bot_submission_compensation(
                request=ledger_request,
                lease_token=lease_token,
            )
        if lease_error is not None:
            raise lease_error
        return True
    except Exception as exc:
        if lease_token is not None:
            with contextlib.suppress(Exception):
                await private_bot_submission_ledger.record_private_bot_submission_compensation_error(
                    request=ledger_request,
                    lease_token=lease_token,
                    error_message=str(exc),
                )
        raise


async def submit_bot_task(
    *,
    submission: BotTaskSubmissionContext,
    delivery_context: dict | None = None,
    task_application: TaskApplication | None = None,
) -> tuple[str, str, list[str]]:
    private_submission_key = next_private_bot_submission_key()
    task_id = submission.task_id_override or (
        str(uuid.uuid5(uuid.NAMESPACE_URL, private_submission_key))
        if private_submission_key
        else str(uuid.uuid4())
    )
    correlation_id.set(task_id)
    application = task_application or get_task_application()

    async def submit_once(*, journal: SubmissionJournal):
        return await application.submit(
            TaskSubmissionCommand(
                internal_user_id=submission.internal_user_id,
                username=submission.username,
                task_type=submission.task_type,
                inputs=submission.inputs,
                task_id=task_id,
                source_post_id=submission.source_post_id,
                delivery_context=delivery_context,
                registry_metadata=submission.recovery_metadata or None,
            ),
            TaskSubmissionPolicy(
                client_type=submission.client_type,
                deduct_quota=submission.deduct_quota,
                cost_override=submission.cost_override,
                base_priority=submission.base_priority,
                user_cancel_allowed=submission.user_cancel_allowed,
                concurrency_idempotency_key=(
                    private_bot_submission_ledger.private_bot_submission_concurrency_idempotency_key(
                        task_id
                    )
                    if private_submission_key
                    else None
                ),
                debit_idempotency_key=(
                    f"task_debit:{private_submission_key}"
                    if private_submission_key
                    else None
                ),
                prepare_timeout_seconds=(
                    private_bot_submission_ledger.PRIVATE_BOT_PREPARATION_HARD_DEADLINE_SECONDS
                    if private_submission_key
                    else None
                ),
                debit_timeout_seconds=(
                    private_bot_submission_ledger.PRIVATE_BOT_DISPATCH_HARD_DEADLINE_SECONDS
                    if private_submission_key
                    else None
                ),
                dispatch_timeout_seconds=(
                    private_bot_submission_ledger.PRIVATE_BOT_DISPATCH_HARD_DEADLINE_SECONDS
                    if private_submission_key
                    else None
                ),
                refund_idempotency_key=(
                    private_bot_submission_ledger.private_bot_submission_refund_idempotency_key(
                        task_id
                    )
                    if private_submission_key
                    else None
                ),
                refund_task_type=(
                    "refund_private_submission" if private_submission_key else None
                ),
                release_idempotency_key=(
                    private_bot_submission_ledger.private_bot_submission_release_idempotency_key(
                        task_id
                    )
                    if private_submission_key
                    else None
                ),
            ),
            journal,
        )

    private_bot_id = parse_private_bot_client_type(submission.client_type)
    if private_bot_id is None:
        result = await submit_once(
            journal=BotRecoverySubmissionJournal(expected_registry_task_id=task_id)
        )
    else:
        # This lock is shared with pause/disable/unlink. The state recheck and
        # durable task registration therefore form one linearized admission.
        from src.services.private_qqcc_bot_runtime import (
            private_bot_accepts_new_tasks,
            private_bot_admission_lock,
            private_bot_exists_for_continuation,
        )

        async with private_bot_admission_lock(private_bot_id):
            continuation_ref = normalize_private_qqcc_continuation_task_ref(
                submission.recovery_metadata
            )
            if continuation_ref is not None:
                if not await private_bot_exists_for_continuation(private_bot_id):
                    raise CoreDomainError("私有 Bot 已永久解绑，任务链无法继续")
            elif not await private_bot_accepts_new_tasks(private_bot_id):
                raise CoreDomainError("私有 Bot 已暂停、禁用或解绑，请稍后重试")
            if not private_submission_key:
                raise CoreDomainError("私有 Bot 更新缺少持久幂等上下文")
            try:
                ledger_request = (
                    private_bot_submission_ledger.build_private_bot_submission_request(
                        submission_key=private_submission_key,
                        internal_user_id=submission.internal_user_id,
                        client_type=submission.client_type,
                        task_type=submission.task_type,
                        inputs=submission.inputs,
                        source_post_id=submission.source_post_id,
                        deduct_quota=submission.deduct_quota,
                        cost_override=submission.cost_override,
                        base_priority=submission.base_priority,
                        user_cancel_allowed=submission.user_cancel_allowed,
                    )
                )
                ledger_snapshot = await (
                    private_bot_submission_ledger.reserve_private_bot_submission(
                        ledger_request
                    )
                )
            except private_bot_submission_ledger.PrivateBotSubmissionLedgerError as exc:
                raise CoreDomainError(str(exc)) from exc

            if ledger_snapshot.status == "submitted":
                mark_private_bot_task_durable()
                raise private_bot_submission_ledger.PrivateBotSubmissionReplayHandled(
                    ledger_snapshot.registry_task_id
                )
            elif ledger_snapshot.status == "dispatching":
                reconciliation = await private_bot_submission_ledger.reconcile_private_bot_dispatching_submission(
                    ledger_snapshot,
                    registry_lookup=TaskRegistry.get_task_strict,
                    backend_lookup=image_service.get_task_status,
                )
                if (
                    not reconciliation.confirmed
                    and not reconciliation.definitively_missing
                ):
                    raise CoreDomainError(
                        "任务派发状态仍在确认中；为避免重复扣费或派发，本次不会重试提交"
                    )
                if reconciliation.definitively_missing:
                    ledger_snapshot = await private_bot_submission_ledger.mark_private_bot_submission_failed(
                        request=ledger_request,
                        actual_cost=int(ledger_snapshot.actual_cost or 0),
                        error_code="dispatch_not_found",
                        error_message="Central confirmed that the deterministic dispatch is absent.",
                    )
                    await compensate_failed_private_bot_submission(
                        submission=submission,
                        ledger_request=ledger_request,
                        actual_cost=int(ledger_snapshot.actual_cost or 0),
                        registry_task_id=task_id,
                    )
                    mark_private_bot_task_durable()
                    raise private_bot_submission_ledger.PrivateBotSubmissionReplayHandled(
                        ledger_snapshot.registry_task_id
                    )
                result = {
                    "cost": int(ledger_snapshot.actual_cost or 0),
                    "registry_task_id": ledger_snapshot.registry_task_id,
                    "backend_task_id": reconciliation.backend_task_id,
                    "saved_inputs": list(ledger_snapshot.saved_inputs),
                }
                await (
                    private_bot_submission_ledger.mark_private_bot_submission_submitted(
                        request=ledger_request,
                        result=result,
                    )
                )
                mark_private_bot_task_durable()
                raise private_bot_submission_ledger.PrivateBotSubmissionReplayHandled(
                    ledger_snapshot.registry_task_id
                )
            elif ledger_snapshot.status == "failed":
                await compensate_failed_private_bot_submission(
                    submission=submission,
                    ledger_request=ledger_request,
                    actual_cost=int(ledger_snapshot.actual_cost or 0),
                    registry_task_id=task_id,
                )
                mark_private_bot_task_durable()
                raise private_bot_submission_ledger.PrivateBotSubmissionReplayHandled(
                    ledger_snapshot.registry_task_id
                )
            else:
                now = datetime.now()
                if (
                    getattr(ledger_snapshot, "reconcile_not_before_at", None)
                    is not None
                    and ledger_snapshot.reconcile_not_before_at > now
                ):
                    raise CoreDomainError(
                        "任务仍由原派发器处理；为避免重复派发，本次不会重新提交"
                    )
                dispatch_owner_token = uuid.uuid4().hex
                journal = PrivateBotSubmissionJournal(
                    submission=submission,
                    ledger_request=ledger_request,
                    registry_task_id=task_id,
                    owner_token=dispatch_owner_token,
                    compensate_func=compensate_failed_private_bot_submission,
                )
                try:
                    ledger_snapshot = await private_bot_submission_ledger.claim_private_bot_submission_owner(
                        request=ledger_request,
                        owner_token=dispatch_owner_token,
                        owner_deadline_at=journal.owner_deadline_at,
                        reconcile_not_before_at=journal.reconcile_not_before_at,
                    )
                except (
                    private_bot_submission_ledger.PrivateBotSubmissionLedgerError
                ) as exc:
                    raise CoreDomainError(str(exc)) from exc

                try:
                    result = await submit_once(journal=journal)
                except Exception:
                    await journal.compensate_if_requested()
                    raise
                await (
                    private_bot_submission_ledger.mark_private_bot_submission_submitted(
                        request=ledger_request,
                        result=result,
                        owner_token=dispatch_owner_token,
                    )
                )
    mark_private_bot_task_durable()
    saved_inputs = mark_task_submission_succeeded(submission.runtime_state, result)
    backend_task_id = submission.runtime_state.backend_task_id or task_id
    return task_id, backend_task_id, saved_inputs


def build_bot_task_recovery_metadata(*, flow, client_type: str) -> dict:
    """Serialize presentation state needed for safe task recovery."""

    presentation = flow.presentation
    record_history = getattr(presentation, "record_history", True)
    show_queue_status = getattr(presentation, "show_queue_status", True)
    is_private_bot = parse_private_bot_client_type(client_type) is not None
    if (
        not is_private_bot
        and not (client_type == "bot" and not record_history)
        and show_queue_status
    ):
        return {}

    request = flow.request
    message_spec = presentation.message_spec
    metadata = build_bot_task_recovery_contract(
        send_result=getattr(presentation, "send_result", True),
        delete_status=getattr(presentation, "delete_status", True),
        allow_contribute=getattr(presentation, "allow_contribute", True),
        record_history=record_history,
        result_task_type=getattr(presentation, "result_task_type", None),
        result_prompt=getattr(presentation, "result_prompt", None),
        result_input_image_indices=getattr(
            presentation,
            "result_input_image_indices",
            None,
        ),
        result_meta=getattr(presentation, "result_meta", None),
        completion_caption=getattr(message_spec, "completion_caption", None),
        language_code=resolve_context_lang(request.context),
        show_queue_status=show_queue_status,
    )
    if is_private_bot:
        metadata.update(build_private_qqcc_continuation_registry_metadata())
    return metadata


def select_result_saved_inputs(
    saved_inputs: list[str],
    result_input_image_indices: list[int] | None,
) -> list[str]:
    if result_input_image_indices is None:
        return saved_inputs
    selected = [
        saved_inputs[index]
        for index in result_input_image_indices
        if 0 <= index < len(saved_inputs)
    ]
    return selected or saved_inputs


async def send_initial_task_status(
    *,
    context,
    update,
    chat_id,
    status_msg_id,
    message_spec: BotTaskMessageSpec,
    is_video: bool = False,
    show_queue_status: bool = True,
):
    status_text = (
        message_spec.initial_status_text
        if show_queue_status
        else build_running_status_text(
            is_video=is_video,
            progress=0,
            lang=resolve_context_lang(context),
        )
    )
    if update is not None:
        return await robust_reply_text(
            update.effective_message,
            status_text,
        )
    return await get_or_send_status_message(
        context, chat_id, status_msg_id, status_text
    )


async def update_submitted_task_status(
    *,
    status_msg,
    message_spec: BotTaskMessageSpec,
    registry_task_id: Optional[str] = None,
    allow_cancel: bool = True,
    show_queue_status: bool = True,
):
    if not show_queue_status:
        return
    reply_markup = (
        build_cancel_task_markup(registry_task_id)
        if allow_cancel and registry_task_id
        else None
    )
    if message_spec.submitted_status_text:
        await robust_edit_text(
            status_msg,
            message_spec.submitted_status_text,
            reply_markup=reply_markup,
        )
    elif message_spec.progress_wait_text:
        await robust_edit_text(
            status_msg,
            message_spec.progress_wait_text,
            reply_markup=reply_markup,
        )


async def prepare_and_submit_bot_task(
    *,
    context,
    update,
    chat_id,
    status_msg_id=None,
    message_spec: BotTaskMessageSpec,
    submitted_status_builder: Optional[Callable[[int], str]] = None,
    submission: BotTaskSubmissionContext,
    allow_cancel: bool = True,
    is_video: bool = False,
    show_queue_status: bool = True,
):
    status_msg = await send_initial_task_status(
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
        is_video=is_video,
        show_queue_status=show_queue_status,
    )
    try:
        submission_result = await submit_bot_task(
            submission=submission,
            delivery_context=build_bot_delivery_context(
                chat_id=chat_id,
                status_msg=status_msg,
            ),
        )
    except private_bot_submission_ledger.PrivateBotSubmissionReplayHandled:
        delete = getattr(status_msg, "delete", None)
        if callable(delete):
            with contextlib.suppress(Exception):
                await delete()
        raise
    if len(submission_result) == 2:
        registry_task_id, saved_inputs = submission_result
        backend_task_id = registry_task_id
    else:
        registry_task_id, backend_task_id, saved_inputs = submission_result
    if submitted_status_builder is not None:
        message_spec = with_submitted_status(
            message_spec,
            submitted_status_builder(submission.runtime_state.actual_cost),
        )
    await update_submitted_task_status(
        status_msg=status_msg,
        message_spec=message_spec,
        registry_task_id=registry_task_id,
        allow_cancel=allow_cancel,
        show_queue_status=show_queue_status,
    )
    return status_msg, registry_task_id, backend_task_id, saved_inputs, message_spec


async def run_bot_task_submission_stage(
    *,
    context,
    update,
    chat_id,
    status_msg_id,
    message_spec: BotTaskMessageSpec,
    submitted_status_builder: Optional[Callable[[int], str]],
    submission: BotTaskSubmissionContext,
    allow_cancel: bool = True,
    is_video: bool = False,
    show_queue_status: bool = True,
):
    return await prepare_and_submit_bot_task(
        context=context,
        update=update,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        message_spec=message_spec,
        submitted_status_builder=submitted_status_builder,
        submission=submission,
        allow_cancel=allow_cancel,
        is_video=is_video,
        show_queue_status=show_queue_status,
    )


async def run_bot_task_monitor_stage(
    *,
    backend_task_id: str,
    status_msg,
    is_video: bool,
    internal_user_id: int,
    lang: str = "zh",
    allow_cancel: bool = True,
    show_queue_status: bool = True,
):
    return await task_service_completion_helpers.monitor_submitted_bot_task(
        task_id=backend_task_id,
        status_msg=status_msg,
        is_video=is_video,
        internal_user_id=internal_user_id,
        monitor_func=image_service.monitor_progress,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        monitor_bot_task_progress_func=(
            task_service_completion_helpers.monitor_bot_task_progress
        ),
        lang=lang,
        allow_cancel=allow_cancel,
        show_queue_status=show_queue_status,
    )


async def run_bot_task_completion_stage(
    *,
    context,
    chat_id,
    status_msg,
    runtime_state,
    internal_user_id: int,
    username: Optional[str],
    prompt: str,
    task_type: str,
    registry_task_id: str,
    backend_task_id: str,
    saved_inputs: list[str],
    final_info,
    is_video: bool,
    message_spec,
    send_result: bool,
    reply_markup,
    result_meta: dict | None,
    delete_status: bool,
    allow_contribute: bool,
    record_history: bool,
    billing_resolution: Optional[str],
    requested_duration: Optional[int],
    missing_output_should_refund: bool,
):
    return await task_service_completion_helpers.complete_monitored_bot_task(
        completion=BotTaskCompletionContext(
            context=context,
            chat_id=chat_id,
            status_msg=status_msg,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            prompt=prompt,
            task_type=task_type,
            registry_task_id=registry_task_id,
            backend_task_id=backend_task_id,
            saved_input_images=saved_inputs,
            final_info=final_info,
            is_video=is_video,
            message_spec=message_spec,
            user_logger=UserLogger(internal_user_id, username),
            send_result=send_result,
            reply_markup=reply_markup,
            result_meta=result_meta,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            record_history=record_history,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            missing_output_should_refund=missing_output_should_refund,
        ),
    )


def should_refund_for_unexpected_bot_error(
    *,
    runtime_state,
    deduct_quota: bool,
    unexpected_should_refund: Optional[Callable],
) -> bool:
    if unexpected_should_refund is not None:
        return unexpected_should_refund(runtime_state)
    return deduct_quota and runtime_state.task_submitted


async def cleanup_bot_task_flow(
    *,
    internal_user_id: int,
    runtime_state,
    cleanup_enabled: bool,
    cleanup_paths: Optional[list[str]],
    cleanup_files_func,
    cleanup_runtime_enabled: bool = True,
):
    if cleanup_runtime_enabled:
        await task_service_finalize_helpers.cleanup_runtime_state_if_needed(
            internal_user_id=internal_user_id,
            registry_task_id=runtime_state.registry_task_id,
            release_lock=runtime_state.task_submitted,
            terminal_state_finalized=runtime_state.terminal_state_finalized,
        )
    if cleanup_enabled and cleanup_paths:
        cleanup_files_func(cleanup_paths)


async def execute_bot_task_stages(
    *,
    flow: BotTaskFlowContext,
    execution: _BotTaskExecutionState,
    submission: BotTaskSubmissionContext,
) -> tuple[bytes | None, str | None]:
    request = flow.request
    presentation = flow.presentation
    billing = flow.billing
    allow_cancel = getattr(presentation, "allow_cancel", True)
    show_queue_status = getattr(presentation, "show_queue_status", True)
    (
        execution.status_msg,
        execution.registry_task_id,
        execution.backend_task_id,
        execution.saved_inputs,
        execution.message_spec,
    ) = await run_bot_task_submission_stage(
        context=request.context,
        update=request.update,
        chat_id=request.chat_id,
        status_msg_id=request.status_msg_id,
        message_spec=presentation.message_spec,
        submitted_status_builder=presentation.submitted_status_builder,
        submission=submission,
        allow_cancel=allow_cancel,
        is_video=getattr(request, "is_video", False),
        show_queue_status=show_queue_status,
    )

    async def monitor_and_complete():
        completion_result_meta = merge_minimax_h3_input_assets_into_metadata(
            task_type=request.task_type,
            metadata=presentation.result_meta,
            inputs=submission.inputs,
        )
        return await run_monitored_task_lifecycle(
            monitor_stage_func=lambda: run_bot_task_monitor_stage(
                backend_task_id=execution.backend_task_id,
                status_msg=execution.status_msg,
                is_video=request.is_video,
                internal_user_id=request.internal_user_id,
                lang=resolve_context_lang(request.context),
                allow_cancel=allow_cancel,
                show_queue_status=show_queue_status,
            ),
            route_terminal_result_func=lambda final_info: run_bot_task_completion_stage(
                context=request.context,
                chat_id=request.chat_id,
                status_msg=execution.status_msg,
                runtime_state=flow.runtime_state,
                internal_user_id=request.internal_user_id,
                username=request.username,
                prompt=getattr(presentation, "result_prompt", None) or request.prompt,
                task_type=(
                    getattr(presentation, "result_task_type", None) or request.task_type
                ),
                registry_task_id=execution.registry_task_id,
                backend_task_id=execution.backend_task_id,
                saved_inputs=select_result_saved_inputs(
                    execution.saved_inputs or [],
                    getattr(presentation, "result_input_image_indices", None),
                ),
                final_info=final_info,
                is_video=request.is_video,
                message_spec=execution.message_spec or presentation.message_spec,
                send_result=presentation.send_result,
                reply_markup=presentation.reply_markup,
                result_meta=completion_result_meta,
                delete_status=presentation.delete_status,
                allow_contribute=presentation.allow_contribute,
                record_history=getattr(presentation, "record_history", True),
                billing_resolution=billing.billing_resolution,
                requested_duration=billing.requested_duration,
                missing_output_should_refund=billing.missing_output_should_refund,
            ),
        )

    if parse_private_bot_client_type(submission.client_type) is None:
        return await monitor_and_complete()

    from src.services.private_bot_task_monitor_lease import (
        private_bot_task_monitor_lease,
    )

    lease_stack = contextlib.AsyncExitStack()
    try:
        await lease_stack.enter_async_context(
            private_bot_task_monitor_lease(execution.registry_task_id or "")
        )
    except BaseException:
        await lease_stack.aclose()
        raise
    execution.monitor_lease_stack = lease_stack
    return await monitor_and_complete()


async def run_bot_task_application(
    *,
    flow: BotTaskFlowContext,
) -> tuple[bytes | None, str | None]:
    request = flow.request
    presentation = flow.presentation
    failure_policy = flow.failure_policy
    cleanup_policy = flow.cleanup_policy
    execution = _BotTaskExecutionState(message_spec=presentation.message_spec)
    bot_data = getattr(request.context, "bot_data", {}) or {}
    client_type = bot_data.get("bot_client_type", "bot")
    submission = BotTaskSubmissionContext(
        runtime_state=flow.runtime_state,
        internal_user_id=request.internal_user_id,
        username=request.username,
        task_type=request.task_type,
        inputs=request.inputs,
        source_post_id=request.source_post_id,
        deduct_quota=request.deduct_quota,
        client_type=client_type,
        cost_override=getattr(request, "cost_override", None),
        base_priority=getattr(request, "base_priority", 0),
        user_cancel_allowed=getattr(request, "user_cancel_allowed", True),
        recovery_metadata=build_bot_task_recovery_metadata(
            flow=flow,
            client_type=client_type,
        ),
        task_id_override=getattr(request, "task_id_override", None),
    )

    try:
        return await execute_bot_task_stages(
            flow=flow,
            execution=execution,
            submission=submission,
        )
    except ConcurrencyLimitError as e:
        await task_service_finalize_helpers.send_bot_warning(
            request.context, request.chat_id, e
        )
        return None, None
    except InsufficientCreditsError as e:
        await task_service_finalize_helpers.send_bot_warning(
            request.context, request.chat_id, e
        )
        return None, None
    except BotTaskCancelled:
        return await task_service_finalize_helpers.handle_bot_cancelled_exception(
            status_msg=execution.status_msg,
            runtime_state=flow.runtime_state,
            internal_user_id=request.internal_user_id,
            username=request.username,
            message_spec=execution.message_spec or presentation.message_spec,
            deduct_quota=request.deduct_quota,
        )
    except private_bot_submission_ledger.PrivateBotSubmissionReplayHandled:
        # Startup recovery (or the first live flow) retains the only monitor and
        # delivery ownership for this deterministic registry task.
        return None, None
    except PrivateBotTaskMonitorLeaseError:
        # Another process owns delivery, or this process lost its lease during
        # shutdown/failover. Preserve the paid registry record for recovery.
        execution.preserve_runtime_state = True
        return None, None
    except PrivateQqccContinuationError:
        # The paid task/result remains recoverable through TaskRegistry.  Do
        # not refund or release its concurrency state until the continuation
        # checkpoint durably records the result.
        execution.preserve_runtime_state = True
        raise
    except asyncio.CancelledError:
        if (
            parse_private_bot_client_type(client_type) is not None
            and bool(getattr(flow.runtime_state, "task_submitted", False))
            and not bool(getattr(flow.runtime_state, "terminal_state_finalized", False))
        ):
            execution.preserve_runtime_state = True
        raise
    except CoreDomainError as e:
        await task_service_finalize_helpers.send_bot_domain_error(
            request.context, request.chat_id, e
        )
        return None, None
    except Exception as e:
        return await task_service_finalize_helpers.handle_bot_unexpected_exception(
            context=request.context,
            chat_id=request.chat_id,
            status_msg=(
                execution.status_msg if presentation.prefer_edit_status else None
            ),
            runtime_state=flow.runtime_state,
            internal_user_id=request.internal_user_id,
            username=request.username,
            error=e,
            log_message=failure_policy.unexpected_error_log_message.format(
                internal_user_id=request.internal_user_id,
                error=e,
            ),
            should_refund=should_refund_for_unexpected_bot_error(
                runtime_state=flow.runtime_state,
                deduct_quota=request.deduct_quota,
                unexpected_should_refund=failure_policy.unexpected_should_refund,
            ),
            generic_error_prefix=failure_policy.unexpected_error_prefix,
            prefer_edit_status=presentation.prefer_edit_status,
            refund_suffix_mode=failure_policy.refund_suffix_mode,
        )
    finally:
        try:
            await cleanup_bot_task_flow(
                internal_user_id=request.internal_user_id,
                runtime_state=flow.runtime_state,
                cleanup_enabled=cleanup_policy.cleanup_enabled,
                cleanup_paths=cleanup_policy.cleanup_paths,
                cleanup_files_func=cleanup_policy.cleanup_files_func,
                cleanup_runtime_enabled=not execution.preserve_runtime_state,
            )
        finally:
            if execution.monitor_lease_stack is not None:
                await execution.monitor_lease_stack.aclose()
