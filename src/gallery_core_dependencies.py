from dataclasses import dataclass
from functools import lru_cache

from src.database.core import AsyncSessionLocal
from src.core.billing_core import get_default_billing_core_providers
from src.core.task_core_service_providers import get_task_core_storage_service


@dataclass(frozen=True)
class GallerySubmissionDependencies:
    session_factory: object
    get_gallery_post_by_task_id_func: object
    get_gallery_history_for_user_task_func: object
    get_gallery_user_func: object
    reactivate_gallery_post_for_owner_func: object
    create_gallery_post_from_history_func: object
    check_gallery_submit_limit_func: object | None
    increment_gallery_submit_func: object | None


@dataclass(frozen=True)
class GalleryInteractionDependencies:
    session_factory: object
    get_gallery_post_by_id_func: object
    get_gallery_reaction_interaction_func: object
    remove_gallery_reaction_func: object
    decrement_gallery_reaction_counter_func: object
    switch_gallery_reaction_func: object
    insert_gallery_reaction_if_absent_func: object
    increment_gallery_reaction_counter_func: object
    insert_gallery_apply_interaction_if_absent_func: object
    increment_gallery_apply_counter_func: object


def get_gallery_storage_service():
    return get_task_core_storage_service()


def get_gallery_submission_outbox():
    return get_default_billing_core_providers().get_redis_client_func()


def get_gallery_session_factory():
    return AsyncSessionLocal


@lru_cache(maxsize=1)
def get_default_gallery_submission_dependencies() -> GallerySubmissionDependencies:
    from src.services.gallery_repository import (
        create_gallery_post_from_history,
        get_gallery_history_for_user_task,
        get_gallery_post_by_task_id,
        get_gallery_user,
        reactivate_gallery_post_for_owner,
    )

    return GallerySubmissionDependencies(
        session_factory=get_gallery_session_factory(),
        get_gallery_post_by_task_id_func=get_gallery_post_by_task_id,
        get_gallery_history_for_user_task_func=get_gallery_history_for_user_task,
        get_gallery_user_func=get_gallery_user,
        reactivate_gallery_post_for_owner_func=reactivate_gallery_post_for_owner,
        create_gallery_post_from_history_func=create_gallery_post_from_history,
        check_gallery_submit_limit_func=None,
        increment_gallery_submit_func=None,
    )


@lru_cache(maxsize=1)
def get_default_gallery_interaction_dependencies() -> GalleryInteractionDependencies:
    from src.services.gallery_repository import (
        decrement_gallery_reaction_counter,
        get_gallery_post_by_id,
        get_gallery_reaction_interaction,
        increment_gallery_apply_counter,
        increment_gallery_reaction_counter,
        insert_gallery_apply_interaction_if_absent,
        insert_gallery_reaction_if_absent,
        remove_gallery_reaction,
        switch_gallery_reaction,
    )

    return GalleryInteractionDependencies(
        session_factory=get_gallery_session_factory(),
        get_gallery_post_by_id_func=get_gallery_post_by_id,
        get_gallery_reaction_interaction_func=get_gallery_reaction_interaction,
        remove_gallery_reaction_func=remove_gallery_reaction,
        decrement_gallery_reaction_counter_func=decrement_gallery_reaction_counter,
        switch_gallery_reaction_func=switch_gallery_reaction,
        insert_gallery_reaction_if_absent_func=insert_gallery_reaction_if_absent,
        increment_gallery_reaction_counter_func=increment_gallery_reaction_counter,
        insert_gallery_apply_interaction_if_absent_func=(
            insert_gallery_apply_interaction_if_absent
        ),
        increment_gallery_apply_counter_func=increment_gallery_apply_counter,
    )
