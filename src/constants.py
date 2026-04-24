import os

# Directories
TMP_DIR = os.path.abspath("./tg_tmp")
TEMPLATE_DIR_PENETRATION = os.path.abspath("./templates/penetration")
TEMPLATE_DIR_QUICK_FACE = os.path.abspath("./templates/quick_face")
TEMPLATE_DIR_VIDEO_NICE = os.path.abspath("./templates/video_nice")
TEMP_TEMPLATE_DIR = os.path.abspath("./templates/temps")

# Main Menu Keyboard
MAIN_MENU_KEYBOARD = [
    ["🏆 发现/排行榜", "💎 充值灵石", "📅 每日签到", "👤 个人中心"],
    ["🤝 分享赚灵石", "⏳ 排队状态"],
    ["🖼️ 懒人P图", "🎬 懒人动图", "🎬 视频换脸"],
    ["🌟 幻想换脸", "🎨 自由P图"],
    ["🎬 图生视频(附加模型)", "🎬 自定义图生视频", "🎬 高级图生视频"]
]

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
MODE_LTX_VIDEO = "ltx_video"
MODE_I2I_PRO = "i2i_pro"
MODE_IMG2IMG_LORA = "img2img_lora"
MODE_TEMPLATE_CONTRIBUTE = "template_contribute"
MODE_NONE = "none"

# Mode Name Mapping (Human Readable)
MODE_NAME_MAP = {
    MODE_EDIT: "自由P图",
    MODE_I2I_PRO: "幻想换脸",
    MODE_IMG2IMG_LORA: "图生图(附加模型)",
    MODE_UNDRESS: "快速脱衣",
    MODE_MASTURBATION: "快速自慰",
    MODE_FACESWAP_STEP1: "快速换脸",
    MODE_FACESWAP_STEP2: "快速换脸",
    MODE_FACE_VIDEO_STEP1: "视频换脸",
    MODE_FACE_VIDEO_STEP2: "视频换脸",
    MODE_RANDOM_FACESWAP: "随机换脸",
    MODE_PENETRATION_STEP1: "快速抽插",
    MODE_PENETRATION_STEP2: "快速抽插",
    MODE_PERFECT_VIDEO_INSERT: "动图传教士",
    MODE_DOGGY_STYLE: "动图后入",
    MODE_BLOWJOB: "口交黑人",
    MODE_UNDRESS_TONGUE: "脱衣吐舌",
    MODE_CLOSEUP_BLOWJOB: "特写口交",
    MODE_CUSTOM_VIDEO: "自定义图生视频",
    MODE_LTX_VIDEO: "高级图生视频",
    MODE_VIDEO_LORA: "图生视频(附加模型)",
    MODE_TEMPLATE_CONTRIBUTE: "模板共建",
    MODE_NONE: "无模式"
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
    MODE_VIDEO_LORA: 6,
    MODE_I2I_PRO: 6,
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
    "default": (512, 512)
}

DEFAULT_RESOLUTION = "512p"
DEFAULT_DURATION = "5s"

# Task Limits
MAX_CONCURRENT_TASKS = 3

# TON Payment Constants
TON_TO_NANOTON = 1_000_000_000
TON_SLIPPAGE_NANOTON = 10_000_000 # 0.01 TON allowed slippage

RESOLUTION_PERMISSIONS = {
    "凡人": ["512p"],
    "外门弟子": ["512p"],
    "练气期": ["512p"],
    "筑基期": ["512p", "720p"],
    "金丹期": ["512p", "720p", "1024p"],
    "元婴期": ["512p", "720p", "1024p"],
    "内门弟子": ["512p", "720p"],
    "核心弟子": ["512p", "720p", "1024p"],
    "真传弟子": ["512p", "720p", "1024p"]
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
    "真传弟子": ["5s", "8s", "10s"]
}

# Forbidden words for public sharing
FORBIDDEN_WORDS = [
    "小男孩", "小女孩", "男童", "女童", "幼女", "幼童", "儿童", "小孩", "婴儿", "萝莉", "正太",
    "boy", "girl", "child", "children", "kid", "kids", "toddler", "baby", "loli", "shota"
]


RESOLUTION_COST = {
    "512p": 6,
    "720p": 18,
    "1024p": 36
}

LTX_RESOLUTION_COST = {
    "1280x704": 10
}

DURATION_MULTIPLIER = {
    "5s": 1.0,
    "8s": 2.0,
    "10s": 3.0
}

LTX_DURATION_MULTIPLIER = {
    "5s": 1.0,
    "10s": 2.0,
    "15s": 3.0,
    "20s": 4.0
}

DURATION_FRAMES = {
    "5s": 81,
    "8s": 129,
    "10s": 161
}

def get_video_settings_keyboard(user_group: str, user_identity: str = "外门弟子", current_resolution: str = DEFAULT_RESOLUTION, current_duration: str = DEFAULT_DURATION):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    group_res_allowed = RESOLUTION_PERMISSIONS.get(user_group, ["512p"])
    identity_res_allowed = RESOLUTION_PERMISSIONS.get(user_identity, ["512p"])
    allowed_resolutions = list(set(group_res_allowed + identity_res_allowed))
    
    group_dur_allowed = DURATION_PERMISSIONS.get(user_group, ["5s"])
    identity_dur_allowed = DURATION_PERMISSIONS.get(user_identity, ["5s"])
    allowed_durations = list(set(group_dur_allowed + identity_dur_allowed))
    
    keyboard = []
    
    # Resolution row
    res_row = []
    for res in ['512p', '720p', '1024p']:
        if res in allowed_resolutions:
            if res == "1024p" and current_duration == "10s":
                continue # Prevent 1024p when 10s is selected
                
            base_cost = RESOLUTION_COST.get(res, 6)
            multiplier = DURATION_MULTIPLIER.get(current_duration, 1.0)
            cost = int(base_cost * multiplier)
            display_text = f"{res} ({cost}灵石)"
            text = f"✅ {display_text}" if res == current_resolution else display_text
            callback_data = f"set_res_{res}"
            res_row.append(InlineKeyboardButton(text, callback_data=callback_data))
    
    if res_row:
        keyboard.append(res_row)
        
    # Duration row
    dur_row = []
    for dur in ['5s', '8s', '10s']:
        if dur in allowed_durations:
            if dur == "10s" and current_resolution == "1024p":
                continue # Prevent 10s when 1024p is selected
                
            multiplier = DURATION_MULTIPLIER.get(dur, 1.0)
            display_text = f"{dur} (x{multiplier})"
            text = f"✅ {display_text}" if dur == current_duration else display_text
            callback_data = f"set_dur_{dur}"
            dur_row.append(InlineKeyboardButton(text, callback_data=callback_data))
            
    if dur_row:
        keyboard.append(dur_row)
        
    return InlineKeyboardMarkup(keyboard)

def get_ltx_video_settings_keyboard(user_group: str, user_identity: str = "外门弟子", current_resolution: str = "1280x704", current_duration: str = "5s"):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    # Temporarily hardcode permissions for LTX Video, or we can use the same logic if we extend DURATION_PERMISSIONS
    # For now, allow 5s, 10s, 15s, 20s based on groups.
    allowed_durations = ["5s", "10s", "15s", "20s"]
    
    keyboard = []
    
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
    "真传弟子": [(40, 45), (70, 20), (float('inf'), 1)],
    "核心弟子": [(30, 30), (60, 12), (float('inf'), 1)],
    "内门弟子": [(20, 20), (50, 8), (float('inf'), 1)],
    "元婴期": [(10, 12), (50, 5), (100, 1)],
    "金丹期": [(10, 8), (50, 3), (100, 1)],
    "筑基期": [(10, 5), (50, 1)],
    "练气期": [(10, 3), (50, 1)],
    "凡人": [], # Always 0
    "外门弟子": [] # Same as Mortal
}

# Task types that count towards daily usage limit
GENERATION_TASK_TYPES = [
    "image", "video", "face_swap", "undress", "masturbation",
    MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_LTX_VIDEO, MODE_VIDEO_LORA, MODE_PERFECT_VIDEO_INSERT,
    MODE_DOGGY_STYLE, MODE_BLOWJOB, MODE_UNDRESS_TONGUE, MODE_CLOSEUP_BLOWJOB,
    MODE_FACESWAP_STEP1, MODE_FACESWAP_STEP2, MODE_RANDOM_FACESWAP,
    MODE_FACE_VIDEO_STEP1, MODE_FACE_VIDEO_STEP2,
    MODE_PENETRATION_STEP1, MODE_PENETRATION_STEP2,
    MODE_I2I_PRO
]
