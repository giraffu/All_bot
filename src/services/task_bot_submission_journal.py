from dataclasses import dataclass

from src.core.task_core_types import CoreDomainError, SubmissionJournal


@dataclass(slots=True)
class BotRecoverySubmissionJournal(SubmissionJournal):
    """Guard the registry identity used by the Bot recovery record."""

    expected_registry_task_id: str
    dispatching_persisted: bool = False

    async def before_dispatch(self, **event) -> None:
        registry_task_id = str(event.get("registry_task_id") or "")
        if registry_task_id != self.expected_registry_task_id:
            raise CoreDomainError("Bot recovery registry identity changed before dispatch")
        self.dispatching_persisted = True
