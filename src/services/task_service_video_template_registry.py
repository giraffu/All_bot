from dataclasses import dataclass

from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_DOGGY_STYLE,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
)


@dataclass(frozen=True)
class VideoTemplateTaskSpec:
    mode: str
    default_prompt_key: str
    default_prompt_text: str


VIDEO_TEMPLATE_TASK_SPECS: dict[str, VideoTemplateTaskSpec] = {
    "blowjob": VideoTemplateTaskSpec(
        mode=MODE_BLOWJOB,
        default_prompt_key="blowjob",
        default_prompt_text="undress blowjob",
    ),
    "undress_tongue": VideoTemplateTaskSpec(
        mode=MODE_UNDRESS_TONGUE,
        default_prompt_key="undress_tongue",
        default_prompt_text="undress and show tongue",
    ),
    "doggy_style": VideoTemplateTaskSpec(
        mode=MODE_DOGGY_STYLE,
        default_prompt_key="doggy_style",
        default_prompt_text="doggy style sex",
    ),
    "closeup_blowjob": VideoTemplateTaskSpec(
        mode=MODE_CLOSEUP_BLOWJOB,
        default_prompt_key="closeup_blowjob",
        default_prompt_text="closeup blowjob sex",
    ),
    "perfect_video_insert": VideoTemplateTaskSpec(
        mode=MODE_PERFECT_VIDEO_INSERT,
        default_prompt_key="perfect_video_insert",
        default_prompt_text="missionary sex",
    ),
}
