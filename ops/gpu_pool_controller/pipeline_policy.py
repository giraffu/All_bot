from __future__ import annotations


FAST_IMAGE_PIPELINE_POLICY = "image_claim3_comfy2_delivery1_v1"
MEDIA_PIPELINE_POLICY = "media_claim2_comfy1_delivery1_v1"
LEGACY_BF16_LAN_PIPELINE_POLICY = "bf16_lan_claim3_comfy2_delivery1"

FAST_IMAGE_PIPELINE_PROFILES = frozenset(
    {
        "img2img",
        "img2img_lora",
        "i2i_pro",
        "pornmaster_flux2_edit_bf16",
    }
)
MEDIA_PIPELINE_PROFILES = frozenset(
    {
        "all",
        "image_to_video",
        "ltx_video",
        "ltx_t2v",
        "scail2",
        "wan22_video_v2",
    }
)


def pipeline_policy_for_profile(profile: str) -> str:
    normalized = str(profile or "").strip()
    if normalized in FAST_IMAGE_PIPELINE_PROFILES:
        return FAST_IMAGE_PIPELINE_POLICY
    if normalized in MEDIA_PIPELINE_PROFILES:
        return MEDIA_PIPELINE_POLICY
    return ""


def pipeline_environment_for_profile(profile: str) -> dict[str, str]:
    policy = pipeline_policy_for_profile(profile)
    if not policy:
        return {}
    return {
        "PIPELINE_PROFILE_POLICY": policy,
        # These conservative numeric values preserve serial behavior if an old
        # image is restored. New images resolve the profile policy above into
        # the effective fast-image or media slot limits.
        "PIPELINE_MAX_RUNNING_TASKS": "1",
        "PIPELINE_MAX_CLAIMED_TASKS": "2",
        "PIPELINE_DELIVERY_CONCURRENCY": "1",
    }
