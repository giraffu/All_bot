"""Runtime-safe catalog for the downloaded Wan 2.2 explicit LoRA pairs.

The source inventory is the local model-registry bundle
``wan22_explicit_lora_library/2026-07-18``.  Runtime code must not read that
host-local path, so this module keeps only the stable key, display label,
conservative single-slider default, and ComfyUI paths required by QQCC and the
worker patcher.

The upstream inventory records separate high/low recommendations.  QQCC uses
one editable strength for both stages, therefore the default below is the
lower of the two recommendations so neither stage starts above its guidance.
"""

from __future__ import annotations

from typing import Any


_WAN22_EXPLICIT_LORA_ROWS: tuple[tuple[str, str, float, str, str], ...] = (
    (
        "wan22_explicit_005",
        "005 · 口部插入转场",
        0.8,
        "wan2.2/explicit_top200/005-oral-insertion-wan-2-2/wan2.2-i2v-high-oral-insertion-v1.0.safetensors",
        "wan2.2/explicit_top200/005-oral-insertion-wan-2-2/wan2.2-i2v-low-oral-insertion-v1.0.safetensors",
    ),
    (
        "wan22_explicit_006",
        "006 · POV 传教士",
        0.8,
        "wan2.2/explicit_top200/006-wan-2-2-2-1-pov-missionary/wan2.2_i2v_highnoise_pov_missionary_v1.0.safetensors",
        "wan2.2/explicit_top200/006-wan-2-2-2-1-pov-missionary/wan2.2_i2v_lownoise_pov_missionary_v1.0.safetensors",
    ),
    (
        "wan22_explicit_008",
        "008 · F4C3SPL4SH 面部射精",
        1.0,
        "wan2.2/explicit_top200/008-f4c3spl4sh-cumshot-i2v-wan-2-2-video-lora-k3nk/wan22-f4c3spl4sh-100epoc-high-k3nk.safetensors",
        "wan2.2/explicit_top200/008-f4c3spl4sh-cumshot-i2v-wan-2-2-video-lora-k3nk/wan22-f4c3spl4sh-154epoc-low-k3nk.safetensors",
    ),
    (
        "wan22_explicit_009",
        "009 · 牛仔 / 反向牛仔",
        0.8,
        "wan2.2/explicit_top200/009-wan-cowgirl-reverse-cowgirl-t2v-i2v-lora/wan22.r3v3rs3_c0wg1rl-14b-High-i2v_e70.safetensors",
        "wan2.2/explicit_top200/009-wan-cowgirl-reverse-cowgirl-t2v-i2v-lora/wan22.r3v3rs3_c0wg1rl-14b-Low-i2v_e70.safetensors",
    ),
    (
        "wan22_explicit_010",
        "010 · POV 插入转场",
        0.8,
        "wan2.2/explicit_top200/010-pov-insertion-wan-2-x/wan2.2-i2v-high-pov-insertion-v1.0.safetensors",
        "wan2.2/explicit_top200/010-pov-insertion-wan-2-x/wan2.2-i2v-low-pov-insertion-v1.0.safetensors",
    ),
    (
        "wan22_explicit_014",
        "014 · 手交+口交组合",
        1.0,
        "wan2.2/explicit_top200/014-wan-2-2-i2v-combo-handjob-blowjob/WAN-2.2-I2V-HandjobBlowjobCombo-HIGH-v1.safetensors",
        "wan2.2/explicit_top200/014-wan-2-2-i2v-combo-handjob-blowjob/WAN-2.2-I2V-HandjobBlowjobCombo-LOW-v1.safetensors",
    ),
    (
        "wan22_explicit_022",
        "022 · Ultimate DeepThroat v1.1",
        0.8,
        "wan2.2/explicit_top200/022-ultimate-deepthroat-i2v-wan2-2-video-lora-k3nk/wan22-ultimatedeepthroat-i2v-102epoc-high-k3nk.safetensors",
        "wan2.2/explicit_top200/022-ultimate-deepthroat-i2v-wan2-2-video-lora-k3nk/wan22-ultimatedeepthroat-I2V-101epoc-low-k3nk.safetensors",
    ),
    (
        "wan22_explicit_025",
        "025 · 肛交",
        0.8,
        "wan2.2/explicit_top200/025-wan-2-2-wan-2-1-anal-sex/wan22_i2v_anal_v1_high_noise.safetensors",
        "wan2.2/explicit_top200/025-wan-2-2-wan-2-1-anal-sex/wan22_i2v_anal_v1_low_noise.safetensors",
    ),
    (
        "wan22_explicit_026",
        "026 · 主动牛仔",
        0.85,
        "wan2.2/explicit_top200/026-wan-i2v-2-2-2-1-assertive-cowgirl/Wan22-I2V-HIGH-Hip_Slammin_Assertive_Cowgirl.safetensors",
        "wan2.2/explicit_top200/026-wan-i2v-2-2-2-1-assertive-cowgirl/Wan22-I2V-LOW-Hip_Slammin_Assertive_Cowgirl.safetensors",
    ),
    (
        "wan22_explicit_029",
        "029 · POV 双人口交",
        1.0,
        "wan2.2/explicit_top200/029-wan-2-2-i2v-pov-double-blowjob/WAN-2.2-I2V-Double-Blowjob-HIGH-v1.safetensors",
        "wan2.2/explicit_top200/029-wan-2-2-i2v-pov-double-blowjob/WAN-2.2-I2V-Double-Blowjob-LOW-v1.safetensors",
    ),
    (
        "wan22_explicit_030",
        "030 · 阴茎玩弄 / 崇拜",
        0.8,
        "wan2.2/explicit_top200/030-penis-play/pworship_high_noise.safetensors",
        "wan2.2/explicit_top200/030-penis-play/pworship_low_noise.safetensors",
    ),
    (
        "wan22_explicit_034",
        "034 · SmoothMix 成人动画增强",
        0.65,
        "wan2.2/explicit_top200/034-smoothmix-animations-wan-2-2/SmoothXXXAnimation_High.safetensors",
        "wan2.2/explicit_top200/034-smoothmix-animations-wan-2-2/SmoothXXXAnimation_Low.safetensors",
    ),
    (
        "wan22_explicit_035",
        "035 · 反向悬空体位",
        0.8,
        "wan2.2/explicit_top200/035-wan-2-2-reverse-suspended-congress-i2v-t2v/reverse_suspended_congress_I2V_high.safetensors",
        "wan2.2/explicit_top200/035-wan-2-2-reverse-suspended-congress-i2v-t2v/reverse_suspended_congress_I2V_low.safetensors",
    ),
    (
        "wan22_explicit_038",
        "038 · 指交",
        0.85,
        "wan2.2/explicit_top200/038-perfect-fingering-wan-2-2-i2v/Sensual_fingering_v1_high_noise.safetensors",
        "wan2.2/explicit_top200/038-perfect-fingering-wan-2-2-i2v/Sensual_fingering_v1_low_noise.safetensors",
    ),
    (
        "wan22_explicit_040",
        "040 · 足交",
        1.0,
        "wan2.2/explicit_top200/040-wan-2-2-i2v-footjob/wan2.2_i2v_highnoise_footjob_v1.0.safetensors",
        "wan2.2/explicit_top200/040-wan-2-2-i2v-footjob/wan2.2_i2v_lownoise_footjob_v1.0.safetensors",
    ),
    (
        "wan22_explicit_046",
        "046 · POV 体外射精/拔出",
        0.8,
        "wan2.2/explicit_top200/046-wan-2-2-i2v-pov-body-cumshot-pullout/WAN-2.2-I2V-POV-Body-Cumshot-Pullout-HIGH-v1.safetensors",
        "wan2.2/explicit_top200/046-wan-2-2-i2v-pov-body-cumshot-pullout/WAN-2.2-I2V-POV-Body-Cumshot-Pullout-LOW-v1.safetensors",
    ),
    (
        "wan22_explicit_048",
        "048 · 胸部玩弄",
        0.8,
        "wan2.2/explicit_top200/048-wan-2-2-i2v-breast-play/WAN-2.2-I2V-BreastPlay-HIGH-v2.safetensors",
        "wan2.2/explicit_top200/048-wan-2-2-i2v-breast-play/WAN-2.2-I2V-BreastPlay-LOW-v2.safetensors",
    ),
    (
        "wan22_explicit_053",
        "053 · Deepthroat / Face Fuck v3",
        0.8,
        "wan2.2/explicit_top200/053-deepthroat-face-fuck-wan2-2-i2v/Wan22_ThroatV3_High.safetensors",
        "wan2.2/explicit_top200/053-deepthroat-face-fuck-wan2-2-i2v/Wan22_ThroatV3_Low.safetensors",
    ),
    (
        "wan22_explicit_054",
        "054 · Sex Smash Cut",
        0.8,
        "wan2.2/explicit_top200/054-sex-smash-cut-wan-2-2/wan2.2-i2v-high-sex-smashcut-v1.0.safetensors",
        "wan2.2/explicit_top200/054-sex-smash-cut-wan-2-2/wan2.2-i2v-low-sex-smashcut-v1.0.safetensors",
    ),
    (
        "wan22_explicit_055",
        "055 · 多姿势裸拍",
        0.8,
        "wan2.2/explicit_top200/055-nsfw-posing-nude/W22_NSFW_Posing_Nude_i2v_HN_v2.safetensors",
        "wan2.2/explicit_top200/055-nsfw-posing-nude/W22_NSFW_Posing_Nude_i2v_LN_v2.safetensors",
    ),
    (
        "wan22_explicit_056",
        "056 · 蠕动/触手运动",
        0.8,
        "wan2.2/explicit_top200/056-wriggling-motion-lora-wan-2-2-release-tentacles/wriggling_i2v_high_e010.safetensors",
        "wan2.2/explicit_top200/056-wriggling-motion-lora-wan-2-2-release-tentacles/wriggling_i2v_low_e020.safetensors",
    ),
    (
        "wan22_explicit_059",
        "059 · 巨乳乳交",
        0.9,
        "wan2.2/explicit_top200/059-huge-titfuck-wan/zurimix-high-i2v.safetensors",
        "wan2.2/explicit_top200/059-huge-titfuck-wan/zurimix-low-i2v.safetensors",
    ),
    (
        "wan22_explicit_060",
        "060 · Twerk",
        0.8,
        "wan2.2/explicit_top200/060-slop-twerk-wan-2-2-i2v/slop_twerk_HighNoise_merged3_7_v2.safetensors",
        "wan2.2/explicit_top200/060-slop-twerk-wan-2-2-i2v/slop_twerk_LowNoise_merged3_7_v2.safetensors",
    ),
    (
        "wan22_explicit_067",
        "067 · 高潮",
        0.8,
        "wan2.2/explicit_top200/067-orgasm/Wan2.2 - I2V - Orgasm - HIGH 14B.safetensors",
        "wan2.2/explicit_top200/067-orgasm/Wan2.2 - I2V - Orgasm - LOW 14B.safetensors",
    ),
    (
        "wan22_explicit_069",
        "069 · 舔阴",
        0.8,
        "wan2.2/explicit_top200/069-cunnilingus-pussy-licking-lora-i2v-wan2-2-k3nk/wan22-cunilingus-I2V-106epoc-high.safetensors",
        "wan2.2/explicit_top200/069-cunnilingus-pussy-licking-lora-i2v-wan2-2-k3nk/wan22-cunilingus-I2V-72epoc-low.safetensors",
    ),
    (
        "wan22_explicit_070",
        "070 · Mating Press（旧）",
        0.8,
        "wan2.2/explicit_top200/070-mating-press/mating_press_high.safetensors",
        "wan2.2/explicit_top200/070-mating-press/mating_press_low.safetensors",
    ),
    (
        "wan22_explicit_071",
        "071 · 挑逗式口交",
        0.8,
        "wan2.2/explicit_top200/071-wan-2-2-i2v-teasing-sensual-blowjob/WAN-2.2-I2V-SensualTeasingBlowjob-HIGH-v1.safetensors",
        "wan2.2/explicit_top200/071-wan-2-2-i2v-teasing-sensual-blowjob/WAN-2.2-I2V-SensualTeasingBlowjob-LOW-v1.safetensors",
    ),
    (
        "wan22_explicit_076",
        "076 · 性行为 FOV 拉远",
        0.8,
        "wan2.2/explicit_top200/076-sex-fov-slider-wan-2-2/wan2.2-i2v-high-sex-fov-slider-v1.0.safetensors",
        "wan2.2/explicit_top200/076-sex-fov-slider-wan-2-2/wan2.2-i2v-low-sex-fov-slider-v1.0.safetensors",
    ),
    (
        "wan22_explicit_077",
        "077 · 胸部膨胀",
        0.7,
        "wan2.2/explicit_top200/077-breast-expansion-wan-2-2-i2v/wan22_i2v_BE_v5_high_noise.safetensors",
        "wan2.2/explicit_top200/077-breast-expansion-wan-2-2-i2v/wan22_i2v_BE_v5_low_noise.safetensors",
    ),
    (
        "wan22_explicit_079",
        "079 · 扶她变身",
        0.9,
        "wan2.2/explicit_top200/079-wan2-2-i2v-a14b-futanari-transformation-futanarization-lora/Wan22_I2V_A14B_FutaTF_lora_v1_high_noise.safetensors",
        "wan2.2/explicit_top200/079-wan2-2-i2v-a14b-futanari-transformation-futanarization-lora/Wan22_I2V_A14B_FutaTF_lora_v1_low_noise.safetensors",
    ),
    (
        "wan22_explicit_081",
        "081 · Doggy 镜头滑动",
        0.8,
        "wan2.2/explicit_top200/081-doggy-slider-t2v-i2v-wan2-2-video-lora/I2V_doggyslider_high.safetensors",
        "wan2.2/explicit_top200/081-doggy-slider-t2v-i2v-wan2-2-video-lora/I2V_doggyslider_low.safetensors",
    ),
    (
        "wan22_explicit_088",
        "088 · 胸部插入转场",
        0.8,
        "wan2.2/explicit_top200/088-breast-insertion-wan-2-2/wan2.2-i2v-high-breast-insertion-v1.0.safetensors",
        "wan2.2/explicit_top200/088-breast-insertion-wan-2-2/wan2.2-i2v-low-breast-insertion-v1.0.safetensors",
    ),
    (
        "wan22_explicit_089",
        "089 · 举手舞蹈",
        0.5,
        "wan2.2/explicit_top200/089-dancing/dncng1 high 250901.safetensors",
        "wan2.2/explicit_top200/089-dancing/dncng1 low 250901.safetensors",
    ),
    (
        "wan22_explicit_096",
        "096 · 满嘴射精",
        1.0,
        "wan2.2/explicit_top200/096-mouthfull-cumshot-i2v-wan-2-2-video-lora-k3nk/wan22-mouthfull-140epoc-high-k3nk.safetensors",
        "wan2.2/explicit_top200/096-mouthfull-cumshot-i2v-wan-2-2-video-lora-k3nk/wan22-mouthfull-152epoc-low-k3nk.safetensors",
    ),
    (
        "wan22_explicit_097",
        "097 · 正面后入",
        0.8,
        "wan2.2/explicit_top200/097-i2v-sex-from-behind-front-facing/sfbehind_v2.1_high_noise.safetensors",
        "wan2.2/explicit_top200/097-i2v-sex-from-behind-front-facing/sfbehind_v2.1_low_noise.safetensors",
    ),
    (
        "wan22_explicit_103",
        "103 · 腹部隆起运动增强",
        0.6,
        "wan2.2/explicit_top200/103-wan2-2-nsfw-motion-enhancer/st0m4chBulg3_FUSED_HN.safetensors",
        "wan2.2/explicit_top200/103-wan2-2-nsfw-motion-enhancer/st0m4chBulg3_FUSED_LN.safetensors",
    ),
    (
        "wan22_explicit_104",
        "104 · 连续多次射精",
        0.8,
        "wan2.2/explicit_top200/104-sh00tz-series-of-cumshots/sh00tz_HN_75.safetensors",
        "wan2.2/explicit_top200/104-sh00tz-series-of-cumshots/sh00tz_LN_75.safetensors",
    ),
    (
        "wan22_explicit_115",
        "115 · 法式接吻",
        0.7,
        "wan2.2/explicit_top200/115-wan2-2-french-kiss-i2v-t2v/WAN2.2-FrenchKiss_HighNoise.safetensors",
        "wan2.2/explicit_top200/115-wan2-2-french-kiss-i2v-t2v/WAN2.2-FrenchKiss_LowNoise.safetensors",
    ),
    (
        "wan22_explicit_118",
        "118 · 假阳具机器",
        0.8,
        "wan2.2/explicit_top200/118-dildo-fucking-machine/Wan2.2 - I2V - Fucking Machine - HIGH 14B.safetensors",
        "wan2.2/explicit_top200/118-dildo-fucking-machine/Wan2.2 - I2V - Fucking Machine - LOW 14B.safetensors",
    ),
    (
        "wan22_explicit_120",
        "120 · 趴跪翘臀",
        0.8,
        "wan2.2/explicit_top200/120-wan-2-2-i2v-face-down-ass-up/WAN-2.2-I2V-FaceDownAssUp-HIGH-v1.safetensors",
        "wan2.2/explicit_top200/120-wan-2-2-i2v-face-down-ass-up/WAN-2.2-I2V-FaceDownAssUp-LOW-v1.safetensors",
    ),
    (
        "wan22_explicit_130",
        "130 · 肛门外观生成",
        0.75,
        "wan2.2/explicit_top200/130-wan-2-2-i2v-edible-anuses/I2V-WAN2.2-EdibleAnus-HighNoise-1.1_-000050.safetensors",
        "wan2.2/explicit_top200/130-wan-2-2-i2v-edible-anuses/I2V-WAN2.2-EdibleAnus-LowNoise-1.1_-000060.safetensors",
    ),
    (
        "wan22_explicit_135",
        "135 · 口腔侧颊插入",
        0.8,
        "wan2.2/explicit_top200/135-cheek-fuck-insertion-i2v-wan2-2/FF-v3-high-120.safetensors",
        "wan2.2/explicit_top200/135-cheek-fuck-insertion-i2v-wan2-2/FF-v3-low-120.safetensors",
    ),
    (
        "wan22_explicit_148",
        "148 · 侧视肛交",
        0.6,
        "wan2.2/explicit_top200/148-wan2-2-anal-side-view-t2v-i2v/Wan2.2_Anal-v1-HighNoise-I2V_T2V.safetensors",
        "wan2.2/explicit_top200/148-wan2-2-anal-side-view-t2v-i2v/Wan2.2_Anal-v1-LowNoise-I2V_T2V.safetensors",
    ),
    (
        "wan22_explicit_149",
        "149 · 磨蹭式牛仔",
        0.8,
        "wan2.2/explicit_top200/149-wan-2-2-i2v-grinding-cowgirl/WAN-2.2-I2V-Grinding-Cowgirl-HIGH-v1.safetensors",
        "wan2.2/explicit_top200/149-wan-2-2-i2v-grinding-cowgirl/WAN-2.2-I2V-Grinding-Cowgirl-LOW-v1.safetensors",
    ),
    (
        "wan22_explicit_155",
        "155 · 巨根深喉",
        0.8,
        "wan2.2/explicit_top200/155-ultimate-bbc-deepthroat-i2v-wan2-2-video-lora-k3nk/wan22-bbcdeepthroat-115epoc-high-k3nk.safetensors",
        "wan2.2/explicit_top200/155-ultimate-bbc-deepthroat-i2v-wan2-2-video-lora-k3nk/wan22-bbcdeepthroat-155epoc-low-720-k3nk.safetensors",
    ),
    (
        "wan22_explicit_157",
        "157 · 扇耳光 / 自扇",
        0.8,
        "wan2.2/explicit_top200/157-slap-and-self-slap-wan-2-2-i2v-t2v/wan_2.2_i2v_slap_high_v2.0.safetensors",
        "wan2.2/explicit_top200/157-slap-and-self-slap-wan-2-2-i2v-t2v/wan_2.2_i2v_slap_low_v2.0.safetensors",
    ),
    (
        "wan22_explicit_162",
        "162 · PornMaster Bukkake",
        1.0,
        "wan2.2/explicit_top200/162-pornmaster-wan-2-2-14b-i2v-bukkake/Pornmaster_wan 2.2_14b_I2V_bukkake_v1.4_high_noise.safetensors",
        "wan2.2/explicit_top200/162-pornmaster-wan-2-2-14b-i2v-bukkake/Pornmaster_wan 2.2_14b_I2V_bukkake_v1.4_low_noise.safetensors",
    ),
    (
        "wan22_explicit_164",
        "164 · 小胸/平胸保持",
        0.8,
        "wan2.2/explicit_top200/164-wan2-2-t2v-i2v-small-breasts-lora/WAN2.2_I2V-T2V_Flatchested_High.safetensors",
        "wan2.2/explicit_top200/164-wan2-2-t2v-i2v-small-breasts-lora/WAN2.2_I2V-T2V_Flatchested_Low.safetensors",
    ),
    (
        "wan22_explicit_198",
        "198 · 舔嘴唇",
        0.8,
        "wan2.2/explicit_top200/198-licking-lips-i2v-wan2-2/LipL-high-60.safetensors",
        "wan2.2/explicit_top200/198-licking-lips-i2v-wan2-2/LipL-low-60.safetensors",
    ),
)


WAN22_EXPLICIT_LORA_MODELS: dict[str, dict[str, Any]] = {
    key: {
        "label": label,
        "default_strength": default_strength,
        "high_path": high_path,
        "low_path": low_path,
    }
    for key, label, default_strength, high_path, low_path in _WAN22_EXPLICIT_LORA_ROWS
}


def resolve_wan22_lora_pair(name: str) -> tuple[str, str] | None:
    item = WAN22_EXPLICIT_LORA_MODELS.get(str(name or "").strip())
    if not item:
        return None
    return str(item["high_path"]), str(item["low_path"])
