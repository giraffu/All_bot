from src.api_client import api_client
from src.core.task_core_service_providers import (
    TaskCoreServiceProviders,
    configure_task_core_service_providers,
    get_configured_task_core_service_providers,
)
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.redis_client import redis_client
from src.services.storage import storage
from src.services.task_registry import TaskRegistry


def ensure_task_core_service_providers_registered() -> TaskCoreServiceProviders:
    configured = get_configured_task_core_service_providers()
    if configured is not None:
        return configured

    return configure_task_core_service_providers(
        TaskCoreServiceProviders(
            get_image_service=lambda: image_service,
            get_storage_service=lambda: storage,
            get_task_registry=lambda: TaskRegistry,
            get_permission_service=lambda: permission_service,
            get_submission_outbox=lambda: redis_client,
            get_api_client=lambda: api_client,
        )
    )
