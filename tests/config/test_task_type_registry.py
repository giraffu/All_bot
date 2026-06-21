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
from src.web_api.services.gallery_service_support import (
    APPLY_CONTEXT_ALLOW_INPUT_REUSE_TASK_TYPES,
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
