from src.database.core import AsyncSessionLocal
from src.core.billing_core import get_default_billing_core_providers
from src.core.task_core_service_providers import get_task_core_storage_service


def get_gallery_storage_service():
    return get_task_core_storage_service()


def get_gallery_submission_outbox():
    return get_default_billing_core_providers().get_redis_client_func()


def get_gallery_session_factory():
    return AsyncSessionLocal
