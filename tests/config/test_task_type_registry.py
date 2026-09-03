from backend.app.main_simple_task_routes import SIMPLE_TASK_TYPE_MAP
from ops.gpu_pool_controller.providers.runpod import RUNPOD_TASK_PROFILES
from src.constants import (
    GENERATION_TASK_TYPES,
    MODE_NAME_MAP,
    TASK_COSTS,
    VIDEO_TASK_TYPES,
)
from src.core.gallery_submission_core import ALLOWED_WEB_SUBMIT_TYPES
from src.core.task_execution_types import resolve_worker_execution_task_type
from src.domain_config.task_type_registry import TASK_TYPE_REGISTRY
from src.domain_config.task_type_registry import (
    apply_input_reuse_task_types,
    gallery_display_type_configs,
    gallery_supported_task_types,
    get_central_task_type,
    get_execution_task_type,
    get_public_task_type,
    get_runpod_profile,
    get_task_cost,
    get_workflow_filename,
    is_apply_input_reuse_supported_task_type,
    is_gallery_supported_task_type,
    is_video_task_type,
)
from src.web_api.services.gallery_service_support import (
    APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES,
    DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS,
)
from src.workflow_mapping_validation import TASK_TYPE_WORKFLOW_FILENAMES


def test_registry_covers_current_constants_modes_costs_and_video_types():
    ignored_mode_entries = {"none", "template_contribute"}
    for task_type in MODE_NAME_MAP:
        if task_type in ignored_mode_entries:
            continue
        assert task_type in TASK_TYPE_REGISTRY

    for task_type in GENERATION_TASK_TYPES:
        entry = TASK_TYPE_REGISTRY[task_type]
        assert entry.is_generation is True

    for task_type in VIDEO_TASK_TYPES:
        entry = TASK_TYPE_REGISTRY[task_type]
        assert entry.is_video is True

    for task_type, cost in TASK_COSTS.items():
        entry = TASK_TYPE_REGISTRY[task_type]
        assert entry.cost == cost


def test_registry_matches_central_simple_task_type_map():
    for task_key, central_task_type in SIMPLE_TASK_TYPE_MAP.items():
        entry = TASK_TYPE_REGISTRY[task_key]
        assert entry.central_type == central_task_type.value


def test_registry_matches_workflow_filename_facts():
    for task_type, workflow_filename in TASK_TYPE_WORKFLOW_FILENAMES.items():
        matching_entries = [
            entry
            for entry in TASK_TYPE_REGISTRY.values()
            if entry.task_type == task_type or entry.execution_type == task_type
        ]
        assert matching_entries, task_type
        for entry in matching_entries:
            assert entry.workflow_filename == workflow_filename


def test_registry_matches_runpod_profile_supported_task_types():
    for entry in TASK_TYPE_REGISTRY.values():
        if entry.runpod_profile is None:
            continue
        profile = RUNPOD_TASK_PROFILES[entry.runpod_profile]
        assert entry.execution_type in profile.supported_task_types


def test_face_swap_versions_share_two_credit_price_on_i2i_pro_capacity():
    assert get_task_cost("face_swap") == 2
    assert get_workflow_filename("face_swap") == "face_swap.json"
    assert get_runpod_profile("face_swap") == "i2i_pro"

    assert get_task_cost("face_swap_v2") == 2
    assert get_workflow_filename("face_swap_v2") == "face_swap_v2.json"
    assert get_runpod_profile("face_swap_v2") == "i2i_pro"


def test_ltx25_video_upscale_has_an_isolated_gpu_profile_contract():
    entry = TASK_TYPE_REGISTRY["ltx25_video_upscale"]

    assert entry.public_type == "ltx25_video_upscale"
    assert entry.execution_type == "ltx25_video_upscale"
    assert entry.central_type == "ltx25_video_upscale"
    assert entry.workflow_filename == "LTX 2.5 IC V2V Upscale.api.json"
    assert entry.runpod_profile == "ltx25_video_upscale"
    assert entry.is_generation is True
    assert entry.is_video is True
    assert entry.gallery_supported is False
    assert entry.cost == 50


def test_registry_matches_gallery_and_apply_capability_lists():
    gallery_supported = {
        entry.task_type
        for entry in TASK_TYPE_REGISTRY.values()
        if entry.gallery_supported
    }
    assert gallery_supported == set(ALLOWED_WEB_SUBMIT_TYPES)

    apply_supported = {
        entry.task_type
        for entry in TASK_TYPE_REGISTRY.values()
        if entry.apply_input_reuse_supported
    }
    assert apply_supported == APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES


def test_registry_records_known_legacy_aliases_and_execution_profiles():
    expected = {
        "video_lora": ("image_to_video", "image_to_video", "Wan22AioV82.json"),
        "custom_video": ("image_to_video", "image_to_video", "Wan22AioV82.json"),
        "image_to_video": ("image_to_video", "image_to_video", "Wan22AioV82.json"),
        "video_insert": ("image_to_video", "image_to_video", "Wan22AioV82.json"),
        "video_edit": ("image_to_video", "image_to_video", "Wan22AioV82.json"),
        "ltx_video": ("ltx_video", "ltx_video", "LTX 2.3 I2V 6.1.json"),
        "wan22_video_v2": ("wan22_video_v2", "wan22_video_v2", "Wan22AioV82.json"),
        "scail2_action_transfer": (
            "scail2_action_transfer",
            "scail2_action_transfer",
            "SCAIL-2_Animation_multi-char_audio.api.json",
        ),
        "scail2_action_transfer_long": (
            "scail2_action_transfer_long",
            "scail2_action_transfer_long",
            "SCAIL-2_Animation_WAN-Context-Windows.api.json",
        ),
        "scail2_video_replacement": (
            "scail2_video_replacement",
            "scail2_video_replacement",
            "SCAIL-2_Replacement_audio.api.json",
        ),
        "i2i_pro": ("i2i_pro", "i2i_pro", "i2i_pro.json"),
        "txt2img": (
            "txt2img",
            "t2i-pornmaster-turbo",
            "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json",
        ),
        "face_swap": ("face_swap", "face_swap", "face_swap.json"),
        "face_swap_v2": ("face_swap_v2", "face_swap_v2", "face_swap_v2.json"),
        "pornmaster_flux2_single_edit": (
            "pornmaster_flux2_single_edit",
            "pornmaster_flux2_single_edit",
            "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json",
        ),
        "pornmaster_flux2_multi_edit": (
            "pornmaster_flux2_multi_edit",
            "pornmaster_flux2_multi_edit",
            "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json",
        ),
        "pornmaster_flux2_edit_bf16": (
            "pornmaster_flux2_edit_bf16",
            "pornmaster_flux2_edit_bf16",
            "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json",
        ),
        "pornmaster_flux2_multi_edit_bf16": (
            "pornmaster_flux2_multi_edit_bf16",
            "pornmaster_flux2_multi_edit_bf16",
            "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json",
        ),
    }

    for task_type, (public_type, execution_type, workflow_filename) in expected.items():
        entry = TASK_TYPE_REGISTRY[task_type]
        assert entry.public_type == public_type
        assert entry.execution_type == execution_type
        assert entry.workflow_filename == workflow_filename


def test_registry_matches_worker_execution_aliases_for_public_task_types():
    ignored_generic_types = {"image", "video"}
    for task_type, entry in TASK_TYPE_REGISTRY.items():
        if task_type in ignored_generic_types:
            continue
        assert entry.execution_type == resolve_worker_execution_task_type(task_type)


def test_free_edit_v25_registry_reuses_bf16_runtime_with_own_business_identity():
    entry = TASK_TYPE_REGISTRY["free_edit_v2_5"]

    assert entry.public_type == "free_edit_v2_5"
    assert entry.execution_type == "pornmaster_flux2_edit_bf16"
    assert entry.central_type == "pornmaster_flux2_edit_bf16"
    assert entry.runpod_profile == "pornmaster_flux2_edit_bf16"
    assert entry.cost == 3
    assert entry.gallery_supported is True
    assert resolve_worker_execution_task_type("free_edit_v2_5") == (
        "pornmaster_flux2_edit_bf16"
    )

    multi_entry = TASK_TYPE_REGISTRY["pornmaster_flux2_multi_edit_bf16"]
    assert multi_entry.runpod_profile == "pornmaster_flux2_edit_bf16"
    assert multi_entry.cost == 7
    assert multi_entry.is_generation is False
    assert multi_entry.gallery_supported is False


def test_registry_query_helpers_cover_key_task_type_relationships():
    expected = {
        "video_lora": {
            "public": "image_to_video",
            "execution": "image_to_video",
            "central": "image_to_video",
            "workflow": "Wan22AioV82.json",
            "runpod": "image_to_video",
            "video": True,
            "cost": 6,
            "gallery": True,
            "apply": False,
        },
        "custom_video": {
            "public": "image_to_video",
            "execution": "image_to_video",
            "central": None,
            "workflow": "Wan22AioV82.json",
            "runpod": "image_to_video",
            "video": True,
            "cost": 6,
            "gallery": True,
            "apply": False,
        },
        "image_to_video": {
            "public": "image_to_video",
            "execution": "image_to_video",
            "central": "image_to_video",
            "workflow": "Wan22AioV82.json",
            "runpod": "image_to_video",
            "video": True,
            "cost": 6,
            "gallery": False,
            "apply": False,
        },
        "wan22_video_v2": {
            "public": "wan22_video_v2",
            "execution": "wan22_video_v2",
            "central": "wan22_video_v2",
            "workflow": "Wan22AioV82.json",
            "runpod": "wan22_video_v2",
            "video": True,
            "cost": 6,
            "gallery": True,
            "apply": False,
        },
        "ltx_video": {
            "public": "ltx_video",
            "execution": "ltx_video",
            "central": "ltx_video",
            "workflow": "LTX 2.3 I2V 6.1.json",
            "runpod": None,
            "video": True,
            "cost": 10,
            "gallery": True,
            "apply": True,
        },
        "ltx_video_flf2v": {
            "public": "ltx_video",
            "execution": "ltx_video_flf2v",
            "central": "ltx_video_flf2v",
            "workflow": "LTX 2.3 FLF2V 6.1.json",
            "runpod": None,
            "video": True,
            "cost": 10,
            "gallery": True,
            "apply": True,
        },
        "minimax_h3_i2v": {
            "public": "minimax_h3_i2v",
            "execution": "minimax_h3_i2v",
            "central": "minimax_h3_i2v",
            "workflow": "MiniMax H3 I2V.api.json",
            "runpod": "minimax_h3",
            "video": True,
            "cost": 10,
            "gallery": True,
            "apply": False,
        },
        "minimax_h3_flf2v": {
            "public": "minimax_h3_flf2v",
            "execution": "minimax_h3_flf2v",
            "central": "minimax_h3_flf2v",
            "workflow": "MiniMax H3 FLF2V.api.json",
            "runpod": "minimax_h3",
            "video": True,
            "cost": 10,
            "gallery": True,
            "apply": False,
        },
        "scail2_action_transfer": {
            "public": "scail2_action_transfer",
            "execution": "scail2_action_transfer",
            "central": "scail2_action_transfer",
            "workflow": "SCAIL-2_Animation_multi-char_audio.api.json",
            "runpod": "scail2",
            "video": True,
            "cost": 40,
            "gallery": True,
            "apply": True,
        },
        "scail2_action_transfer_long": {
            "public": "scail2_action_transfer_long",
            "execution": "scail2_action_transfer_long",
            "central": "scail2_action_transfer_long",
            "workflow": "SCAIL-2_Animation_WAN-Context-Windows.api.json",
            "runpod": None,
            "video": True,
            "cost": 40,
            "gallery": True,
            "apply": True,
        },
        "scail2_video_replacement": {
            "public": "scail2_video_replacement",
            "execution": "scail2_video_replacement",
            "central": "scail2_video_replacement",
            "workflow": "SCAIL-2_Replacement_audio.api.json",
            "runpod": "scail2",
            "video": True,
            "cost": 40,
            "gallery": True,
            "apply": True,
        },
        "scail2_face_swap_v2": {
            "public": "scail2_face_swap_v2",
            "execution": "scail2_face_swap_v2",
            "central": "scail2_face_swap_v2",
            "workflow": "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json",
            "runpod": None,
            "video": True,
            "cost": 40,
            "gallery": True,
            "apply": True,
        },
        "txt2img": {
            "public": "txt2img",
            "execution": "t2i-pornmaster-turbo",
            "central": "t2i-pornmaster-turbo",
            "workflow": "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json",
            "runpod": "i2i_pro",
            "video": False,
            "cost": 2,
            "gallery": True,
            "apply": False,
        },
        "face_swap": {
            "public": "face_swap",
            "execution": "face_swap",
            "central": "face_swap",
            "workflow": "face_swap.json",
            "runpod": "i2i_pro",
            "video": False,
            "cost": 2,
            "gallery": False,
            "apply": True,
        },
        "face_swap_v2": {
            "public": "face_swap_v2",
            "execution": "face_swap_v2",
            "central": "face_swap_v2",
            "workflow": "face_swap_v2.json",
            "runpod": "i2i_pro",
            "video": False,
            "cost": 2,
            "gallery": False,
            "apply": False,
        },
        "pornmaster_flux2_single_edit": {
            "public": "pornmaster_flux2_single_edit",
            "execution": "pornmaster_flux2_single_edit",
            "central": "pornmaster_flux2_single_edit",
            "workflow": "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json",
            "runpod": None,
            "video": False,
            "cost": 2,
            "gallery": True,
            "apply": False,
        },
        "pornmaster_flux2_multi_edit": {
            "public": "pornmaster_flux2_multi_edit",
            "execution": "pornmaster_flux2_multi_edit",
            "central": "pornmaster_flux2_multi_edit",
            "workflow": "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json",
            "runpod": None,
            "video": False,
            "cost": 6,
            "gallery": True,
            "apply": False,
        },
    }

    for task_type, facts in expected.items():
        assert get_public_task_type(task_type) == facts["public"]
        assert get_execution_task_type(task_type) == facts["execution"]
        assert get_central_task_type(task_type) == facts["central"]
        assert get_workflow_filename(task_type) == facts["workflow"]
        assert get_runpod_profile(task_type) == facts["runpod"]
        assert is_video_task_type(task_type) is facts["video"]
        assert get_task_cost(task_type) == facts["cost"]
        assert is_gallery_supported_task_type(task_type) is facts["gallery"]
        assert is_apply_input_reuse_supported_task_type(task_type) is facts["apply"]


def test_registry_gallery_helpers_preserve_existing_lists_and_order():
    assert list(gallery_supported_task_types()) == [
        "txt2img",
        "i2i_pro",
        "i2i_draw",
        "custom_video",
        "video_lora",
        "ltx_video",
        "ltx_video_flf2v",
        "minimax_h3_i2v",
        "minimax_h3_flf2v",
        "minimax_h3_ref2v",
        "wan22_video_v2",
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
        "edit",
        "img2img_lora",
        "free_edit_v2_5",
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]
    assert list(gallery_supported_task_types()) == ALLOWED_WEB_SUBMIT_TYPES

    assert list(gallery_display_type_configs()) == [
        ("txt2img", "task.mode_txt2img"),
        ("i2i_pro", "task.mode_i2i_pro"),
        ("i2i_draw", "task.mode_i2i_draw"),
        ("edit", "task.mode_edit"),
        ("img2img_lora", "task.mode_img2img_lora"),
        ("free_edit_v2_5", "task.mode_free_edit_v2_5"),
        ("pornmaster_flux2_edit_bf16", "task.mode_free_edit_v3"),
        ("pornmaster_flux2_single_edit", "task.mode_free_edit_v2"),
        ("pornmaster_flux2_multi_edit", "task.mode_free_edit_v2"),
        ("custom_video", "task.mode_custom_video"),
        ("video_lora", "task.mode_video_lora"),
        ("ltx_video", "task.mode_ltx_video"),
        ("minimax_h3_i2v", "task.mode_minimax_h3_i2v"),
        ("wan22_video_v2", "task.mode_wan22_video_v2"),
        ("scail2_action_transfer", "task.mode_scail2_action_transfer"),
        ("scail2_video_replacement", "task.mode_scail2_video_replacement"),
        ("scail2_face_swap_v2", "task.mode_scail2_face_swap_v2"),
    ]
    assert list(gallery_display_type_configs()) == DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS

    assert apply_input_reuse_task_types() == {
        "face_swap",
        "face_video",
        "ltx_video",
        "ltx_video_flf2v",
        "minimax_h3_ref2v",
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    }
    assert apply_input_reuse_task_types() == APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES


def test_ref2v_registry_exposes_gallery_and_template_reuse_capabilities():
    assert is_gallery_supported_task_type("minimax_h3_ref2v") is True
    assert is_apply_input_reuse_supported_task_type("minimax_h3_ref2v") is True
    assert get_task_cost("minimax_h3_ref2v") == 11
