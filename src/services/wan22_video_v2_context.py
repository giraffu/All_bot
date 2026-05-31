from typing import Any

DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT = (
    "censored, mosaic censoring, bar censor, pixelated, glowing, bloom, blurry, "
    "out of focus, low detail, bad anatomy, ugly, overexposed, underexposed, "
    "distorted face, extra limbs, cartoonish, 3d render artifacts, duplicate "
    "people, unnatural lighting, bad composition, missing shadows, low "
    "resolution, poorly textured, glitch, noise, grain, static, motionless, "
    "still frame, stylized, artwork, painting, illustration, many people in "
    "background, three legs, walking backward, unnatural skin tone, discolored "
    "eyelid, red eyelids, closed eyes, poorly drawn hands, extra fingers, fused "
    "fingers, poorly drawn face, deformed, disfigured, malformed limbs, fog, "
    "mist, voluminous eyelashes,"
)


def normalize_wan22_video_v2_negative_prompt(negative_prompt: str | None) -> str:
    normalized = (negative_prompt or "").strip()
    return normalized or DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT


def normalize_wan22_video_v2_chain_task_ids(chain_task_ids: Any) -> list[str]:
    if not isinstance(chain_task_ids, (list, tuple)):
        return []
    normalized: list[str] = []
    for value in chain_task_ids:
        task_id = str(value or "").strip()
        if task_id:
            normalized.append(task_id)
    return normalized
