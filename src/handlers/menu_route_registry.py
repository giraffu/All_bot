"""Menu route keys that need reverse text matching outside prompt decorators."""

from collections.abc import Iterable

FSM_MENU_KEYS = (
    "menu.cancel",
    "menu.exit",
    "menu.main_menu",
    "menu.back_main",
    "menu.lazy_bot",
    "menu.open_lazy_bot",
    "menu.photo_edit",
    "menu.video_edit",
    "menu.open_main_bot",
    "qqcc.menu.quick_faceswap",
    "qqcc.menu.ai_draw",
    "qqcc.menu.ai_filter",
    "qqcc.menu.market",
    "menu.face_video",
    "menu.video_to_video",
    "menu.video_to_video_replacement",
    "menu.video_to_video_action_transfer",
    "menu.txt2img",
    "menu.i2i_pro",
    "menu.free_edit",
    "menu.free_edit_v2",
    "menu.video_lora",
    "menu.custom_video",
    "menu.ltx_video",
    "menu.wan22_video_v2",
    "menu.photo_edit_undress",
    "menu.photo_edit_faceswap",
    "menu.photo_edit_masturbation",
    "menu.photo_edit_random_faceswap",
    "menu.video_edit_missionary",
    "menu.video_edit_doggy",
    "menu.video_edit_blowjob",
    "menu.video_edit_undress_tongue",
    "menu.video_edit_closeup_blowjob",
)

SPECIAL_TRANSLATION_ROUTES = (
    ("menu.video_lora", "menu.video_lora"),
    ("qqcc.menu.video_edit", "menu.video_edit"),
    ("qqcc.menu.ai_draw", "qqcc.menu.ai_draw"),
    ("qqcc.menu.ai_filter", "qqcc.menu.ai_filter"),
    ("qqcc.menu.quick_faceswap", "qqcc.menu.quick_faceswap"),
    ("qqcc.menu.market", "qqcc.menu.market"),
)
SPECIAL_TRANSLATION_ROUTE_KEYS = tuple(
    route_key for _translation_key, route_key in SPECIAL_TRANSLATION_ROUTES
)

LEGACY_TEXT_ALIASES = {
    "🏆 发现/排行榜": "menu.gallery",
    "💰 个人中心": "menu.profile",
    "👤 个人中心": "menu.profile",
    "🎬 懒人动图": "menu.video_edit",
    "AI动图": "menu.video_edit",
    "AI绘图": "qqcc.menu.ai_draw",
    "AI滤镜": "qqcc.menu.ai_filter",
    "快速换脸": "qqcc.menu.quick_faceswap",
    "懒人bot": "menu.lazy_bot",
    "懒人Bot": "menu.lazy_bot",
    "🖼️ 懒人P图": "menu.photo_edit",
    "🎬 自定义图生视频": "menu.custom_video",
    "自定义图生视频": "menu.custom_video",
}


def build_global_reverse_route_keys(
    registered_route_keys: Iterable[str],
) -> set[str]:
    return set(registered_route_keys).union(FSM_MENU_KEYS)
