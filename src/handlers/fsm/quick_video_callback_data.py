QUICK_VIDEO_MODE_CALLBACK_PREFIX = "qvid_mode:"
QUICK_VIDEO_SCENE_CALLBACK_PREFIX = "qvid_scene:"

QUICK_VIDEO_MODE_KEYS = (
    "menu.video_edit_missionary",
    "menu.video_edit_doggy",
    "menu.video_edit_blowjob",
    "menu.video_edit_undress_tongue",
    "menu.video_edit_closeup_blowjob",
)

QUICK_VIDEO_ENTRY_CALLBACK_PATTERN = (
    r"^(?:qvid_scene:[A-Za-z0-9_-]{1,32}|"
    r"qvid_mode:menu\.video_edit_"
    r"(?:missionary|doggy|blowjob|undress_tongue|closeup_blowjob))$"
)


def build_quick_video_mode_callback_data(route_key: str) -> str:
    return f"{QUICK_VIDEO_MODE_CALLBACK_PREFIX}{route_key}"


def build_quick_video_scene_callback_data(scene_id: str) -> str:
    return f"{QUICK_VIDEO_SCENE_CALLBACK_PREFIX}{scene_id}"


def parse_quick_video_mode_callback_data(data: str | None) -> str | None:
    if not data or not data.startswith(QUICK_VIDEO_MODE_CALLBACK_PREFIX):
        return None
    route_key = data[len(QUICK_VIDEO_MODE_CALLBACK_PREFIX) :]
    if route_key not in QUICK_VIDEO_MODE_KEYS:
        return None
    return route_key


def parse_quick_video_scene_callback_data(data: str | None) -> str | None:
    if not data or not data.startswith(QUICK_VIDEO_SCENE_CALLBACK_PREFIX):
        return None
    scene_id = data[len(QUICK_VIDEO_SCENE_CALLBACK_PREFIX) :]
    if not scene_id or len(scene_id) > 32:
        return None
    if not all(char.isalnum() or char in {"_", "-"} for char in scene_id):
        return None
    return scene_id
