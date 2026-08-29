from enum import IntEnum, auto


class Scail2VideoState(IntEnum):
    """SCAIL-2 视频生视频流程的状态枚举"""

    WAIT_REFERENCE_IMAGE = auto()
    WAIT_MOTION_VIDEO = auto()
    WAIT_PROMPT = auto()
    WAIT_DURATION = auto()


class EditImageState(IntEnum):
    """自由P图/幻想换脸流程的状态枚举"""

    WAIT_LORA_SELECTION = auto()
    WAIT_REFERENCE_IMAGES = auto()
    WAIT_PROMPT = auto()


class FaceSwapState(IntEnum):
    """双人换脸流程的状态枚举"""

    WAIT_FACE_IMAGE = auto()
    WAIT_BODY_IMAGE = auto()


class LtxVideoState(IntEnum):
    WAIT_LORA_SELECTION = auto()
    WAIT_MODE_SELECTION = auto()
    WAIT_IMAGE = auto()
    WAIT_END_IMAGE = auto()
    WAIT_SETTINGS_AND_PROMPT = auto()
    WAIT_CONFIRMATION = auto()


class AdvancedVideoProState(IntEnum):
    WAIT_SETTINGS = auto()
    WAIT_MEDIA = auto()
    WAIT_REFERENCE_DESCRIPTION = auto()
    WAIT_REFERENCE_AUDIO = auto()
    WAIT_PROMPT = auto()
    WAIT_CONFIRMATION = auto()


class ImageToVideoState(IntEnum):
    """统一图生视频流程的状态枚举"""

    WAIT_LORA_SELECTION = auto()
    WAIT_IMAGE = auto()
    WAIT_END_FRAME_CHOICE = auto()
    WAIT_END_IMAGE = auto()
    WAIT_SETTINGS_AND_PROMPT = auto()


class Wan22VideoV2State(IntEnum):
    """图生视频 v2 流程状态枚举"""

    WAIT_SETUP = auto()
    WAIT_START_IMAGE = auto()
    WAIT_END_FRAME_CHOICE = auto()
    WAIT_END_IMAGE = auto()
    WAIT_PROMPT = auto()
    WAIT_NEGATIVE_PROMPT = auto()
    WAIT_SETTINGS = auto()


class Txt2ImgState(IntEnum):
    """文生图流程状态枚举"""

    WAIT_PROMPT = auto()


class QuickImageState(IntEnum):
    """懒人P图 (脱衣/自慰/随机换脸) 状态枚举"""

    WAIT_IMAGE = auto()


class QuickVideoState(IntEnum):
    """懒人动图 (传教士/后入/口交等) 状态枚举"""

    WAIT_REFERENCE_TEMPLATE_UPLOAD = auto()
    WAIT_IMAGE = auto()
    WAIT_SETTINGS = auto()


class AffiliateRedeemState(IntEnum):
    """返佣兑换流程状态枚举"""

    WAIT_CREDITS_AMOUNT = auto()
    WAIT_USDT_AMOUNT = auto()
    WAIT_USDT_ADDRESS = auto()
    WAIT_USDT_CONFIRM = auto()
