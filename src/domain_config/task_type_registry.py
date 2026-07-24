from __future__ import annotations

from dataclasses import dataclass

from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_EDIT,
    MODE_FREE_EDIT_V2_5,
    MODE_FACE_SWAP,
    MODE_FACE_SWAP_V2,
    MODE_FACE_VIDEO_STEP1,
    MODE_FACE_VIDEO_STEP2,
    MODE_FACESWAP_STEP1,
    MODE_FACESWAP_STEP2,
    MODE_I2I_DRAW,
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMAGE_TO_VIDEO_LITERAL,
    MODE_IMG2IMG_LORA,
    MODE_LTX_VIDEO,
    MODE_LTX_VIDEO_FLF2V,
    MODE_LTX_T2V,
    MODE_LTX_T2V_IC,
    MODE_CHARACTER_REFERENCE_BUILD,
    MODE_MASTURBATION,
    MODE_NAME_MAP,
    MODE_PENETRATION_STEP1,
    MODE_PENETRATION_STEP2,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_RANDOM_FACESWAP,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    MODE_TXT2IMG,
    MODE_UNDRESS,
    MODE_UNDRESS_TONGUE,
    MODE_WAN22_VIDEO_V2,
)


@dataclass(frozen=True, slots=True)
class TaskTypeRegistryEntry:
    task_type: str
    public_type: str
    execution_type: str
    central_type: str | None
    workflow_filename: str | None
    runpod_profile: str | None = None
    is_generation: bool = False
    is_video: bool = False
    gallery_supported: bool = False
    apply_input_reuse_supported: bool = False
    cost: int | None = None
    legacy_alias_of: str | None = None


def _entry(
    task_type: str,
    *,
    public_type: str | None = None,
    execution_type: str | None = None,
    central_type: str | None = None,
    workflow_filename: str | None = None,
    runpod_profile: str | None = None,
    is_generation: bool = False,
    is_video: bool = False,
    gallery_supported: bool = False,
    apply_input_reuse_supported: bool = False,
    cost: int | None = None,
    legacy_alias_of: str | None = None,
) -> TaskTypeRegistryEntry:
    public = public_type or task_type
    execution = execution_type or public
    return TaskTypeRegistryEntry(
        task_type=task_type,
        public_type=public,
        execution_type=execution,
        central_type=central_type,
        workflow_filename=workflow_filename,
        runpod_profile=runpod_profile,
        is_generation=is_generation,
        is_video=is_video,
        gallery_supported=gallery_supported,
        apply_input_reuse_supported=apply_input_reuse_supported,
        cost=cost,
        legacy_alias_of=legacy_alias_of,
    )


_IMAGE_TO_VIDEO_WORKFLOW = "Wan22AioV82.json"


TASK_TYPE_REGISTRY: dict[str, TaskTypeRegistryEntry] = {
    "image": _entry(
        "image",
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        legacy_alias_of="img2img",
    ),
    "quick_image": _entry(
        "quick_image",
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        legacy_alias_of="img2img",
    ),
    "video": _entry(
        "video",
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_generation=True,
        is_video=True,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_EDIT: _entry(
        MODE_EDIT,
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        gallery_supported=True,
        cost=2,
        legacy_alias_of="img2img",
    ),
    MODE_UNDRESS: _entry(
        MODE_UNDRESS,
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        cost=2,
        legacy_alias_of="img2img",
    ),
    MODE_MASTURBATION: _entry(
        MODE_MASTURBATION,
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        cost=2,
        legacy_alias_of="img2img",
    ),
    MODE_RANDOM_FACESWAP: _entry(
        MODE_RANDOM_FACESWAP,
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        cost=1,
        legacy_alias_of="img2img",
    ),
    MODE_PENETRATION_STEP1: _entry(
        MODE_PENETRATION_STEP1,
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        cost=2,
        legacy_alias_of="img2img",
    ),
    MODE_PENETRATION_STEP2: _entry(
        MODE_PENETRATION_STEP2,
        public_type="img2img",
        execution_type="img2img",
        central_type=None,
        workflow_filename="Qwen-Rapid-AIO.json",
        is_generation=True,
        legacy_alias_of="img2img",
    ),
    "img2img": _entry(
        "img2img",
        central_type="img2img",
        workflow_filename="Qwen-Rapid-AIO.json",
        runpod_profile="img2img_lora",
    ),
    MODE_IMG2IMG_LORA: _entry(
        MODE_IMG2IMG_LORA,
        central_type="img2img_lora",
        workflow_filename="Qwen-Rapid-AIO.json",
        runpod_profile="img2img_lora",
        is_generation=True,
        gallery_supported=True,
        cost=6,
    ),
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT: _entry(
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        central_type=MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        workflow_filename=(
            "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json"
        ),
        is_generation=True,
        gallery_supported=True,
        cost=2,
    ),
    MODE_PORNMASTER_FLUX2_MULTI_EDIT: _entry(
        MODE_PORNMASTER_FLUX2_MULTI_EDIT,
        central_type=MODE_PORNMASTER_FLUX2_MULTI_EDIT,
        workflow_filename=(
            "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json"
        ),
        is_generation=True,
        gallery_supported=True,
        cost=6,
    ),
    MODE_PORNMASTER_FLUX2_EDIT_BF16: _entry(
        MODE_PORNMASTER_FLUX2_EDIT_BF16,
        central_type=MODE_PORNMASTER_FLUX2_EDIT_BF16,
        workflow_filename=(
            "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json"
        ),
        is_generation=True,
        gallery_supported=True,
        cost=6,
    ),
    MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16: _entry(
        MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16,
        central_type=MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16,
        workflow_filename=(
            "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json"
        ),
        runpod_profile="pornmaster_flux2_edit_bf16",
        cost=7,
    ),
    MODE_FREE_EDIT_V2_5: _entry(
        MODE_FREE_EDIT_V2_5,
        execution_type=MODE_PORNMASTER_FLUX2_EDIT_BF16,
        central_type=MODE_PORNMASTER_FLUX2_EDIT_BF16,
        workflow_filename=(
            "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json"
        ),
        runpod_profile="pornmaster_flux2_edit_bf16",
        is_generation=True,
        gallery_supported=True,
        cost=3,
    ),
    MODE_FACE_SWAP: _entry(
        MODE_FACE_SWAP,
        central_type=MODE_FACE_SWAP,
        workflow_filename="face_swap.json",
        is_generation=True,
        apply_input_reuse_supported=True,
        cost=1,
    ),
    MODE_FACE_SWAP_V2: _entry(
        MODE_FACE_SWAP_V2,
        central_type=MODE_FACE_SWAP_V2,
        workflow_filename="face_swap_v2.json",
        runpod_profile="i2i_pro",
        is_generation=True,
        cost=2,
    ),
    MODE_FACESWAP_STEP1: _entry(
        MODE_FACESWAP_STEP1,
        public_type="face_swap",
        execution_type="face_swap",
        central_type=None,
        workflow_filename="face_swap.json",
        is_generation=True,
        legacy_alias_of="face_swap",
        cost=1,
    ),
    MODE_FACESWAP_STEP2: _entry(
        MODE_FACESWAP_STEP2,
        public_type="face_swap",
        execution_type="face_swap",
        central_type=None,
        workflow_filename="face_swap.json",
        is_generation=True,
        legacy_alias_of="face_swap",
    ),
    "face_video": _entry(
        "face_video",
        central_type="face_video",
        workflow_filename="face_video.json",
        is_video=True,
        apply_input_reuse_supported=True,
    ),
    MODE_FACE_VIDEO_STEP1: _entry(
        MODE_FACE_VIDEO_STEP1,
        public_type="face_video",
        execution_type="face_video",
        central_type=None,
        workflow_filename="face_video.json",
        is_generation=True,
        is_video=True,
        legacy_alias_of="face_video",
    ),
    MODE_FACE_VIDEO_STEP2: _entry(
        MODE_FACE_VIDEO_STEP2,
        public_type="face_video",
        execution_type="face_video",
        central_type=None,
        workflow_filename="face_video.json",
        is_generation=True,
        is_video=True,
        legacy_alias_of="face_video",
    ),
    MODE_CUSTOM_VIDEO: _entry(
        MODE_CUSTOM_VIDEO,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        runpod_profile="image_to_video",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_IMAGE_TO_VIDEO: _entry(
        MODE_IMAGE_TO_VIDEO,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        runpod_profile="image_to_video",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_IMAGE_TO_VIDEO_LITERAL: _entry(
        MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        runpod_profile="image_to_video",
        is_video=True,
        cost=6,
    ),
    "video_insert": _entry(
        "video_insert",
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        runpod_profile="image_to_video",
        is_video=True,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    "video_edit": _entry(
        "video_edit",
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        runpod_profile="image_to_video",
        is_video=True,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    "perfect_video_edit": _entry(
        "perfect_video_edit",
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_video=True,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    "txt2video": _entry(
        "txt2video",
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_video=True,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_PERFECT_VIDEO_INSERT: _entry(
        MODE_PERFECT_VIDEO_INSERT,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_generation=True,
        is_video=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_DOGGY_STYLE: _entry(
        MODE_DOGGY_STYLE,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_generation=True,
        is_video=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_BLOWJOB: _entry(
        MODE_BLOWJOB,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_generation=True,
        is_video=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_UNDRESS_TONGUE: _entry(
        MODE_UNDRESS_TONGUE,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_generation=True,
        is_video=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_CLOSEUP_BLOWJOB: _entry(
        MODE_CLOSEUP_BLOWJOB,
        public_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        execution_type=MODE_IMAGE_TO_VIDEO_LITERAL,
        central_type=None,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        is_generation=True,
        is_video=True,
        cost=6,
        legacy_alias_of=MODE_IMAGE_TO_VIDEO_LITERAL,
    ),
    MODE_LTX_VIDEO: _entry(
        MODE_LTX_VIDEO,
        central_type=MODE_LTX_VIDEO,
        workflow_filename="LTX 2.3 I2V 6.1.json",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        apply_input_reuse_supported=True,
        cost=10,
    ),
    MODE_LTX_VIDEO_FLF2V: _entry(
        MODE_LTX_VIDEO_FLF2V,
        public_type=MODE_LTX_VIDEO,
        execution_type=MODE_LTX_VIDEO_FLF2V,
        central_type=MODE_LTX_VIDEO_FLF2V,
        workflow_filename="LTX 2.3 FLF2V 6.1.json",
        is_video=True,
        gallery_supported=True,
        apply_input_reuse_supported=True,
        cost=10,
    ),
    "ltx_video_v2v_audio": _entry(
        "ltx_video_v2v_audio",
        central_type="ltx_video_v2v_audio",
        workflow_filename="LTX 2.3 V2V Audio 6.1.json",
        is_video=True,
    ),
    MODE_LTX_T2V: _entry(
        MODE_LTX_T2V,
        central_type=MODE_LTX_T2V,
        workflow_filename="LTX 2.3 Sulphur T2V.json",
        is_generation=True,
        is_video=True,
        cost=10,
    ),
    MODE_LTX_T2V_IC: _entry(
        MODE_LTX_T2V_IC,
        central_type=MODE_LTX_T2V_IC,
        workflow_filename="LTX 2.3 Sulphur Ingredients T2V.json",
        is_generation=True,
        is_video=True,
        cost=12,
    ),
    MODE_CHARACTER_REFERENCE_BUILD: _entry(
        MODE_CHARACTER_REFERENCE_BUILD,
        central_type=MODE_CHARACTER_REFERENCE_BUILD,
        workflow_filename="Character Reference Six Views.json",
        is_generation=True,
        cost=18,
    ),
    MODE_WAN22_VIDEO_V2: _entry(
        MODE_WAN22_VIDEO_V2,
        central_type=MODE_WAN22_VIDEO_V2,
        workflow_filename=_IMAGE_TO_VIDEO_WORKFLOW,
        runpod_profile="wan22_video_v2",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        cost=6,
    ),
    MODE_SCAIL2_ACTION_TRANSFER: _entry(
        MODE_SCAIL2_ACTION_TRANSFER,
        central_type=MODE_SCAIL2_ACTION_TRANSFER,
        workflow_filename="SCAIL-2_Animation_multi-char_audio.api.json",
        runpod_profile="scail2",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        apply_input_reuse_supported=True,
        cost=40,
    ),
    MODE_SCAIL2_ACTION_TRANSFER_LONG: _entry(
        MODE_SCAIL2_ACTION_TRANSFER_LONG,
        central_type=MODE_SCAIL2_ACTION_TRANSFER_LONG,
        workflow_filename="SCAIL-2_Animation_WAN-Context-Windows.api.json",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        apply_input_reuse_supported=True,
        cost=40,
    ),
    MODE_SCAIL2_VIDEO_REPLACEMENT: _entry(
        MODE_SCAIL2_VIDEO_REPLACEMENT,
        central_type=MODE_SCAIL2_VIDEO_REPLACEMENT,
        workflow_filename="SCAIL-2_Replacement_audio.api.json",
        runpod_profile="scail2",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        apply_input_reuse_supported=True,
        cost=40,
    ),
    MODE_SCAIL2_FACE_SWAP_V2: _entry(
        MODE_SCAIL2_FACE_SWAP_V2,
        central_type=MODE_SCAIL2_FACE_SWAP_V2,
        workflow_filename="SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json",
        is_generation=True,
        is_video=True,
        gallery_supported=True,
        apply_input_reuse_supported=True,
        cost=40,
    ),
    MODE_TXT2IMG: _entry(
        MODE_TXT2IMG,
        execution_type="t2i-pornmaster-turbo",
        central_type="t2i-pornmaster-turbo",
        workflow_filename=(
            "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"
        ),
        runpod_profile="i2i_pro",
        is_generation=True,
        gallery_supported=True,
        cost=2,
    ),
    MODE_I2I_PRO: _entry(
        MODE_I2I_PRO,
        central_type=MODE_I2I_PRO,
        workflow_filename="i2i_pro.json",
        runpod_profile="i2i_pro",
        is_generation=True,
        gallery_supported=True,
        cost=6,
    ),
    MODE_I2I_DRAW: _entry(
        MODE_I2I_DRAW,
        central_type=MODE_I2I_DRAW,
        workflow_filename="I2I_draw.json",
        is_generation=True,
        gallery_supported=True,
        cost=3,
    ),
}


_GALLERY_SUBMIT_TASK_TYPE_ORDER = (
    MODE_TXT2IMG,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_LTX_VIDEO,
    MODE_LTX_VIDEO_FLF2V,
    MODE_WAN22_VIDEO_V2,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_FREE_EDIT_V2_5,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
)

_GALLERY_DISPLAY_TASK_TYPE_ORDER = (
    MODE_TXT2IMG,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_FREE_EDIT_V2_5,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_LTX_VIDEO,
    MODE_WAN22_VIDEO_V2,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    MODE_SCAIL2_FACE_SWAP_V2,
)


def get_task_type_entry(task_type: str) -> TaskTypeRegistryEntry | None:
    return TASK_TYPE_REGISTRY.get(str(task_type or "").strip())


def iter_task_type_entries() -> tuple[TaskTypeRegistryEntry, ...]:
    return tuple(TASK_TYPE_REGISTRY.values())


def require_task_type_entry(task_type: str) -> TaskTypeRegistryEntry:
    entry = get_task_type_entry(task_type)
    if entry is None:
        raise KeyError(f"unknown task type registry entry: {task_type}")
    return entry


def get_public_task_type(task_type: str) -> str | None:
    entry = get_task_type_entry(task_type)
    return entry.public_type if entry else None


def get_execution_task_type(task_type: str) -> str | None:
    entry = get_task_type_entry(task_type)
    return entry.execution_type if entry else None


def get_central_task_type(task_type: str) -> str | None:
    entry = get_task_type_entry(task_type)
    return entry.central_type if entry else None


def get_workflow_filename(task_type: str) -> str | None:
    entry = get_task_type_entry(task_type)
    return entry.workflow_filename if entry else None


def workflow_filename_facts() -> dict[str, str]:
    facts: dict[str, str] = {}
    for entry in iter_task_type_entries():
        if not entry.workflow_filename:
            continue
        for key in (entry.task_type, entry.execution_type, entry.central_type):
            if not key:
                continue
            existing = facts.get(key)
            if existing is not None and existing != entry.workflow_filename:
                raise ValueError(
                    f"conflicting workflow filename for {key}: "
                    f"{existing!r} != {entry.workflow_filename!r}"
                )
            facts[key] = entry.workflow_filename
    return facts


def get_runpod_profile(task_type: str) -> str | None:
    entry = get_task_type_entry(task_type)
    return entry.runpod_profile if entry else None


def get_task_cost(task_type: str) -> int | None:
    entry = get_task_type_entry(task_type)
    return entry.cost if entry else None


def is_video_task_type(task_type: str) -> bool:
    entry = get_task_type_entry(task_type)
    return bool(entry and entry.is_video)


def is_gallery_supported_task_type(task_type: str) -> bool:
    entry = get_task_type_entry(task_type)
    return bool(entry and entry.gallery_supported)


def is_apply_input_reuse_supported_task_type(task_type: str) -> bool:
    entry = get_task_type_entry(task_type)
    return bool(entry and entry.apply_input_reuse_supported)


def gallery_supported_task_types() -> tuple[str, ...]:
    return tuple(
        task_type
        for task_type in _GALLERY_SUBMIT_TASK_TYPE_ORDER
        if is_gallery_supported_task_type(task_type)
    )


def gallery_display_type_configs() -> tuple[tuple[str, str], ...]:
    return tuple(
        (task_type, MODE_NAME_MAP.get(task_type, "task_type.other"))
        for task_type in _GALLERY_DISPLAY_TASK_TYPE_ORDER
        if is_gallery_supported_task_type(task_type)
    )


def apply_input_reuse_task_types() -> set[str]:
    return {
        entry.task_type
        for entry in TASK_TYPE_REGISTRY.values()
        if entry.apply_input_reuse_supported
    }
