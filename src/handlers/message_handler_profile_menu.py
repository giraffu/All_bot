from src.logger import logger


TASK_TYPE_DISPLAY_NAMES = {
    "img2img": "task.img2img",
    "img2img_lora": "task.img2img_lora",
    "i2i_pro": "task.i2i_pro",
    "free_edit_v2": "task.mode_free_edit_v2",
    "face_swap": "task.face_swap",
    "img2video_group": "task.mode_video_lora",
    "wan22_video_v2": "task.mode_wan22_video_v2",
    "scail2_video_replacement": "task.mode_scail2_video_replacement",
    "scail2_action_transfer": "task.mode_scail2_action_transfer",
    "scail2_action_transfer_long": "task.mode_scail2_action_transfer",
    "scail2_face_swap_v2": "task.mode_scail2_face_swap_v2",
    "face_video": "task.face_video",
    "ltx_video": "task.ltx_video",
    "t2i-pornmaster-turbo": "task.t2i_pornmaster_turbo",
}


async def handle_personal_center_impl(
    update,
    context,
    *,
    build_payload,
    reply_with_async_payload,
    reply_text,
    invite_link: str,
    web_url: str,
):
    user = update.effective_user
    if not user:
        return None
    return await reply_with_async_payload(
        update,
        reply_text=reply_text,
        build_payload=build_payload,
        context=context,
        user=user,
        invite_link=invite_link,
        web_url=web_url,
    )


async def handle_checkin_impl(
    update,
    context,
    *,
    refuge_group_id,
    get_reply_message,
    get_checkin_gate_reply,
    build_checkin_reply,
    reply_text,
):
    message = get_reply_message(update)
    if not message:
        return None

    gate_reply = await get_checkin_gate_reply(update, context, refuge_group_id)
    if gate_reply:
        if gate_reply[0] == "__warning__":
            logger.warning(f"Failed to check refuge group membership: {gate_reply[1]}")
        else:
            msg, reply_markup = gate_reply
            await reply_text(
                message,
                msg,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return None

    msg = await build_checkin_reply(update, context)
    if not msg:
        return None
    await reply_text(message, msg, parse_mode="Markdown")
    return None


async def handle_share_impl(
    update,
    context,
    *,
    build_payload,
    reply_with_async_payload,
    reply_text,
):
    user = update.effective_user
    if not user:
        return None
    return await reply_with_async_payload(
        update,
        reply_text=reply_text,
        build_payload=build_payload,
        context=context,
        user=user,
    )


async def handle_switch_lang_impl(
    update,
    context,
    *,
    build_payload,
    reply_with_async_payload,
    reply_text,
):
    user = update.effective_user
    if not user:
        return None
    return await reply_with_async_payload(
        update,
        reply_text=reply_text,
        build_payload=build_payload,
        parse_mode=None,
        context=context,
        user=user,
    )


async def handle_queue_status_impl(
    update,
    context,
    *,
    build_payload,
    reply_with_async_payload,
    reply_text,
    task_type_display_names,
):
    user = update.effective_user
    if not user:
        return None
    return await reply_with_async_payload(
        update,
        reply_text=reply_text,
        build_payload=build_payload,
        context=context,
        user=user,
        task_type_display_names=task_type_display_names,
    )
