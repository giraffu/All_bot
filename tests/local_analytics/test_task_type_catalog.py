from local_analytics_platform.app import analytics_common, user_profile_analytics
from local_analytics_platform.app.analytics_common import _input_requirements
from local_analytics_platform.app.task_type_catalog import MINIMAX_H3_TASK_TYPES


def test_minimax_h3_modes_are_generation_credit_operations_everywhere():
    for task_type in MINIMAX_H3_TASK_TYPES:
        assert task_type in analytics_common.GENERATION_OPERATION_TYPES
        assert task_type in user_profile_analytics.GENERATION_OPERATION_TYPES


def test_generation_operation_catalog_is_shared_with_user_profiles():
    assert (
        user_profile_analytics.GENERATION_OPERATION_TYPES
        is analytics_common.GENERATION_OPERATION_TYPES
    )


def test_minimax_h3_history_prompt_details_are_treated_as_video_tasks():
    assert "需校验首帧/时长" in _input_requirements([], "minimax_h3_i2v")
