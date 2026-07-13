QUICK_DRAW_SCENE_CALLBACK_PREFIX = "qdraw_scene:"
QUICK_DRAW_SCENE_CALLBACK_PATTERN = r"^qdraw_scene:[A-Za-z0-9_-]{1,32}$"
QUICK_FILTER_SCENE_CALLBACK_PREFIX = "qfilter_scene:"
QUICK_FILTER_SCENE_CALLBACK_PATTERN = r"^qfilter_scene:[A-Za-z0-9_-]{1,32}$"


def build_quick_draw_scene_callback_data(scene_id: str) -> str:
    return f"{QUICK_DRAW_SCENE_CALLBACK_PREFIX}{scene_id}"


def parse_quick_draw_scene_callback_data(data: str | None) -> str | None:
    if not data or not data.startswith(QUICK_DRAW_SCENE_CALLBACK_PREFIX):
        return None
    scene_id = data[len(QUICK_DRAW_SCENE_CALLBACK_PREFIX) :]
    if not scene_id or len(scene_id) > 32:
        return None
    if not all(char.isalnum() or char in {"_", "-"} for char in scene_id):
        return None
    return scene_id


def build_quick_filter_scene_callback_data(scene_id: str) -> str:
    return f"{QUICK_FILTER_SCENE_CALLBACK_PREFIX}{scene_id}"


def parse_quick_filter_scene_callback_data(data: str | None) -> str | None:
    if not data or not data.startswith(QUICK_FILTER_SCENE_CALLBACK_PREFIX):
        return None
    scene_id = data[len(QUICK_FILTER_SCENE_CALLBACK_PREFIX) :]
    if not scene_id or len(scene_id) > 32:
        return None
    if not all(char.isalnum() or char in {"_", "-"} for char in scene_id):
        return None
    return scene_id
