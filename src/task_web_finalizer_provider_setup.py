from __future__ import annotations

from src.services.task_web_finalizer_dependencies import (
    TaskWebFinalizerDependencies,
    configure_task_web_finalizer_dependencies,
)


async def _store_prompt_result(**kwargs):
    from src.web_api.services.prompt_result_store import store_prompt_result

    return await store_prompt_result(**kwargs)


async def _store_prompt_failure_result(**kwargs):
    from src.web_api.services.prompt_result_store import store_prompt_failure_result

    return await store_prompt_failure_result(**kwargs)


async def _finalize_character_reference(**kwargs):
    from src.web_api.services.character_reference_service import (
        finalize_character_reference,
    )

    return await finalize_character_reference(**kwargs)


async def _finalize_official_asset(**kwargs):
    from src.web_api.services.official_asset_finalizer import finalize_official_asset

    return await finalize_official_asset(**kwargs)


def configure_task_web_finalizer_providers() -> None:
    configure_task_web_finalizer_dependencies(
        TaskWebFinalizerDependencies(
            store_prompt_result=_store_prompt_result,
            store_prompt_failure_result=_store_prompt_failure_result,
            finalize_character_reference=_finalize_character_reference,
            finalize_official_asset=_finalize_official_asset,
        )
    )
