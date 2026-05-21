from src.services.task_service_entrypoints_generation import (
    process_generation_task,
    process_i2i_pro_task,
)


async def process_generation_task_entrypoint(*, service_cls, **kwargs):
    return await process_generation_task(service=service_cls, **kwargs)


async def process_i2i_pro_task_entrypoint(*, service_cls, **kwargs):
    return await process_i2i_pro_task(service=service_cls, **kwargs)
