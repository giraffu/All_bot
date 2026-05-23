from enum import IntEnum, auto


class FaceVideoState(IntEnum):
    """视频换脸流程的状态枚举"""

    WAIT_FACE_IMAGE = auto()
    WAIT_VIDEO = auto()
    SELECT_RESOLUTION = auto()


class EditImageState(IntEnum):
    """自由P图/幻想换脸流程的状态枚举"""

    WAIT_LORA_SELECTION = auto()
    WAIT_REFERENCE_IMAGES = auto()
    WAIT_PROMPT = auto()


class FaceSwapState(IntEnum):
    """双人换脸流程的状态枚举"""

    WAIT_FACE_IMAGE = auto()
    WAIT_BODY_IMAGE = auto()


class CustomVideoState(IntEnum):
    """自定义视频流程的状态枚举"""

    WAIT_IMAGE = auto()
    WAIT_SETTINGS_AND_PROMPT = auto()


class LtxVideoState(IntEnum):
    WAIT_IMAGE = auto()
    WAIT_SETTINGS_AND_PROMPT = auto()
    WAIT_CONFIRMATION = auto()


class ImageToVideoState(IntEnum):
    """统一图生视频流程的状态枚举"""

    WAIT_LORA_SELECTION = auto()
    WAIT_IMAGE = auto()
    WAIT_SETTINGS_AND_PROMPT = auto()


# Deprecated compatibility alias retained for legacy imports.
VideoLoraState = ImageToVideoState


class QuickImageState(IntEnum):
    """懒人P图 (脱衣/自慰/随机换脸) 状态枚举"""

    WAIT_IMAGE = auto()


class QuickVideoState(IntEnum):
    """懒人动图 (传教士/后入/口交等) 状态枚举"""

    WAIT_IMAGE = auto()
    WAIT_SETTINGS = auto()


class AffiliateRedeemState(IntEnum):
    """返佣兑换流程状态枚举"""

    WAIT_CREDITS_AMOUNT = auto()


class CommonState(IntEnum):
    """通用的 ConversationHandler 状态，比如超时"""

    TIMEOUT = auto()
