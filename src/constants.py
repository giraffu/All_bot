import os

# Directories
TMP_DIR = os.path.abspath("./tg_tmp")
TEMPLATE_DIR_PENETRATION = os.path.abspath("./templates/penetration")
TEMPLATE_DIR_QUICK_FACE = os.path.abspath("./templates/quick_face")
TEMPLATE_DIR_VIDEO_NICE = os.path.abspath("./templates/video_nice")
TEMP_TEMPLATE_DIR = os.path.abspath("./templates/temps")

# Main Menu Keyboard definition removed. Use src.i18n.keyboards.get_main_menu_keyboard instead.

# Modes
MODE_EDIT = "edit"
MODE_UNDRESS = "undress"
MODE_MASTURBATION = "masturbation"
MODE_FACESWAP_STEP1 = "faceswap_step1"
MODE_FACESWAP_STEP2 = "faceswap_step2"
MODE_FACE_VIDEO_STEP1 = "face_video_step1"
MODE_FACE_VIDEO_STEP2 = "face_video_step2"
MODE_RANDOM_FACESWAP = "random_faceswap"
MODE_PENETRATION_STEP1 = "penetration_step1"
MODE_PENETRATION_STEP2 = "penetration_step2"
MODE_PERFECT_VIDEO_INSERT = "perfect_video_insert"
MODE_DOGGY_STYLE = "doggy_style"
MODE_BLOWJOB = "blowjob"
MODE_UNDRESS_TONGUE = "undress_tongue"
MODE_CLOSEUP_BLOWJOB = "closeup_blowjob"
MODE_CUSTOM_VIDEO = "custom_video"
MODE_VIDEO_LORA = "video_lora"
# Neutral semantic alias for the unified image-to-video capability.
# Keep the underlying value on the legacy video_lora string during the compat phase.
MODE_IMAGE_TO_VIDEO = MODE_VIDEO_LORA
MODE_LTX_VIDEO = "ltx_video"
MODE_TXT2IMG = "txt2img"
MODE_I2I_PRO = "i2i_pro"
MODE_I2I_DRAW = "i2i_draw"
MODE_IMG2IMG_LORA = "img2img_lora"
MODE_TEMPLATE_CONTRIBUTE = "template_contribute"
MODE_NONE = "none"

# Mode Name Mapping (Human Readable)
MODE_NAME_MAP = {
    MODE_EDIT: "task.mode_edit",
    MODE_I2I_PRO: "task.mode_i2i_pro",
    MODE_I2I_DRAW: "task.mode_i2i_draw",
    MODE_IMG2IMG_LORA: "task.mode_img2img_lora",
    MODE_UNDRESS: "task.mode_undress",
    MODE_MASTURBATION: "task.mode_masturbation",
    MODE_FACESWAP_STEP1: "task.mode_faceswap_step1",
    MODE_FACESWAP_STEP2: "task.mode_faceswap_step2",
    MODE_FACE_VIDEO_STEP1: "task.mode_face_video_step1",
    MODE_FACE_VIDEO_STEP2: "task.mode_face_video_step2",
    MODE_RANDOM_FACESWAP: "task.mode_random_faceswap",
    MODE_PENETRATION_STEP1: "task.mode_penetration_step1",
    MODE_PENETRATION_STEP2: "task.mode_penetration_step2",
    MODE_PERFECT_VIDEO_INSERT: "task.mode_perfect_video_insert",
    MODE_DOGGY_STYLE: "task.mode_doggy_style",
    MODE_BLOWJOB: "task.mode_blowjob",
    MODE_UNDRESS_TONGUE: "task.mode_undress_tongue",
    MODE_CLOSEUP_BLOWJOB: "task.mode_closeup_blowjob",
    MODE_CUSTOM_VIDEO: "task.mode_custom_video",
    MODE_LTX_VIDEO: "task.mode_ltx_video",
    MODE_TXT2IMG: "task.mode_txt2img",
    MODE_IMAGE_TO_VIDEO: "task.mode_video_lora",
    MODE_TEMPLATE_CONTRIBUTE: "task.mode_template_contribute",
    MODE_NONE: "task.mode_none",
}

# Task Costs (Credits)
TASK_COSTS = {
    MODE_EDIT: 2,
    MODE_UNDRESS: 2,
    MODE_MASTURBATION: 2,
    MODE_FACESWAP_STEP1: 1,
    MODE_PENETRATION_STEP1: 2,
    MODE_RANDOM_FACESWAP: 1,
    MODE_BLOWJOB: 6,
    MODE_UNDRESS_TONGUE: 6,
    MODE_DOGGY_STYLE: 6,
    MODE_PERFECT_VIDEO_INSERT: 6,
    MODE_CLOSEUP_BLOWJOB: 6,
    MODE_CUSTOM_VIDEO: 6,
    MODE_LTX_VIDEO: 10,
    MODE_TXT2IMG: 2,
    MODE_IMAGE_TO_VIDEO: 6,
    MODE_I2I_PRO: 6,
    MODE_I2I_DRAW: 3,
    MODE_IMG2IMG_LORA: 6,
}

# Default Video Resolutions based on User Group
VIDEO_RESOLUTIONS = {
    "真传弟子": (720, 720),
    "核心弟子": (720, 720),
    "内门弟子": (720, 720),
    "元婴期": (720, 720),
    "金丹期": (720, 720),
    "筑基期": (720, 720),
    "default": (512, 512),
}

DEFAULT_RESOLUTION = "512p"
DEFAULT_DURATION = "5s"

# Task Limits
MAX_CONCURRENT_TASKS = 3

# TON Payment Constants
TON_TO_NANOTON = 1_000_000_000
TON_SLIPPAGE_NANOTON = 10_000_000  # 0.01 TON allowed slippage
TON_RECEIVER_ADDRESS = "UQC2q_W2d061mO_g3zB-hK12v0p2u44-nI5z9F82L1j88g7b"

# Commission Settings
COMMISSION_RATE = 0.10

RESOLUTION_PERMISSIONS = {
    "凡人": ["512p"],
    "外门弟子": ["512p"],
    "练气期": ["512p"],
    "筑基期": ["512p", "720p"],
    "金丹期": ["512p", "720p", "1024p"],
    "元婴期": ["512p", "720p", "1024p"],
    "内门弟子": ["512p", "720p"],
    "核心弟子": ["512p", "720p", "1024p"],
    "真传弟子": ["512p", "720p", "1024p"],
}

DURATION_PERMISSIONS = {
    "凡人": ["5s"],
    "外门弟子": ["5s"],
    "练气期": ["5s"],
    "筑基期": ["5s", "8s"],
    "金丹期": ["5s", "8s", "10s"],
    "元婴期": ["5s", "8s", "10s"],
    "内门弟子": ["5s", "8s"],
    "核心弟子": ["5s", "8s", "10s"],
    "真传弟子": ["5s", "8s", "10s"],
}

FAVORITE_LIMITS_BY_IDENTITY = {
    "外门弟子": 100,
    "内门弟子": 300,
    "核心弟子": 600,
    "真传弟子": 1000,
}

DEFAULT_FAVORITE_LIMIT = FAVORITE_LIMITS_BY_IDENTITY["外门弟子"]

# Forbidden words for public sharing
FORBIDDEN_WORDS = [
    "小男孩",
    "小女孩",
    "男童",
    "女童",
    "幼女",
    "幼童",
    "儿童",
    "小孩",
    "婴儿",
    "萝莉",
    "正太",
    "boy",
    "girl",
    "child",
    "children",
    "kid",
    "kids",
    "toddler",
    "baby",
    "loli",
    "shota",
]


RESOLUTION_COST = {"512p": 6, "720p": 18, "1024p": 36}

LTX_RESOLUTION_COST = {"1280x704": 10}

DURATION_MULTIPLIER = {"5s": 1.0, "8s": 2.0, "10s": 3.0}

LTX_DURATION_MULTIPLIER = {"5s": 1.0, "10s": 2.0, "15s": 3.0, "20s": 4.0}

DURATION_FRAMES = {"5s": 81, "8s": 129, "10s": 161}


def get_video_settings_keyboard(
    user_group: str,
    user_identity: str = "外门弟子",
    current_resolution: str = DEFAULT_RESOLUTION,
    current_duration: str = DEFAULT_DURATION,
    lang: str = "zh",
):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from src.i18n.translator import get_text

    group_res_allowed = RESOLUTION_PERMISSIONS.get(user_group, ["512p"])
    identity_res_allowed = RESOLUTION_PERMISSIONS.get(user_identity, ["512p"])
    allowed_resolutions = list(set(group_res_allowed + identity_res_allowed))

    group_dur_allowed = DURATION_PERMISSIONS.get(user_group, ["5s"])
    identity_dur_allowed = DURATION_PERMISSIONS.get(user_identity, ["5s"])
    allowed_durations = list(set(group_dur_allowed + identity_dur_allowed))

    keyboard = []

    credits_text = get_text("app.credits", lang)

    # Resolution row
    res_row = []
    for res in ["512p", "720p", "1024p"]:
        if res in allowed_resolutions:
            if res == "1024p" and current_duration == "10s":
                continue  # Prevent 1024p when 10s is selected

            base_cost = RESOLUTION_COST.get(res, 6)
            multiplier = DURATION_MULTIPLIER.get(current_duration, 1.0)
            cost = int(base_cost * multiplier)
            display_text = f"{res} ({cost}{credits_text})"
            text = f"✅ {display_text}" if res == current_resolution else display_text
            callback_data = f"set_res_{res}"
            res_row.append(InlineKeyboardButton(text, callback_data=callback_data))

    if res_row:
        keyboard.append(res_row)

    # Duration row
    dur_row = []
    for dur in ["5s", "8s", "10s"]:
        if dur in allowed_durations:
            if dur == "10s" and current_resolution == "1024p":
                continue  # Prevent 10s when 1024p is selected

            multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
            display_text = f"{dur} (x{multiplier})"
            text = f"✅ {display_text}" if dur == current_duration else display_text
            callback_data = f"set_dur_{dur}"
            dur_row.append(InlineKeyboardButton(text, callback_data=callback_data))

    if dur_row:
        keyboard.append(dur_row)

    return InlineKeyboardMarkup(keyboard)


def get_ltx_video_settings_keyboard(
    user_group: str,
    user_identity: str = "外门弟子",
    current_resolution: str = "1280x704",
    current_duration: str = "5s",
    lang: str = "zh",
):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from src.i18n.translator import get_text

    # Temporarily hardcode permissions for LTX Video, or we can use the same logic if we extend DURATION_PERMISSIONS
    # For now, allow 5s, 10s, 15s, 20s based on groups.
    allowed_durations = ["5s", "10s", "15s", "20s"]

    keyboard = []

    credits_text = get_text("app.credits", lang)

    # Resolution row (Currently only one for LTX)
    res_row = []
    for res in ["1280x704"]:
        base_cost = 10
        multiplier = LTX_DURATION_MULTIPLIER.get(current_duration, 1.0)
        cost = int(base_cost * multiplier)
        display_text = f"{res} ({cost}{credits_text})"
        text = f"✅ {display_text}" if res == current_resolution else display_text
        callback_data = f"set_ltxres_{res}"
        res_row.append(InlineKeyboardButton(text, callback_data=callback_data))

    if res_row:
        keyboard.append(res_row)

    # Duration row
    dur_row = []
    for dur in allowed_durations:
        multiplier = LTX_DURATION_MULTIPLIER.get(dur, 1.0)
        display_text = f"{dur} (x{multiplier})"
        text = f"✅ {display_text}" if dur == current_duration else display_text
        callback_data = f"set_ltxdur_{dur}"
        dur_row.append(InlineKeyboardButton(text, callback_data=callback_data))

    if dur_row:
        # split duration into two rows to prevent overflow
        keyboard.append(dur_row[:2])
        keyboard.append(dur_row[2:])

    return InlineKeyboardMarkup(keyboard)


# Dynamic Priority Rules
# Format: "Group Name": [(limit_1, priority_1), (limit_2, priority_2), ...]
# Logic: if usage < limit_1 return priority_1, elif usage < limit_2 return priority_2... else return 0
DYNAMIC_PRIORITY_RULES = {
    "真传弟子": [(40, 45), (70, 20), (float("inf"), 1)],
    "核心弟子": [(30, 30), (60, 12), (float("inf"), 1)],
    "内门弟子": [(20, 20), (50, 8), (float("inf"), 1)],
    "元婴期": [(10, 12), (50, 5), (100, 1)],
    "金丹期": [(10, 8), (50, 3), (100, 1)],
    "筑基期": [(10, 5), (50, 1)],
    "练气期": [(10, 3), (50, 1)],
    "凡人": [],  # Always 0
    "外门弟子": [],  # Same as Mortal
}

# Task types that count towards daily usage limit
GENERATION_TASK_TYPES = [
    "image",
    "video",
    "face_swap",
    "undress",
    "masturbation",
    MODE_EDIT,
    MODE_CUSTOM_VIDEO,
    MODE_LTX_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_DOGGY_STYLE,
    MODE_BLOWJOB,
    MODE_UNDRESS_TONGUE,
    MODE_CLOSEUP_BLOWJOB,
    MODE_FACESWAP_STEP1,
    MODE_FACESWAP_STEP2,
    MODE_RANDOM_FACESWAP,
    MODE_FACE_VIDEO_STEP1,
    MODE_FACE_VIDEO_STEP2,
    MODE_PENETRATION_STEP1,
    MODE_PENETRATION_STEP2,
    MODE_TXT2IMG,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
]

VIDEO_TASK_TYPES = [
    "doggy_style",
    "perfect_video_insert",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
    "custom_video",
    "face_video",
    "face_video_step1",
    "face_video_step2",
    MODE_IMAGE_TO_VIDEO,
    "ltx_video",
    "video_edit",
    "perfect_video_edit",
    "txt2video",
    "video_insert",
]

# Web Access Allowed Roles
WEB_ACCESS_ALLOWED_IDENTITIES = ["内门弟子", "核心弟子", "真传弟子"]
WEB_ACCESS_ALLOWED_GROUPS = [
    "练气期",
    "筑基期",
    "金丹期",
    "元婴期",
    "化神期",
    "炼虚期",
    "合体期",
    "大乘期",
    "渡劫期",
]
