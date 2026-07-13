import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TaskExecutionContext:
    task_id: str
    task_type: str
    prompt_id: Optional[str] = None
    task_result: Optional[str] = None
    task_result_priority: int = -1
    task_error: Optional[str] = None
    phase: str = "preparing"
    params: dict[str, Any] = field(default_factory=dict)
    downloaded_input_paths: list[str] = field(default_factory=list)
    completed_event: asyncio.Event = field(default_factory=asyncio.Event)
