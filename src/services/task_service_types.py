from dataclasses import dataclass
from typing import Optional


@dataclass
class BotTaskRuntimeState:
    registry_task_id: Optional[str] = None
    task_submitted: bool = False
    actual_cost: int = 0
    terminal_state_finalized: bool = False


@dataclass(frozen=True)
class BotTaskMessageSpec:
    initial_status_text: str
    submitted_status_text: Optional[str] = None
    progress_wait_text: Optional[str] = None
    completion_caption: Optional[str] = None
    missing_output_message: str = "生成完成但未获取到文件路径，已退还灵石"
    cancellation_message_template: str = "任务已撤销，预扣的 {cost} 灵石已全额退回。"
