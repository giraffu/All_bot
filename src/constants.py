import os

# Directories
TMP_DIR = os.path.abspath("./tg_tmp")
TEMPLATE_DIR_PENETRATION = os.path.abspath("./templates/penetration")
TEMPLATE_DIR_QUICK_FACE = os.path.abspath("./templates/quick_face")
TEMPLATE_DIR_VIDEO_NICE = os.path.abspath("./templates/video_nice")
TEMP_TEMPLATE_DIR = os.path.abspath("./templates/temps")

# Modes
MODE_EDIT = "edit"
MODE_UNDRESS = "undress"
MODE_MASTURBATION = "masturbation"
MODE_FACESWAP_STEP1 = "faceswap_step1"
MODE_FACESWAP_STEP2 = "faceswap_step2"
MODE_RANDOM_FACESWAP = "random_faceswap"
MODE_PENETRATION_STEP1 = "penetration_step1"
MODE_PENETRATION_STEP2 = "penetration_step2"
MODE_PERFECT_VIDEO_INSERT = "perfect_video_insert"
MODE_DOGGY_STYLE = "doggy_style"
MODE_BLOWJOB = "blowjob"
MODE_UNDRESS_TONGUE = "undress_tongue"
MODE_CLOSEUP_BLOWJOB = "closeup_blowjob"
MODE_CUSTOM_VIDEO = "custom_video"
MODE_TEMPLATE_CONTRIBUTE = "template_contribute"
MODE_NONE = "none"

# Mode Name Mapping (Human Readable)
MODE_NAME_MAP = {
    MODE_EDIT: "自由P图",
    MODE_UNDRESS: "快速脱衣",
    MODE_MASTURBATION: "快速自慰",
    MODE_FACESWAP_STEP1: "快速换脸",
    MODE_FACESWAP_STEP2: "快速换脸",
    MODE_RANDOM_FACESWAP: "随机换脸",
    MODE_PENETRATION_STEP1: "快速抽插",
    MODE_PENETRATION_STEP2: "快速抽插",
    MODE_PERFECT_VIDEO_INSERT: "动图传教士",
    MODE_DOGGY_STYLE: "动图后入",
    MODE_BLOWJOB: "口交黑人",
    MODE_UNDRESS_TONGUE: "脱衣吐舌",
    MODE_CLOSEUP_BLOWJOB: "特写口交",
    MODE_CUSTOM_VIDEO: "自定义图生视频",
    MODE_TEMPLATE_CONTRIBUTE: "模板共建",
    MODE_NONE: "无模式"
}

# Task Costs (Credits)
TASK_COSTS = {
    MODE_EDIT: 2,
    MODE_UNDRESS: 2,
    MODE_MASTURBATION: 2,
    MODE_FACESWAP_STEP1: 2,
    MODE_PENETRATION_STEP1: 2,
    MODE_BLOWJOB: 6,
    MODE_UNDRESS_TONGUE: 6,
    MODE_DOGGY_STYLE: 6,
    MODE_PERFECT_VIDEO_INSERT: 6,
    MODE_CLOSEUP_BLOWJOB: 6,
    MODE_CUSTOM_VIDEO: 6,
}

# Default Video Resolutions based on User Group
VIDEO_RESOLUTIONS = {
    "筑基期": (720, 720),
    "default": (512, 512)
}

# Default Prompts Keys
PROMPT_KEYS = {
    MODE_BLOWJOB: "blowjob",
    MODE_UNDRESS_TONGUE: "undress_tongue",
    MODE_DOGGY_STYLE: "doggy_style",
    MODE_CLOSEUP_BLOWJOB: "closeup_blowjob",
    MODE_PERFECT_VIDEO_INSERT: "perfect_video_insert",
    MODE_UNDRESS: "undress",
    # Assuming masturbation uses undress or similar if not specified
    MODE_MASTURBATION: "masturbation" 
}
