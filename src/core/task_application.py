from __future__ import annotations

import asyncio
import inspect

from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_process_flow import (
    build_prepared_task_submission_request,
    build_submission_failure_error,
    build_successful_submission_response,
    compensate_failed_task_submission,
    ensure_submission_concurrency_lock,
    execute_task_submission_attempt,
    maybe_deduct_submission_credits,
    prepare_task_submission_context,
    release_submission_lock_if_needed,
)
from src.core.task_core_types import (
    SubmissionJournal,
    SubmissionReconciliationPending,
    TaskSubmissionCommand,
    TaskSubmissionPolicy,
)
from src.core.task_lifecycle_contract import (
    normalize_task_submission_side_effect_plan,
)


class TaskApplication:
    """Explicitly assembled application service for task submission."""

    def __init__(self, *, dependencies: TaskCoreProcessDependencies):
        self._dependencies = dependencies

    async def submit(
        self,
        command: TaskSubmissionCommand,
        policy: TaskSubmissionPolicy | None = None,
        journal: SubmissionJournal | None = None,
    ) -> dict:
        policy = policy or TaskSubmissionPolicy()
        journal = journal or SubmissionJournal()
        dependencies = self._dependencies
        user_id = command.internal_user_id
        task_type = command.task_type
        task_id = command.task_id
        concurrency_idempotency_key = (
            policy.concurrency_idempotency_key or f"task_concurrency:{task_id}"
        )
        release_idempotency_key = (
            policy.release_idempotency_key or concurrency_idempotency_key
        )
        side_effect_plan = normalize_task_submission_side_effect_plan(
            submission_side_effect_plan=policy.side_effect_plan,
            client_type=policy.client_type,
            source_post_id=command.source_post_id,
        )
        request = build_prepared_task_submission_request(
            task_type=task_type,
            inputs=command.inputs,
            dependencies=dependencies,
            cost_override=policy.cost_override,
        )
        await ensure_submission_concurrency_lock(
            user_id=user_id,
            task_type=task_type,
            check_lock=policy.check_lock,
            dependencies=dependencies,
            idempotency_key=concurrency_idempotency_key,
        )

        task_submitted_successfully = False
        credits_deducted = False
        registry_task_id = task_id

        try:
            prepare_kwargs = dict(
                user_id=user_id,
                username=command.username,
                task_type=task_type,
                inputs=command.inputs,
                registry_task_id=registry_task_id,
                base_priority=policy.base_priority,
                is_template=policy.is_template,
                request=request,
                dependencies=dependencies,
            )
            if policy.prepare_timeout_seconds is None:
                submission_context = await prepare_task_submission_context(
                    **prepare_kwargs
                )
            else:
                submission_context = await asyncio.wait_for(
                    prepare_task_submission_context(**prepare_kwargs),
                    timeout=float(policy.prepare_timeout_seconds),
                )
            if command.registry_metadata:
                submission_context.metadata.update(command.registry_metadata)
            if policy.allow_contribute_override is not None:
                submission_context.allow_contribute = bool(
                    policy.allow_contribute_override
                )
            submission_context.client_type = policy.client_type
            submission_context.user_cancel_allowed = policy.user_cancel_allowed
            submission_context.concurrency_acquisition_key = (
                concurrency_idempotency_key
            )
            if command.delivery_context:
                submission_context.delivery_context.update(
                    {
                        key: value
                        for key, value in command.delivery_context.items()
                        if key in {"chat_id", "message_id"} and value is not None
                    }
                )

            await journal.before_debit(
                cost=request.cost,
                registry_task_id=registry_task_id,
            )

            debit_kwargs = dict(
                user_id=user_id,
                username=command.username,
                task_type=task_type,
                cost=request.cost,
                deduct_quota=policy.deduct_quota,
                dependencies=dependencies,
                idempotency_key=policy.debit_idempotency_key,
            )
            if policy.debit_timeout_seconds is None:
                credits_deducted = await maybe_deduct_submission_credits(
                    **debit_kwargs
                )
            else:
                credits_deducted = await asyncio.wait_for(
                    maybe_deduct_submission_credits(**debit_kwargs),
                    timeout=float(policy.debit_timeout_seconds),
                )
            await journal.after_debit(
                cost=request.cost,
                registry_task_id=registry_task_id,
                credits_deducted=credits_deducted,
            )

            try:
                execution_result = await execute_task_submission_attempt(
                    user_id=user_id,
                    username=command.username,
                    task_type=task_type,
                    inputs=command.inputs,
                    registry_task_id=registry_task_id,
                    cost=request.cost,
                    deduct_quota=policy.deduct_quota,
                    submission_context=submission_context,
                    submission_side_effect_plan=side_effect_plan,
                    dependencies=dependencies,
                    submission_before_dispatch_func=journal.before_dispatch,
                    submission_dispatch_timeout_seconds=(
                        policy.dispatch_timeout_seconds
                    ),
                )
                registry_task_id = execution_result.registry_task_id
                task_submitted_successfully = True
                return build_successful_submission_response(
                    execution_result=execution_result,
                    cost=request.cost,
                )

            except Exception as error:
                decision = journal.should_compensate(error)
                should_compensate = bool(
                    await decision if inspect.isawaitable(decision) else decision
                )
                if should_compensate:
                    await journal.before_compensation(
                        error=error,
                        cost=request.cost,
                        registry_task_id=registry_task_id,
                        credits_deducted=credits_deducted,
                    )
                    await compensate_failed_task_submission(
                        user_id=user_id,
                        username=command.username,
                        cost=request.cost,
                        error=error,
                        credits_deducted=credits_deducted,
                        registry_task_id=registry_task_id,
                        dependencies=dependencies,
                        refund_idempotency_key=policy.refund_idempotency_key,
                        refund_task_type=(
                            policy.refund_task_type or "refund_saga_failed"
                        ),
                    )
                    raise build_submission_failure_error(error)
                task_submitted_successfully = True
                raise SubmissionReconciliationPending(
                    registry_task_id=registry_task_id,
                    cost=request.cost,
                ) from error

        finally:
            await release_submission_lock_if_needed(
                user_id=user_id,
                check_lock=policy.check_lock,
                task_submitted_successfully=task_submitted_successfully,
                dependencies=dependencies,
                release_idempotency_key=release_idempotency_key,
            )
