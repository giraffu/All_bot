import json
from pathlib import Path

from backend.app.models import TaskType
from ops.gpu_pool_controller.providers.runpod import RUNPOD_TASK_PROFILES
from scripts.generate_task_type_contract import (
    FRONTEND_CONTRACT_PATH,
    render_frontend_task_type_contract,
)
from src.domain_config.task_type_registry import (
    TASK_TYPE_REGISTRY,
    workflow_filename_facts,
)


def test_generated_frontend_contract_matches_python_registry():
    assert FRONTEND_CONTRACT_PATH.read_text(encoding="utf-8") == (
        render_frontend_task_type_contract()
    )


def test_central_task_enum_only_contains_registered_contract_values():
    registered_keys = set(TASK_TYPE_REGISTRY)
    central_values = {
        entry.central_type
        for entry in TASK_TYPE_REGISTRY.values()
        if entry.central_type is not None
    }
    enum_values = {task_type.value for task_type in TaskType}

    assert central_values <= enum_values
    assert enum_values <= registered_keys | central_values


def test_worker_profiles_and_mappings_only_reference_registered_workflows():
    workflow_facts = workflow_filename_facts()
    mappings_path = Path("workers/comfy_agent/workflows/mappings.json")
    mapping_task_types = set(json.loads(mappings_path.read_text(encoding="utf-8")))

    assert mapping_task_types <= set(workflow_facts)
    for profile in RUNPOD_TASK_PROFILES.values():
        for task_type in profile.supported_task_types:
            assert task_type in workflow_facts, (profile.runtime_profile, task_type)
            assert task_type in mapping_task_types, (profile.runtime_profile, task_type)
