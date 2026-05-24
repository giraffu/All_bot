from src.database.core import AsyncSessionLocal


def get_gallery_storage_service():
    from src.services.storage import storage as storage_impl

    return storage_impl


def get_gallery_submission_outbox():
    from src.services.redis_client import redis_client as redis_client_impl

    return redis_client_impl


def get_gallery_session_factory():
    return AsyncSessionLocal
