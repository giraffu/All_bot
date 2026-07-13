async def handle_prompt_impl(
    update,
    context,
    *,
    prompt_routes,
    ensure_user_access_reward,
    extract_prompt_message_text,
    dispatch_prompt_route,
    reply_private_prompt_fallback,
    reply_text,
    logger,
):
    user = update.effective_user
    if not user:
        return None

    await ensure_user_access_reward(context, user)

    message, text = extract_prompt_message_text(update)
    if not message:
        return None

    logger.info(f"handle_prompt received: {text.encode('utf-8')}")
    if not text:
        return None

    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

    route_matched, routed = await dispatch_prompt_route(
        update,
        context,
        text,
        prompt_routes=prompt_routes,
        reverse_map=GLOBAL_REVERSE_MAP,
    )
    if route_matched:
        return routed

    return await reply_private_prompt_fallback(
        message,
        lang=context.lang,
        reply_text=reply_text,
    )
