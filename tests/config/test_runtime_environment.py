import pytest

from src.runtime_environment import (
    RuntimeEnvironmentError,
    require_env,
    resolve_runtime_environment,
)


def test_runtime_environment_is_required():
    with pytest.raises(RuntimeEnvironmentError, match="ALLBOT_ENV"):
        resolve_runtime_environment({})


def test_bot_type_is_derived_and_conflicts_fail_closed():
    assert resolve_runtime_environment({"ALLBOT_ENV": "prod"}) == ("prod", "PROD")
    with pytest.raises(RuntimeEnvironmentError, match="conflicts"):
        resolve_runtime_environment({"ALLBOT_ENV": "prod", "BOT_TYPE": "TEST"})


def test_required_value_error_does_not_include_secret_value():
    with pytest.raises(RuntimeEnvironmentError) as raised:
        require_env("API_TOKEN", {})
    assert str(raised.value) == "required runtime key is missing: API_TOKEN"
