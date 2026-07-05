from src.services import advanced_video_settings_view_service as service


def _t(key: str, **kwargs) -> str:
    if key == "app.credits":
        return "灵石"
    if key in {
        "fsm.image_to_video.disable_end_frame",
        "fsm.wan22_video_v2.disable_end_frame",
    }:
        return "单首帧"
    if key in {
        "fsm.image_to_video.enable_end_frame",
        "fsm.wan22_video_v2.enable_end_frame",
    }:
        return "首尾帧"
    if key in {
        "fsm.image_to_video.frame_mode_end",
        "fsm.wan22_video_v2.frame_mode_end",
    }:
        return "首尾帧"
    if key in {
        "fsm.image_to_video.frame_mode_single",
        "fsm.wan22_video_v2.frame_mode_single",
    }:
        return "单首帧"
    if key == "fsm.image_to_video.mode_header":
        return "普通图生视频"
    if key == "fsm.image_to_video.compat_mode_header":
        return "兼容图生视频"
    if key == "fsm.image_to_video.setup_text":
        return (
            f"i2v:{kwargs['header']}:{kwargs['model_name']}:"
            f"{kwargs['resolution']}:{kwargs['duration']}:{kwargs['cost']}"
        )
    if key == "fsm.image_to_video.settings_text":
        return (
            f"i2v-settings:{kwargs['model_name']}:"
            f"{kwargs['resolution']}:{kwargs['duration']}:{kwargs['cost']}"
        )
    if key == "fsm.wan22_video_v2.setup_text":
        return (
            f"wan22-setup:{kwargs['frame_mode']}:"
            f"{kwargs['resolution']}:{kwargs['duration']}:{kwargs['cost']}"
        )
    if key in {
        "fsm.wan22_video_v2.settings_text",
        "fsm.wan22_video_v2.legacy_settings_text",
    }:
        return f"{key}:{kwargs['resolution_preset']}:{kwargs['cost']}"
    if key == "fsm.wan22_video_v2.submit_button":
        return "提交"
    if key == "fsm.wan22_video_v2.status_yes":
        return "是"
    if key == "fsm.wan22_video_v2.status_no":
        return "否"
    if key == "fsm.image_to_video.current_lora":
        return f"当前附加模型: {kwargs['model_name']}"
    if key == "fsm.ltx_video.settings_text_english_prompt":
        return (
            f"ltx-settings:{kwargs['resolution']}:{kwargs['duration']}:{kwargs['cost']}"
        )
    return key


def _callback_data(view):
    return [
        button.callback_data
        for row in view.reply_markup.inline_keyboard
        for button in row
    ]


def _button_texts(view):
    return [button.text for row in view.reply_markup.inline_keyboard for button in row]


def test_image_to_video_initial_setup_view_keeps_lora_mode_resolution_and_duration():
    fsm_data = {
        "lora_name": "BreastGrow",
        "allow_lora_selection": True,
        "resolution": "hd",
        "duration": "8s",
        "use_end_frame": True,
    }

    view = service.build_image_to_video_initial_setup_view(
        fsm_data,
        lang="zh",
        translate_func=_t,
        from_compat_alias=False,
    )

    assert view.resolution == "hd"
    assert view.duration == 8
    assert view.cost == 60
    assert "i2v_setup_confirm" not in _callback_data(view)
    assert "i2v_setup_lora_BreastGrow" in _callback_data(view)
    assert "i2v_setup_mode_end" in _callback_data(view)
    assert any(text.startswith("✅ 巨乳膨胀") for text in _button_texts(view))
    assert view.message_text == "i2v:普通图生视频:巨乳膨胀:高清（约 810p）:8 秒:60"


def test_image_to_video_settings_view_uses_generation_setting_callbacks():
    fsm_data = {"resolution": "standard", "duration": 10, "lora_name": ""}

    view = service.build_image_to_video_settings_view(
        fsm_data,
        lang="zh",
        translate_func=_t,
    )

    assert view.cost == 60
    assert "set_res_hd" in _callback_data(view)
    assert "set_dur_10" in _callback_data(view)
    assert view.message_text == "i2v-settings:无:标准（约 720p）:10 秒:60"


def test_apply_wan22_video_settings_callback_updates_selected_values():
    data = {"resolution": "preview", "duration": 5}

    handled_res = service.apply_wan22_video_settings_callback(
        data,
        callback_data="set_res_hd",
        resolution_prefix="set_res_",
        duration_prefix="set_dur_",
        resolution_key="resolution",
    )
    handled_dur = service.apply_wan22_video_settings_callback(
        data,
        callback_data="set_dur_10",
        resolution_prefix="set_res_",
        duration_prefix="set_dur_",
        resolution_key="resolution",
    )

    assert handled_res is True
    assert handled_dur is True
    assert data["resolution"] == "hd"
    assert data["duration"] == 10


def test_apply_wan22_video_settings_callback_ignores_unknown_data():
    data = {"resolution_preset": "preview", "duration": 5}

    handled = service.apply_wan22_video_settings_callback(
        data,
        callback_data="wan22v2_submit",
        resolution_prefix="wan22v2_res_",
        duration_prefix="wan22v2_dur_",
        resolution_key="resolution_preset",
    )

    assert handled is False
    assert data == {"resolution_preset": "preview", "duration": 5}


def test_apply_ltx_video_settings_callback_updates_selected_values():
    data = {"resolution": "1280x704", "duration": "5s"}

    handled_res = service.apply_ltx_video_settings_callback(
        data,
        callback_data="set_ltxres_768x512",
    )
    handled_dur = service.apply_ltx_video_settings_callback(
        data,
        callback_data="set_ltxdur_10s",
    )

    assert handled_res is True
    assert handled_dur is True
    assert data == {"resolution": "768x512", "duration": "10s"}


def test_wan22_views_keep_setup_and_legacy_settings_shapes():
    setup_view = service.build_wan22_initial_setup_view(
        {"resolution_preset": "preview", "duration": 5, "use_end_frame": False},
        lang="zh",
        translate_func=_t,
    )
    settings_view = service.build_wan22_settings_view(
        {
            "resolution_preset": "preview",
            "duration": 5,
            "use_end_frame": False,
            "end_image_path": None,
            "prompt": "positive",
            "negative_prompt": "",
        },
        lang="zh",
        translate_func=_t,
        is_legacy_context=True,
    )

    assert setup_view.message_text == "wan22-setup:单首帧:极速（约 512p）:5 秒:6"
    assert "wan22v2_setup_res_hd" in _callback_data(setup_view)
    assert "wan22v2_setup_confirm" not in _callback_data(setup_view)
    assert settings_view.message_text == (
        "fsm.wan22_video_v2.legacy_settings_text:极速（约 512p）:6"
    )
    assert "wan22v2_submit" in _callback_data(settings_view)
    assert any(text.startswith("• 极速") for text in _button_texts(settings_view))


def test_ltx_initial_setup_view_keeps_extension_direct_prompt_copy_and_no_confirm():
    view = service.build_ltx_initial_setup_view(
        {
            "resolution": "1280x704",
            "duration": "10s",
            "ltx_mode": "i2v",
            "is_extension": True,
        },
        lang="zh",
        translate_func=_t,
        lora_items=[
            {
                "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                "strength": 0.8,
            }
        ],
    )

    assert view.cost == 20
    assert "ltx_setup_confirm" not in _callback_data(view)
    assert "ltx_mode_i2v" in _callback_data(view)
    assert "set_ltxdur_10s" in _callback_data(view)
    assert "已载入上一段尾帧" in view.message_text
    assert "直接发送提示词" in view.message_text
    assert "运动逻辑优化(0.80)" in view.message_text


def test_ltx_prompt_settings_view_uses_permission_keyboard_and_lora_summary():
    view = service.build_ltx_prompt_settings_view(
        {"resolution": "1280x704", "duration": "10s"},
        lang="zh",
        translate_func=_t,
        user_group="default",
        user_identity="外门弟子",
        lora_items=[],
    )

    assert view.cost == 20
    assert "set_ltxres_1280x704" in _callback_data(view)
    assert "set_ltxdur_20s" in _callback_data(view)
    assert view.message_text == "ltx-settings:1280x704:10s:20\n\n当前附加模型: 无"
