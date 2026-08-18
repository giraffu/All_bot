class LegacyTaskApplicationAdapter:
    """Translate typed application calls for behavior tests with legacy fakes."""

    def __init__(self, submit_func):
        self.submit_func = submit_func

    async def submit(self, command, policy, journal):
        return await self.submit_func(
            user_id=command.internal_user_id,
            username=command.username,
            task_type=command.task_type,
            inputs=command.inputs,
            task_id=command.task_id,
            base_priority=policy.base_priority,
            is_template=policy.is_template,
            client_type=policy.client_type,
            deduct_quota=policy.deduct_quota,
            check_lock=policy.check_lock,
            source_post_id=command.source_post_id,
            submission_side_effect_plan=policy.side_effect_plan,
            delivery_context=command.delivery_context,
            cost_override=policy.cost_override,
            user_cancel_allowed=policy.user_cancel_allowed,
            submission_concurrency_idempotency_key=(
                policy.concurrency_idempotency_key
            ),
            submission_idempotency_key=policy.debit_idempotency_key,
            registry_metadata=command.registry_metadata,
            allow_contribute_override=policy.allow_contribute_override,
            submission_prepare_timeout_seconds=policy.prepare_timeout_seconds,
            submission_before_debit_func=journal.before_debit,
            submission_after_debit_func=journal.after_debit,
            submission_debit_timeout_seconds=policy.debit_timeout_seconds,
            submission_before_dispatch_func=journal.before_dispatch,
            submission_dispatch_timeout_seconds=policy.dispatch_timeout_seconds,
            submission_should_compensate_func=journal.should_compensate,
            submission_refund_idempotency_key=policy.refund_idempotency_key,
            submission_refund_task_type=policy.refund_task_type,
            submission_release_idempotency_key=policy.release_idempotency_key,
            submission_before_compensation_func=journal.before_compensation,
        )
