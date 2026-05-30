import asyncio
import logging

from src.core.task_core_default_dependencies import (
    build_default_task_core_process_dependencies,
)
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import CoreDomainError

logger = logging.getLogger("src.core.task_core")


def build_runtime_default_task_core_process_dependencies(
    *,
    logger_override=logger,
) -> TaskCoreProcessDependencies:
    from config import MINIO_BUCKET
    from src.constants import VIDEO_TASK_TYPES
    from src.core.billing_core import (
        check_and_deduct_credits,
        check_concurrency_lock,
        get_user_priority_and_identity,
        release_concurrency_lock,
    )
    from src.core.task_dispatcher import StrategyFactory
    from src.core.task_core_submission import (
        compensate_failed_submission_default,
        execute_task_submission_saga_default,
    )
    from src.services.task_web_side_effects import (
        attach_submission_side_effects_default,
    )
    from src.utils import load_prompts
    from src.core.task_core_input_preparation import (
        process_input_path,
        validate_local_input_paths,
    )
    from src.core.task_core_video_request import build_video_task_request
    from src.logger import UserLogger

    async def attach_submission_side_effects_func(**kwargs):
        return await attach_submission_side_effects_default(
            core_domain_error_cls=CoreDomainError,
            **kwargs,
        )

    return build_default_task_core_process_dependencies(
        video_task_types=VIDEO_TASK_TYPES,
        build_video_task_request_func=build_video_task_request,
        check_concurrency_lock_func=check_concurrency_lock,
        check_and_deduct_credits_func=check_and_deduct_credits,
        execute_task_submission_saga_func=execute_task_submission_saga_default,
        attach_submission_side_effects_func=attach_submission_side_effects_func,
        compensate_failed_submission_func=compensate_failed_submission_default,
        release_concurrency_lock_func=release_concurrency_lock,
        get_strategy_func=StrategyFactory.get_strategy,
        user_logger_factory=UserLogger,
        validate_local_input_paths_func=validate_local_input_paths,
        get_user_priority_and_identity_func=get_user_priority_and_identity,
        load_prompts_func=load_prompts,
        process_input_path_func=process_input_path,
        bucket_name=MINIO_BUCKET,
        shield_func=asyncio.shield,
        logger_override=logger_override,
    )
