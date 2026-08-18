import os
import uuid
from collections.abc import Awaitable, Callable

from asgi_correlation_id import correlation_id

from config import MINIO_BUCKET
from src.core.task_application import TaskApplication
from src.core.task_core_types import (
    CoreDomainError,
    SubmissionReconciliationPending,
    TaskSubmissionCommand,
    TaskSubmissionPolicy,
    TaskSubmissionSideEffectPlan,
)
from src.services.scail2_face_swap_pipeline_service import (
    cleanup_scail2_face_swap_first_frame,
    prepare_scail2_face_swap_first_frame,
)
from src.services.storage import storage
from src.services.storage_r2_promotion import promote_staged_user_inputs
from src.services.task_web_submission_intent import WebSubmissionIntentJournal
from src.task_application_runtime import get_task_application
from src.utils import is_maintenance_mode
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse
from src.web_api.services.web_submission_preparation import (
    WEB_FREE_EDIT_V3_COST,
    WEB_FREE_EDIT_V3_TASK_TYPE,
    prepare_web_pipeline,
    prepare_web_submission_request,
)
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in _ENABLED_VALUES


def _submission_feature_enabled(name: str, *, operator_canary: bool) -> bool:
    if name == "LTX_T2V_MSR_ENABLED" and operator_canary:
        return True
    return _env_enabled(name)


async def submit_generation_task(
    *,
    req: TaskGenerateRequest,
    current_user,
    get_balance: Callable[[int], Awaitable[int]],
    logger=None,
    operator_canary_authorized: bool = False,
    task_id_override: str | None = None,
    registry_metadata_extra: dict | None = None,
    allow_contribute_override: bool | None = None,
    promote_staged_inputs_func=None,
    task_application: TaskApplication | None = None,
) -> TaskGenerateResponse:
    scail2_first_frame_to_cleanup = None
    try:
        if is_maintenance_mode():
            raise CoreDomainError("系统维护中，生成任务暂时不可提交，请稍后再试。")
        prepared = await prepare_web_submission_request(
            req,
            internal_user_id=current_user.id,
            operator_canary_authorized=operator_canary_authorized,
            env_enabled=lambda name: _submission_feature_enabled(
                name,
                operator_canary=operator_canary_authorized,
            ),
        )
        inputs = prepared.inputs
        images = prepared.images
        is_template = prepared.is_template

        task_id = task_id_override or str(uuid.uuid4())
        correlation_id.set(task_id)
        promote_staged_inputs_func = (
            promote_staged_inputs_func or promote_staged_user_inputs
        )
        if images:
            images = await promote_staged_inputs_func(
                input_refs=images,
                task_id=task_id,
                user_id=current_user.id,
                bucket=MINIO_BUCKET,
                client=storage.client,
            )
            inputs["images"] = images

        pipeline = await prepare_web_pipeline(
            task_type=req.task_type,
            inputs=inputs,
            images=images,
            internal_user_id=current_user.id,
            task_id=task_id,
            priority=req.priority,
            is_template=is_template,
            allow_contribute_override=allow_contribute_override,
            registry_metadata_extra=registry_metadata_extra,
            prepare_scail2_first_frame=prepare_scail2_face_swap_first_frame,
        )
        registry_metadata = pipeline.registry_metadata
        scail2_first_frame_to_cleanup = pipeline.cleanup_object_key

        submission_journal = WebSubmissionIntentJournal(
            internal_user_id=current_user.id,
            username=current_user.username,
            task_id=task_id,
            source_post_id=req.source_post_id,
        )

        try:
            application = task_application or get_task_application()
            result = await application.submit(
                TaskSubmissionCommand(
                    internal_user_id=current_user.id,
                    username=current_user.username,
                    task_type=req.task_type,
                    inputs=inputs,
                    task_id=task_id,
                    source_post_id=req.source_post_id,
                    registry_metadata=registry_metadata or None,
                ),
                TaskSubmissionPolicy(
                    base_priority=req.priority,
                    is_template=is_template,
                    side_effect_plan=TaskSubmissionSideEffectPlan(
                        attach_web_monitor=True,
                        source_post_id=req.source_post_id,
                    ),
                    cost_override=(
                        WEB_FREE_EDIT_V3_COST
                        if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE
                        else None
                    ),
                    user_cancel_allowed=True,
                    allow_contribute_override=allow_contribute_override,
                    refund_idempotency_key=(
                        submission_journal.refund_idempotency_key
                    ),
                ),
                submission_journal,
            )
        except SubmissionReconciliationPending as exc:
            scail2_first_frame_to_cleanup = None
            balance = await get_balance(current_user.id)
            return TaskGenerateResponse(
                task_id=exc.registry_task_id,
                status="pending",
                submission_state="reconciling",
                message="Task dispatch is being reconciled",
                cost=exc.cost,
                balance_remaining=balance,
            )
        scail2_first_frame_to_cleanup = None

        balance = await get_balance(current_user.id)
        return TaskGenerateResponse(
            task_id=result["task_id"],
            status="pending",
            submission_state="accepted",
            message="Task submitted successfully",
            cost=result["cost"],
            balance_remaining=balance,
        )
    except Exception as exc:
        if scail2_first_frame_to_cleanup:
            await cleanup_scail2_face_swap_first_frame(scail2_first_frame_to_cleanup)
        if logger is not None:
            logger.error("Task submission error: %s", exc, exc_info=True)
        raise
