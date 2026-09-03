"""User-facing pricing offers, independent from the execution task registry.

The task type registry answers how work is dispatched.  This module answers what
the product currently sells and which user-selected conditions affect pricing.
Keeping those concerns separate prevents legacy aliases and internal stages from
appearing in the admin pricing UI.
"""

from __future__ import annotations

from itertools import product
from typing import Any, Iterable

from src.constants import LTX_DURATION_MULTIPLIER, LTX_RESOLUTION_COST
from src.domain_config.ltx25_video_upscale import (
    LTX25_VIDEO_UPSCALE_CREDITS_PER_SECOND,
    LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS,
    get_ltx25_video_upscale_cost,
)
from src.domain_config.ltx_t2v import (
    CHARACTER_REFERENCE_BUILD_COST,
    LTX_T2V_COST_BY_DURATION,
    LTX_T2V_IC_COST_BY_DURATION,
)
from src.domain_config.minimax_h3 import (
    MINIMAX_H3_NORMAL_PRICE_BY_DURATION,
    MINIMAX_H3_REF2V_PRICE_BY_DURATION,
)
from src.domain_config.scail2_video import SCAIL2_COST_BY_DURATION_SECONDS
from src.domain_config.wan22_aio_video import (
    WAN22_VIDEO_V2_DURATION_SECONDS,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    get_wan22_video_v2_cost,
)


def _option(value: str | int, label: str) -> dict[str, str]:
    return {"value": str(value), "label": label}


YES_NO_OPTIONS = (_option("no", "无"), _option("yes", "有"))
INPUT_COUNT_OPTIONS = (_option(1, "1 个输入"), _option(2, "2 个输入"))
LTX_DURATION_OPTIONS = tuple(_option(value, f"{value} 秒") for value in (5, 10, 15, 20))
WAN_DURATION_OPTIONS = tuple(
    _option(value, f"{value} 秒") for value in WAN22_VIDEO_V2_DURATION_SECONDS
)
WAN_RESOLUTION_OPTIONS = tuple(
    _option(
        key,
        f"{value['label_zh']}（约 {value['approx_resolution']}）",
    )
    for key, value in WAN22_VIDEO_V2_RESOLUTION_PRESETS.items()
)


def _dimension(
    key: str, label: str, options: Iterable[dict[str, str]]
) -> dict[str, Any]:
    return {"key": key, "label": label, "options": list(options)}


def make_variant_id(offer_id: str, conditions: dict[str, str]) -> str:
    suffix = "::".join(f"{key}={value}" for key, value in conditions.items())
    return offer_id if not suffix else f"{offer_id}::{suffix}"


def _variant(
    offer_id: str,
    *,
    task_types: Iterable[str],
    default_cost: int,
    **conditions: str | int,
) -> dict[str, Any]:
    normalized = {key: str(value) for key, value in conditions.items()}
    return {
        "variant_id": make_variant_id(offer_id, normalized),
        "task_types": list(task_types),
        "conditions": normalized,
        "default_cost": int(default_cost),
    }


def _offer(
    offer_id: str,
    label: str,
    description: str,
    dimensions: Iterable[dict[str, Any]],
    variants: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": offer_id,
        "label": label,
        "description": description,
        "dimensions": list(dimensions),
        "variants": list(variants),
    }


def _fixed_offer(
    offer_id: str,
    label: str,
    description: str,
    task_types: Iterable[str],
    default_cost: int,
) -> dict[str, Any]:
    return _offer(
        offer_id,
        label,
        description,
        (),
        (_variant(offer_id, task_types=task_types, default_cost=default_cost),),
    )


def _wan_offer(offer_id: str, label: str, task_types: Iterable[str]) -> dict[str, Any]:
    variants = []
    for input_count, resolution, duration in product(
        (1, 2), WAN22_VIDEO_V2_RESOLUTION_PRESETS, WAN22_VIDEO_V2_DURATION_SECONDS
    ):
        variants.append(
            _variant(
                offer_id,
                task_types=task_types,
                default_cost=get_wan22_video_v2_cost(resolution, duration),
                input_count=input_count,
                resolution=resolution,
                duration=duration,
            )
        )
    return _offer(
        offer_id,
        label,
        "按输入帧数量、清晰度和时长定价",
        (
            _dimension("input_count", "输入图片", INPUT_COUNT_OPTIONS),
            _dimension("resolution", "清晰度", WAN_RESOLUTION_OPTIONS),
            _dimension("duration", "时长", WAN_DURATION_OPTIONS),
        ),
        variants,
    )


def _ltx_video_offer(
    offer_id: str,
    label: str,
    i2v_task_type: str,
    flf2v_task_type: str,
) -> dict[str, Any]:
    variants = []
    for mode, task_types in (
        ("i2v", (i2v_task_type,)),
        # The original LTX entry submits both modes through ltx_video and puts
        # the distinction in inputs; v2 also has a dedicated FLF task type.
        ("flf2v", (i2v_task_type, flf2v_task_type)),
    ):
        for duration in (5, 10, 15, 20):
            variants.append(
                _variant(
                    offer_id,
                    task_types=task_types,
                    default_cost=int(
                        LTX_RESOLUTION_COST["1280x704"]
                        * LTX_DURATION_MULTIPLIER[f"{duration}s"]
                    ),
                    mode=mode,
                    resolution="1280x704",
                    duration=duration,
                )
            )
    return _offer(
        offer_id,
        label,
        "按首帧/首尾帧、分辨率和时长定价",
        (
            _dimension(
                "mode", "输入方式", (_option("i2v", "首帧"), _option("flf2v", "首尾帧"))
            ),
            _dimension("resolution", "分辨率", (_option("1280x704", "1280 × 704"),)),
            _dimension("duration", "时长", LTX_DURATION_OPTIONS),
        ),
        variants,
    )


def _ltx25_video_upscale_offer() -> dict[str, Any]:
    offer_id = "video_upscale"
    durations = tuple(range(1, LTX25_VIDEO_UPSCALE_MAX_DURATION_SECONDS + 1))
    resolutions = tuple(LTX25_VIDEO_UPSCALE_CREDITS_PER_SECOND)
    variants = (
        _variant(
            offer_id,
            task_types=("ltx25_video_upscale",),
            default_cost=get_ltx25_video_upscale_cost(duration, resolution),
            resolution=resolution,
            duration=duration,
        )
        for resolution, duration in product(resolutions, durations)
    )
    return _offer(
        offer_id,
        "视频高清化",
        "按目标清晰度和原片整秒时长计价",
        (
            _dimension(
                "resolution",
                "目标清晰度",
                (
                    _option("720p", "720p"),
                    _option("1080p", "1080p"),
                    _option("2k", "2K"),
                ),
            ),
            _dimension(
                "duration",
                "原片时长",
                tuple(_option(value, f"{value} 秒") for value in durations),
            ),
        ),
        variants,
    )


def _advanced_video_pro_offer() -> dict[str, Any]:
    offer_id = "advanced_video_pro"
    variants = []
    for mode in ("t2v", "i2v", "flf2v", "ref2v"):
        task_type = f"minimax_h3_{mode}"
        matrix = (
            MINIMAX_H3_REF2V_PRICE_BY_DURATION
            if mode == "ref2v"
            else MINIMAX_H3_NORMAL_PRICE_BY_DURATION
        )
        material_options = (
            tuple(product(("no", "yes"), ("no", "yes")))
            if mode == "ref2v"
            else (("no", "no"),)
        )
        for duration, prices in matrix.items():
            for resolution, cost in prices.items():
                for reference_audio, reference_video in material_options:
                    variants.append(
                        _variant(
                            offer_id,
                            task_types=(task_type,),
                            default_cost=cost,
                            mode=mode,
                            resolution=resolution,
                            duration=duration,
                            reference_audio=reference_audio,
                            reference_video=reference_video,
                        )
                    )
    return _offer(
        offer_id,
        "高级图生视频 Pro",
        "按生成方式、清晰度、时长和参考音视频定价",
        (
            _dimension(
                "mode",
                "生成方式",
                (
                    _option("t2v", "文生视频"),
                    _option("i2v", "首帧图生视频"),
                    _option("flf2v", "首尾帧视频"),
                    _option("ref2v", "多参考生成"),
                ),
            ),
            _dimension("resolution", "清晰度", WAN_RESOLUTION_OPTIONS),
            _dimension(
                "duration",
                "时长",
                (_option(5, "5 秒"), _option(10, "10 秒"), _option(15, "15 秒")),
            ),
            _dimension("reference_audio", "参考音频", YES_NO_OPTIONS),
            _dimension("reference_video", "参考视频", YES_NO_OPTIONS),
        ),
        variants,
    )


def _scail2_offer(
    offer_id: str, label: str, task_type: str, durations: tuple[int, ...]
) -> dict[str, Any]:
    return _offer(
        offer_id,
        label,
        "按驱动视频时长定价",
        (
            _dimension(
                "duration",
                "时长",
                tuple(_option(value, f"{value} 秒") for value in durations),
            ),
        ),
        (
            _variant(
                offer_id,
                task_types=(task_type,),
                default_cost=SCAIL2_COST_BY_DURATION_SECONDS[duration],
                duration=duration,
            )
            for duration in durations
        ),
    )


def build_base_task_pricing_catalog() -> list[dict[str, Any]]:
    """Return every current Web/main-Bot sellable offer and no legacy scenes."""

    free_edit_variants = [
        _variant(
            "free_edit",
            task_types=("edit",),
            default_cost=2,
            engine="standard",
            input_count=1,
        ),
        _variant(
            "free_edit",
            task_types=("edit",),
            default_cost=6,
            engine="standard",
            input_count=2,
        ),
        _variant(
            "free_edit",
            task_types=("img2img_lora",),
            default_cost=6,
            engine="addon",
            input_count=1,
        ),
        _variant(
            "free_edit",
            task_types=("img2img_lora",),
            default_cost=6,
            engine="addon",
            input_count=2,
        ),
    ]
    free_edit = _offer(
        "free_edit",
        "自由 P 图",
        "按基础/附加模型和输入图片数量定价",
        (
            _dimension(
                "engine",
                "处理方式",
                (_option("standard", "基础编辑"), _option("addon", "附加模型")),
            ),
            _dimension("input_count", "输入图片", INPUT_COUNT_OPTIONS),
        ),
        free_edit_variants,
    )
    free_edit_v25 = _offer(
        "free_edit_v2_5",
        "自由 P 图 v2.5",
        "单图编辑与双图融合分别定价",
        (_dimension("input_count", "输入图片", INPUT_COUNT_OPTIONS),),
        (
            _variant(
                "free_edit_v2_5",
                task_types=("free_edit_v2_5",),
                default_cost=3,
                input_count=1,
            ),
            _variant(
                "free_edit_v2_5",
                task_types=("free_edit_v2_5",),
                default_cost=7,
                input_count=2,
            ),
        ),
    )

    ltx_t2v_variants = []
    for mode, task_type, matrix, resolution in (
        ("standard", "ltx_t2v", LTX_T2V_COST_BY_DURATION, "1280x704"),
        ("character", "ltx_t2v_ic", LTX_T2V_IC_COST_BY_DURATION, "768x448"),
    ):
        for duration, cost in matrix.items():
            ltx_t2v_variants.append(
                _variant(
                    "text_to_video",
                    task_types=(task_type,),
                    default_cost=cost,
                    mode=mode,
                    resolution=resolution,
                    duration=duration,
                )
            )

    return [
        {
            "id": "image_generation",
            "label": "图片生成",
            "offers": [
                _fixed_offer("txt2img", "文生图", "文字生成图片", ("txt2img",), 2),
                _fixed_offer(
                    "fantasy_face", "幻想换脸", "图片与提示词生成", ("i2i_pro",), 6
                ),
            ],
        },
        {
            "id": "image_editing",
            "label": "图片编辑",
            "offers": [
                free_edit,
                free_edit_v25,
                _fixed_offer(
                    "free_edit_v3",
                    "自由 P 图 v3",
                    "新一代单图编辑",
                    ("pornmaster_flux2_edit_bf16",),
                    5,
                ),
                _fixed_offer(
                    "face_swap",
                    "快速换脸",
                    "两张图片换脸",
                    ("face_swap", "faceswap_step1"),
                    2,
                ),
                _fixed_offer(
                    "random_face_swap",
                    "随机换脸",
                    "单图随机模板换脸",
                    ("random_faceswap",),
                    2,
                ),
            ],
        },
        {
            "id": "video_generation",
            "label": "视频生成",
            "offers": [
                _wan_offer(
                    "image_to_video",
                    "图生视频",
                    ("custom_video", "video_lora", "image_to_video"),
                ),
                _wan_offer("image_to_video_v2", "图生视频 v2", ("wan22_video_v2",)),
                _ltx_video_offer(
                    "advanced_video", "高级图生视频", "ltx_video", "ltx_video_flf2v"
                ),
                _ltx_video_offer(
                    "advanced_video_v2",
                    "高级图生视频 v2",
                    "ltx_video_v2",
                    "ltx_video_v2_flf2v",
                ),
                _offer(
                    "text_to_video",
                    "高级文生视频",
                    "按普通/角色一致性、分辨率和时长定价",
                    (
                        _dimension(
                            "mode",
                            "生成方式",
                            (
                                _option("standard", "普通文生视频"),
                                _option("character", "角色一致性"),
                            ),
                        ),
                        _dimension(
                            "resolution",
                            "分辨率",
                            (
                                _option("1280x704", "1280 × 704"),
                                _option("768x448", "768 × 448"),
                            ),
                        ),
                        _dimension("duration", "时长", LTX_DURATION_OPTIONS),
                    ),
                    ltx_t2v_variants,
                ),
                _advanced_video_pro_offer(),
            ],
        },
        {
            "id": "video_editing",
            "label": "视频处理",
            "offers": [
                _offer(
                    "video_face_swap",
                    "视频换脸",
                    "按输出分辨率定价",
                    (
                        _dimension(
                            "resolution",
                            "分辨率",
                            (_option("720", "720p"), _option("1024", "1024p")),
                        ),
                    ),
                    (
                        _variant(
                            "video_face_swap",
                            task_types=("face_video", "face_video_step1"),
                            default_cost=18,
                            resolution="720",
                        ),
                        _variant(
                            "video_face_swap",
                            task_types=("face_video", "face_video_step1"),
                            default_cost=36,
                            resolution="1024",
                        ),
                    ),
                ),
                _scail2_offer(
                    "action_transfer",
                    "动作迁移",
                    "scail2_action_transfer",
                    (5, 8, 10, 15, 20),
                ),
                _scail2_offer(
                    "video_replacement", "视频换人", "scail2_video_replacement", (5, 8)
                ),
                _scail2_offer(
                    "video_face_swap_v2", "视频换脸 v2", "scail2_face_swap_v2", (5, 8)
                ),
                _ltx25_video_upscale_offer(),
            ],
        },
        {
            "id": "character_tools",
            "label": "人物资产",
            "offers": [
                _fixed_offer(
                    "character_reference",
                    "人物参考表",
                    "生成人物一致性参考资产",
                    ("character_reference_build",),
                    CHARACTER_REFERENCE_BUILD_COST,
                )
            ],
        },
    ]


def iter_base_pricing_variants() -> Iterable[dict[str, Any]]:
    for category in build_base_task_pricing_catalog():
        for offer in category["offers"]:
            yield from offer["variants"]


def pricing_variant_index() -> dict[str, dict[str, Any]]:
    return {item["variant_id"]: item for item in iter_base_pricing_variants()}


def pricing_variants_for_task_type(task_type: str) -> list[dict[str, Any]]:
    normalized = str(task_type or "").strip()
    return [
        item
        for item in iter_base_pricing_variants()
        if normalized in item["task_types"]
    ]
