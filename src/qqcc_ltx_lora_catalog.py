"""QQCC Config-only LTX LoRA catalog.

The public LTX catalog intentionally remains in :mod:`src.lora_catalog`.  This
module extends it only for the authenticated QQCC configuration surface so the
extra choices never appear in the main Bot or public Web workbench.
"""

from __future__ import annotations

from src.lora_catalog import (
    LTX_VIDEO_LORA_DEFAULT_STRENGTHS,
    LTX_VIDEO_LORA_MODELS,
)


# These paths match the verified local model-registry bundle
# ltx23_explicit_lora_library/2026-07-17.  Keep the public catalog separate.
QQCC_LTX23_LIBRARY_MODELS: dict[str, tuple[str, float]] = {
    "ltx2.3/SexGod_Nudity_LTX23_v2_0.safetensors": ("自然裸体与写真姿势", 0.8),
    "ltx2.3/ltxdeepthroat_v01.safetensors": ("深喉", 1.0),
    "ltx2.3/epic_cumshots-V1-LTX_2_3-CUMSH0T.safetensors": ("射精/内射/面部液体", 0.8),
    "ltx2.3/nsfw_riding_backshot_frontshot_ltx23_v1.0.safetensors": ("牛仔/骑乘", 0.7),
    "ltx2.3/SexGod_Handjobs_LTX23_Rank64_v1.safetensors": ("手交", 0.8),
    "ltx2.3/cumonface_inmouth_LTX2.3.safetensors": ("射精/内射/面部液体（面部/口内）", 0.8),
    "ltx2.3/sfbehind_LTX2_3_v0_1.safetensors": ("后入", 1.0),
    "ltx2.3/nsfw_anal_insertion_ltx23_v1.0.safetensors": ("肛交插入/展示", 0.8),
    "ltx2.3/LTX-2.3 - Orgasm.safetensors": ("高潮与成人表情", 0.8),
    "ltx2.3/pussyjob_v1.1_merged_ltx23.safetensors": ("外阴摩擦", 0.7),
    "ltx2.3/SexGod_BreastMassage_LTX23_v1.safetensors": ("自慰/身体抚摸", 0.8),
    "ltx2.3/LTX-2.3 - Dildo Ride.safetensors": ("骑乘/机械道具/枕头摩擦", 0.8),
    "ltx2.3/LTX2.3TITFUCKE2000.safetensors": ("乳交", 1.0),
    "ltx2.3/LTX2.3_blowjob_animation_I2V_v1.0.safetensors": ("口交", 0.8),
    "ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors": ("腹部鼓起", 0.8),
    "ltx2.3/plora_2.3_V6-step00016500.comfy.safetensors": ("男性生殖器/衣下轮廓", 0.8),
    "ltx2.3/Kissing_Lora_2000.safetensors": ("接吻", 0.8),
    "ltx2.3/doggy_mission_3d_ltx23_v1.0.safetensors": ("传教士", 0.8),
    "ltx2.3/LTX2.3_666asslick.safetensors": ("舔阴/舔肛", 0.8),
    "ltx2.3/LTX-2.3-danceV2.comfy.safetensors": ("舞蹈动作", 0.8),
    "ltx2.3/LTX 2.3 - Twerking.safetensors": ("Twerk", 1.0),
    "ltx2.3/ltx2_fnelson-5000steps.k3nk.safetensors": ("Full Nelson", 0.8),
    "ltx2.3/LTX-2.3-fightV3.0.safetensors": ("格斗或剑术", 1.0),
    "ltx2.3/TentacleMotion_10Eros_i2v_v1.0.safetensors": ("触手蠕动/进入", 0.8),
    "ltx2.3/LTXV23_FOOTJOB_V1.safetensors": ("足交", 1.4),
    "ltx2.3/ltx23_facesl_512_02000.safetensors": ("扇脸与头部反应", 1.0),
    "ltx2.3/Shirt lift boob drop-v1.safetensors": ("掀衣展示", 0.8),
    "ltx2.3/LTX-2_3_Futanari_TF_lora_v3_1.safetensors": ("扶她/性别身体转换", 0.8),
    "ltx2.3/SEXGOD_HairyGirls_LTX23_v1_2.safetensors": ("体毛/阴毛", 0.8),
    "ltx2.3/LTX-2.3 - Wet Clothing.safetensors": ("湿衣服", 0.8),
    "ltx2.3/throat_bulge-10Eros_i2v_v1.0.safetensors": ("喉部鼓起", 1.0),
    "ltx2.3/dream_doublebj_1600.safetensors": ("双人口交", 0.8),
}


QQCC_LTX_VIDEO_LORA_MODELS = dict(LTX_VIDEO_LORA_MODELS)
QQCC_LTX_VIDEO_LORA_MODELS.update(
    {
        path: label
        for path, (label, _default_strength) in QQCC_LTX23_LIBRARY_MODELS.items()
    }
)

QQCC_LTX_VIDEO_LORA_DEFAULT_STRENGTHS = dict(LTX_VIDEO_LORA_DEFAULT_STRENGTHS)
QQCC_LTX_VIDEO_LORA_DEFAULT_STRENGTHS.update(
    {
        path: default_strength
        for path, (_label, default_strength) in QQCC_LTX23_LIBRARY_MODELS.items()
    }
)
