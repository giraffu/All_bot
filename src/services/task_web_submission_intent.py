from dataclasses import dataclass

from src.core.task_core_types import TaskSubmissionContext
from src.services.task_web_finalizer import prepare_web_submission_intent


@dataclass(slots=True)
class WebSubmissionIntentJournal:
    """Web adapter for the durable boundary immediately before Central dispatch."""

    internal_user_id: int
    username: str
    task_id: str
    source_post_id: int | None = None
    dispatching_persisted: bool = False

    @property
    def refund_idempotency_key(self) -> str:
        return f"task_refund:task:{self.task_id}"

    async def before_dispatch(
        self,
        *,
        registry_task_id: str,
        cost: int,
        submission_context: TaskSubmissionContext,
        **_kwargs,
    ) -> None:
        await prepare_web_submission_intent(
            internal_user_id=self.internal_user_id,
            username=self.username,
            registry_task_id=registry_task_id,
            submission_context=submission_context,
            cost=cost,
            source_post_id=self.source_post_id,
        )
        self.dispatching_persisted = True

    def should_compensate(self, _error: Exception) -> bool:
        return not self.dispatching_persisted
