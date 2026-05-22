UNSUPPORTED_VIDEO_MESSAGE = "⚠️ 当前模式不支持视频处理。"
UNSUPPORTED_DOCUMENT_MESSAGE = "⚠️ 请发送压缩后的图片或视频格式，不要发送原图/文件。"


async def handle_media_update_impl(
    update,
    context,
    *,
    handle_media_entry,
    is_mentioned,
    ensure_access_and_reward,
    on_template_contribution,
    on_photo_idle,
    handle_media_message_fn,
    unsupported_message: str | None = None,
):
    return await handle_media_entry(
        update,
        context,
        unsupported_message=unsupported_message,
        is_mentioned=is_mentioned,
        ensure_access_and_reward=ensure_access_and_reward,
        on_template_contribution=on_template_contribution,
        on_photo_idle=on_photo_idle,
        handle_media_message_fn=handle_media_message_fn,
    )


def build_media_update_handler(
    *,
    handler_name: str,
    handle_media_entry,
    is_mentioned,
    ensure_access_and_reward,
    on_template_contribution,
    on_photo_idle,
    handle_media_message_fn,
    unsupported_message: str | None = None,
    decorators: tuple = (),
):
    async def handler(update, context):
        return await handle_media_update_impl(
            update,
            context,
            handle_media_entry=handle_media_entry,
            unsupported_message=unsupported_message,
            is_mentioned=is_mentioned,
            ensure_access_and_reward=ensure_access_and_reward,
            on_template_contribution=on_template_contribution,
            on_photo_idle=on_photo_idle,
            handle_media_message_fn=handle_media_message_fn,
        )

    handler.__name__ = handler_name
    for decorator in decorators:
        handler = decorator(handler)
    handler.__name__ = handler_name
    return handler
