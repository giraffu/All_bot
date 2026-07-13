import uuid
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable

from app.main_response_helpers import (
    build_result_url as build_result_url_helper,
    build_task_status_response as build_task_status_response_helper,
    serve_task_result_file as serve_task_result_file_helper,
)
from app.main_t2i_helpers import (
    prepare_t2i_request_payload as prepare_t2i_request_payload_helper,
    build_t2i_terminal_response as build_t2i_terminal_response_helper,
    build_task_event_channel as build_task_event_channel_helper,
    close_task_event_subscription as close_task_event_subscription_helper,
    decode_t2i_pubsub_message as decode_t2i_pubsub_message_helper,
    enqueue_t2i_task as enqueue_t2i_task_helper,
    get_immediate_t2i_terminal_response as get_immediate_t2i_terminal_response_helper,
    optional_t2i_task_subscription as optional_t2i_task_subscription_helper,
    resolve_t2i_priority as resolve_t2i_priority_helper,
    submit_t2i_task_request as submit_t2i_task_request_helper,
    subscribe_task_events as subscribe_task_events_helper,
    validate_t2i_prompt as validate_t2i_prompt_helper,
    wait_for_t2i_sync_result as wait_for_t2i_sync_result_helper,
    wait_for_t2i_terminal_response as wait_for_t2i_terminal_response_helper,
)


@dataclass(frozen=True)
class T2IWiring:
    prepare_task_request_func: Callable[..., Any]
    submit_task_request_func: Callable[..., Any]
    build_task_status_response_func: Callable[..., Any]
    serve_task_result_file_func: Callable[..., Any]


def build_t2i_wiring(
    *,
    response_cls,
    task_type,
    settings,
    logger,
) -> T2IWiring:
    def build_result_url(result_path: str) -> str:
        return build_result_url_helper(
            result_path=result_path,
            settings=settings,
        )

    build_terminal_response_func = partial(
        build_t2i_terminal_response_helper,
        response_cls=response_cls,
        build_result_url_func=build_result_url,
        logger=logger,
    )
    wait_for_terminal_response_func = partial(
        wait_for_t2i_terminal_response_helper,
        decode_message_func=decode_t2i_pubsub_message_helper,
        build_terminal_response_func=build_terminal_response_func,
    )
    subscribe_task_events_func = partial(
        subscribe_task_events_helper,
        build_channel_func=build_task_event_channel_helper,
    )
    optional_subscription_func = partial(
        optional_t2i_task_subscription_helper,
        subscribe_task_events_func=subscribe_task_events_func,
        close_task_event_subscription_func=close_task_event_subscription_helper,
    )
    enqueue_task_func = partial(
        enqueue_t2i_task_helper,
        task_type=task_type,
        logger=logger,
    )
    get_immediate_response_func = partial(
        get_immediate_t2i_terminal_response_helper,
        build_terminal_response_func=build_terminal_response_func,
    )
    wait_for_sync_result_func = partial(
        wait_for_t2i_sync_result_helper,
        logger=logger,
        get_immediate_response_func=get_immediate_response_func,
        wait_for_terminal_response_func=wait_for_terminal_response_func,
    )

    return T2IWiring(
        prepare_task_request_func=partial(
            prepare_t2i_request_payload_helper,
            uuid_factory=uuid.uuid4,
            validate_prompt_func=validate_t2i_prompt_helper,
            resolve_priority_func=resolve_t2i_priority_helper,
        ),
        submit_task_request_func=partial(
            submit_t2i_task_request_helper,
            response_cls=response_cls,
            optional_subscription_func=optional_subscription_func,
            enqueue_t2i_task_func=enqueue_task_func,
            wait_for_sync_result_func=wait_for_sync_result_func,
            logger=logger,
        ),
        build_task_status_response_func=partial(
            build_task_status_response_helper,
            build_result_url_func=build_result_url,
        ),
        serve_task_result_file_func=partial(
            serve_task_result_file_helper,
            settings=settings,
            logger=logger,
        ),
    )
