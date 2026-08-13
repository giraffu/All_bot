import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "runtime_env_contract.py"
CONTRACT_PATH = ROOT / "deploy" / "service-env-contract.yml"


def _load_module():
    spec = importlib.util.spec_from_file_location("runtime_env_contract", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNPOD_RELEASE_PROFILE_IMAGE_ENVS = (
    "RUNPOD_IMAGE_NAME_I2I_PRO",
    "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO",
    "RUNPOD_IMAGE_NAME_IMG2IMG_LORA",
    "RUNPOD_IMAGE_NAME_LTX_T2V",
    "RUNPOD_IMAGE_NAME_LTX_VIDEO",
    "RUNPOD_IMAGE_NAME_MINIMAX_H3",
    "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    "RUNPOD_IMAGE_NAME_SCAIL2",
    "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2",
)

BCRYPT_TEST_HASH = "$2b$12$YIySnXRqN4W6uLKgKUzSKe/V4g4JJEghmIdOcaW0UO21Fda5H05aa"


def _runpod_release_profile_pins() -> str:
    return json.dumps(
        {
            key: (f"ghcr.io/giraffu/test-{index}@sha256:" + f"{index:x}" * 64)
            for index, key in enumerate(
                RUNPOD_RELEASE_PROFILE_IMAGE_ENVS,
                start=1,
            )
        }
    )


def _environment(environment: str) -> dict[str, str]:
    suffix = "test" if environment == "test" else "prod"
    return {
        "ALLBOT_ENV": environment,
        "ALLBOT_STATE_ROOT": f"/var/lib/allbot/{suffix}",
        "DATABASE_URL": f"postgresql+asyncpg://{suffix}-db",
        "REDIS_URL": f"redis://{suffix}-redis/0",
        "WORKER_REDIS_URL": f"redis://{suffix}-worker/0",
        "API_BASE": "http://central-api:8003",
        "API_TOKEN": f"{suffix}-api-token",
        "AUTH_TOKEN": f"{suffix}-auth-token",
        "AGENT_SECRET_TOKEN": f"{suffix}-agent-token",
        "MEDIA_ARCHIVE_AGENT_TOKEN": f"{suffix}-archive-token",
        "MINIO_ENDPOINT": f"{suffix}-storage",
        "MINIO_ACCESS_KEY": f"{suffix}-access",
        "MINIO_SECRET_KEY": f"{suffix}-secret",
        "MINIO_BUCKET": f"user-data-{suffix}",
        "MINIO_RESULT_BUCKET": f"results-{suffix}",
        "MINIO_SECURE": "true",
        "R2_ENDPOINT": f"https://{suffix}-r2.example.com",
        "R2_ACCESS_KEY": f"{suffix}-r2-access",
        "R2_SECRET_KEY": f"{suffix}-r2-secret",
        "R2_BUCKET": f"user-data-{suffix}",
        "R2_PUBLIC_DOMAIN": f"https://assets-{suffix}.example.com",
        "BOT_TOKEN": f"{suffix}-bot-token",
        "TELEGRAM_API_BASE_URL": f"https://telegram-api-{suffix}.example.com",
        "TELEGRAM_FILE_BASE_URL": f"https://telegram-file-{suffix}.example.com",
        "REQUIRED_CHANNEL_ID": "-1001234567890",
        "MAIN_BOT_LAZY_BOT_ENABLED": "true",
        "MAIN_BOT_LAZY_BOT_USERNAME": "@QQCC666_bot",
        "QQCC_BOT_TOKEN": f"{suffix}-qqcc-token",
        "JWT_SECRET_KEY": f"{suffix}-jwt-secret",
        "DASHBOARD_SECRET_KEY": f"{suffix}-dashboard-secret",
        "DASHBOARD_ADMIN_USERNAME": "admin",
        "DASHBOARD_ADMIN_PASSWORD_HASH": BCRYPT_TEST_HASH,
        "QQCC_CONFIG_SECRET_KEY": f"{suffix}-qqcc-secret",
        "QQCC_CONFIG_ADMIN_USERNAME": "qqcc_admin",
        "QQCC_CONFIG_ADMIN_PASSWORD_HASH": BCRYPT_TEST_HASH,
        "QQCC_CONFIG_ADMIN_HOST": f"qqcc-{suffix}.example.com",
        "PRIVATE_QQCC_BOT_OWNER_HOST": f"private-{suffix}.example.com",
        "PRIVATE_QQCC_BOT_ENABLED": "false",
        "PRIVATE_QQCC_BOT_TOKEN_KEYRING": '{"1":"synthetic-key"}',
        "PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY": f"{suffix}-fingerprint",
        "PAID_GROUP_BOT_TOKEN": f"{suffix}-paid-token",
        "PAID_GROUP_CHAT_ID": "-1000000000000",
        "SUPPORT_BOT_TOKEN": f"{suffix}-support-token",
        "HUANYUY_NOTIFY_URL": f"https://pay-{suffix}.example.com/notify",
        "HUANYUY_RETURN_URL": f"https://pay-{suffix}.example.com/return",
        "HUANYUY_PID": f"{suffix}-merchant",
        "HUANYUY_KEY": f"{suffix}-payment-key",
        "HUANYUY_GATEWAY": f"https://gateway-{suffix}.example.com",
        "HUANYUY_SITENAME": f"AllBot {suffix}",
        "RMB_RECONCILIATION_ENABLED": "false",
        "LTX_T2V_BACKEND_ENABLED": "true" if environment == "test" else "false",
        "LTX_T2V_MSR_ENABLED": "true" if environment == "test" else "false",
        "MINIMAX_H3_BACKEND_ENABLED": "true" if environment == "test" else "false",
        "MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED": "true" if environment == "test" else "false",
        "RUNPOD_RELEASE_PROFILE_PINS_JSON": _runpod_release_profile_pins(),
        "RUNPOD_ASSET_CONTRACT_VERIFIED_PROFILES": (
            "img2img,image_to_video,wan22_video_v2,i2i_pro,scail2,ltx_video,"
            "ltx_t2v,minimax_h3,pornmaster_flux2_edit_bf16"
        ),
        "UNRELATED_OPERATOR_SECRET": "must-not-enter-containers",
    }


def test_builds_scoped_service_projections_without_unrelated_secrets():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    snapshot = module.build_snapshot(contract, "prod", _environment("prod"))

    web = snapshot.projections["web-api"]
    assert web["MEDIA_ARCHIVE_AGENT_TOKEN"] == "prod-archive-token"
    assert all(
        "MEDIA_ARCHIVE_AGENT_TOKEN" not in projection
        for service, projection in snapshot.projections.items()
        if service != "web-api"
    )
    bot = snapshot.projections["main-bot"]
    dashboard_frontend = snapshot.projections["dashboard-frontend"]
    dashboard_backend = snapshot.projections["dashboard-backend"]
    support_bot = snapshot.projections["support-bot"]
    assert web["ALLBOT_ENV"] == "prod"
    assert web["ALLBOT_CONFIG_REVISION"] == snapshot.service_revisions["web-api"]
    assert web["BOT_TOKEN"] == "prod-bot-token"
    for key in (
        "HUANYUY_PID",
        "HUANYUY_KEY",
        "HUANYUY_GATEWAY",
        "HUANYUY_NOTIFY_URL",
        "HUANYUY_RETURN_URL",
        "HUANYUY_SITENAME",
    ):
        assert web[key] == _environment("prod")[key]
        assert bot[key] == _environment("prod")[key]
    assert web["TELEGRAM_API_BASE_URL"] == ("https://telegram-api-prod.example.com")
    assert web["WORKER_REDIS_URL"] == "redis://prod-worker/0"
    assert "PAID_GROUP_BOT_TOKEN" not in web
    assert web["LTX_T2V_BACKEND_ENABLED"] == "false"
    assert web["MINIMAX_H3_BACKEND_ENABLED"] == "false"
    assert web["MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED"] == "false"
    assert bot["MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED"] == "false"
    assert all(
        "LTX_T2V_BACKEND_ENABLED" not in projection
        for service, projection in snapshot.projections.items()
        if service != "web-api"
    )
    assert bot["BOT_TOKEN"] == "prod-bot-token"
    assert "UNRELATED_OPERATOR_SECRET" not in bot
    assert dashboard_backend["SUPPORT_BOT_TOKEN"] == "prod-support-token"
    assert support_bot["SUPPORT_BOT_TOKEN"] == "prod-support-token"
    for service, projection in snapshot.projections.items():
        if service not in {"dashboard-backend", "support-bot"}:
            assert "SUPPORT_BOT_TOKEN" not in projection
    assert set(dashboard_frontend) == {
        "ALLBOT_CONFIG_REVISION",
        "ALLBOT_ENV",
    }


def test_rejects_compose_escaped_bcrypt_hash_before_activation():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("test")
    values["DASHBOARD_ADMIN_PASSWORD_HASH"] = BCRYPT_TEST_HASH.replace("$", "$$")

    with pytest.raises(
        module.ContractError,
        match="dashboard-backend has invalid DASHBOARD_ADMIN_PASSWORD_HASH",
    ):
        module.build_snapshot(
            contract,
            "test",
            values,
            services=["dashboard-backend"],
        )


def test_test_dashboard_does_not_require_production_runpod_release_pins():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("test")
    values.pop("RUNPOD_RELEASE_PROFILE_PINS_JSON")

    snapshot = module.build_snapshot(contract, "test", values)

    assert "dashboard-backend" in snapshot.projections
    assert (
        "RUNPOD_RELEASE_PROFILE_PINS_JSON"
        not in snapshot.projections["dashboard-backend"]
    )


def test_prod_dashboard_still_requires_runpod_release_pins():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    values.pop("RUNPOD_RELEASE_PROFILE_PINS_JSON")

    with pytest.raises(
        module.ContractError,
        match="RUNPOD_RELEASE_PROFILE_PINS_JSON",
    ):
        module.build_snapshot(contract, "prod", values)


def test_ltx_t2v_backend_flag_only_reconfigures_web_api():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    assert module.affected_services(contract, {"LTX_T2V_BACKEND_ENABLED"}) == {
        "web-api"
    }


def test_minimax_h3_optimizer_flag_reconfigures_web_and_main_bot():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    assert module.affected_services(
        contract, {"MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED"}
    ) == {"web-api", "main-bot"}


@pytest.mark.parametrize(
    ("environment", "wrong_url"),
    [
        ("test", "https://web.aivison.it.com/"),
        ("prod", "https://web-cf-test.aivison.it.com/"),
    ],
)
def test_environment_rejects_other_environment_mini_app_url(environment, wrong_url):
    module = _load_module()
    values = _environment(environment)
    values["MINI_APP_URL"] = wrong_url

    with pytest.raises(module.ContractError, match="MINI_APP_URL"):
        module.validate_environment_semantics(environment, values)


@pytest.mark.parametrize(
    ("environment", "expected_url"),
    [
        ("test", "https://web-cf-test.aivison.it.com/"),
        ("prod", "https://web.aivison.it.com/"),
    ],
)
def test_environment_accepts_its_canonical_mini_app_url(environment, expected_url):
    module = _load_module()
    values = _environment(environment)
    values["MINI_APP_URL"] = expected_url

    module.validate_environment_semantics(environment, values)


def test_environment_rejects_invalid_worker_workflow_override_json():
    module = _load_module()
    values = _environment("test")
    values["ALLBOT_WORKER_03_TASK_TYPE_WORKFLOW_OVERRIDES"] = (
        "{ltx_video:LTX 2.3 I2V 10Eros LoRA.json}"
    )

    with pytest.raises(
        module.ContractError,
        match="ALLBOT_WORKER_03_TASK_TYPE_WORKFLOW_OVERRIDES must be a JSON object",
    ):
        module.validate_environment_semantics("test", values)


def test_environment_accepts_worker_workflow_override_string_mapping():
    module = _load_module()
    values = _environment("test")
    values["ALLBOT_WORKER_03_TASK_TYPE_WORKFLOW_OVERRIDES"] = json.dumps(
        {"ltx_video": "LTX 2.3 I2V 10Eros LoRA.json"}
    )

    module.validate_environment_semantics("test", values)


@pytest.mark.parametrize(
    "key",
    ["DASHBOARD_REDIS_URL", "DASHBOARD_WORKER_REDIS_URL"],
)
def test_environment_rejects_dashboard_loopback_redis_aliases(key):
    module = _load_module()
    values = _environment("prod")
    values[key] = "redis://127.0.0.1:6379/1"

    with pytest.raises(module.ContractError, match=key):
        module.validate_environment_semantics("prod", values)


def test_environment_accepts_non_loopback_dashboard_redis_aliases():
    module = _load_module()
    values = _environment("prod")
    values["DASHBOARD_REDIS_URL"] = "rediss://valkey.internal:25061/1"
    values["DASHBOARD_WORKER_REDIS_URL"] = "rediss://valkey.internal:25061/2"

    module.validate_environment_semantics("prod", values)


@pytest.mark.parametrize("service", ["web-api", "main-bot"])
def test_ton_merchant_address_is_conditionally_required(service):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    values["TON_PAYMENT_POLLING_ENABLED"] = "true"

    with pytest.raises(module.ContractError) as exc:
        module.build_snapshot(contract, "prod", values, services={service})

    assert "VITE_MERCHANT_ADDRESS" in str(exc.value)
    assert "prod-bot-token" not in str(exc.value)


def test_rmb_query_url_is_required_only_when_reconciliation_is_enabled():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    values["RMB_RECONCILIATION_ENABLED"] = "true"

    with pytest.raises(module.ContractError, match="HUANYUY_QUERY_URL"):
        module.build_snapshot(
            contract,
            "prod",
            values,
            services={"payment-api"},
        )

    values["HUANYUY_QUERY_URL"] = "https://gateway-prod.example.com/order-query"
    snapshot = module.build_snapshot(
        contract,
        "prod",
        values,
        services={"payment-api"},
    )

    assert snapshot.projections["payment-api"]["HUANYUY_QUERY_URL"].endswith(
        "/order-query"
    )
    assert snapshot.projections["payment-api"]["RMB_RECONCILIATION_ENABLED"] == "true"


@pytest.mark.parametrize("service", ["web-api", "main-bot"])
def test_ton_merchant_address_is_projected_only_to_consuming_services(service):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    values.update(
        {
            "TON_PAYMENT_POLLING_ENABLED": "true",
            "VITE_MERCHANT_ADDRESS": (
                "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"
            ),
        }
    )

    snapshot = module.build_snapshot(contract, "prod", values, services={service})

    projection = snapshot.projections[service]
    assert projection["TON_PAYMENT_POLLING_ENABLED"] == "true"
    assert projection["VITE_MERCHANT_ADDRESS"].startswith("UQ")


def test_disabled_ton_does_not_require_or_project_merchant_address():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("test")
    values["TON_PAYMENT_POLLING_ENABLED"] = "false"

    snapshot = module.build_snapshot(
        contract,
        "test",
        values,
        services={"web-api", "main-bot"},
    )

    assert all(
        "VITE_MERCHANT_ADDRESS" not in projection
        for projection in snapshot.projections.values()
    )


def test_dashboard_backend_projection_requires_agent_control_token():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")

    snapshot = module.build_snapshot(
        contract,
        "prod",
        values,
        services={"dashboard-backend"},
    )

    assert snapshot.projections["dashboard-backend"]["AGENT_SECRET_TOKEN"] == (
        "prod-agent-token"
    )
    assert "UNRELATED_OPERATOR_SECRET" not in snapshot.projections["dashboard-backend"]


def test_dashboard_backend_projection_rejects_missing_agent_control_token():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values["AGENT_SECRET_TOKEN"]

    with pytest.raises(module.ContractError, match="AGENT_SECRET_TOKEN"):
        module.build_snapshot(
            contract,
            "prod",
            values,
            services={"dashboard-backend"},
        )


def test_dashboard_backend_projection_rejects_stale_runpod_profile_pin_set():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    pins = json.loads(values["RUNPOD_RELEASE_PROFILE_PINS_JSON"])
    pins["RUNPOD_IMAGE_NAME_FACE_SWAP"] = pins.pop("RUNPOD_IMAGE_NAME_LTX_T2V")
    values["RUNPOD_RELEASE_PROFILE_PINS_JSON"] = json.dumps(pins)

    with pytest.raises(
        module.ContractError,
        match="RUNPOD_RELEASE_PROFILE_PINS_JSON",
    ):
        module.build_snapshot(
            contract,
            "prod",
            values,
            services={"dashboard-backend"},
        )


def test_dashboard_backend_projection_rejects_mutable_runpod_profile_pin():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    pins = json.loads(values["RUNPOD_RELEASE_PROFILE_PINS_JSON"])
    pins["RUNPOD_IMAGE_NAME_I2I_PRO"] = "ghcr.io/giraffu/allbot-gpu-i2i-pro:latest"
    values["RUNPOD_RELEASE_PROFILE_PINS_JSON"] = json.dumps(pins)

    with pytest.raises(
        module.ContractError,
        match="non-digest-pinned.*RUNPOD_RELEASE_PROFILE_PINS_JSON",
    ):
        module.build_snapshot(
            contract,
            "prod",
            values,
            services={"dashboard-backend"},
        )


def test_qqcc_config_backend_projection_includes_central_api_token():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")

    snapshot = module.build_snapshot(
        contract,
        "prod",
        values,
        services={"qqcc-config-backend"},
    )

    projection = snapshot.projections["qqcc-config-backend"]
    assert projection["API_TOKEN"] == "prod-api-token"
    assert "AGENT_SECRET_TOKEN" not in projection
    assert "UNRELATED_OPERATOR_SECRET" not in projection


def test_qqcc_config_backend_projection_rejects_missing_central_api_token():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values["API_TOKEN"]

    with pytest.raises(module.ContractError, match="API_TOKEN"):
        module.build_snapshot(
            contract,
            "prod",
            values,
            services={"qqcc-config-backend"},
        )


def test_main_bot_projection_includes_required_channel_id_only_for_main_bot():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")

    snapshot = module.build_snapshot(contract, "prod", values)

    assert (
        snapshot.projections["main-bot"]["REQUIRED_CHANNEL_ID"]
        == (values["REQUIRED_CHANNEL_ID"])
    )
    assert all(
        "REQUIRED_CHANNEL_ID" not in projection
        for service, projection in snapshot.projections.items()
        if service != "main-bot"
    )
    assert snapshot.projections["main-bot"]["MAIN_BOT_LAZY_BOT_ENABLED"] == "true"
    assert (
        snapshot.projections["main-bot"]["MAIN_BOT_LAZY_BOT_USERNAME"] == "@QQCC666_bot"
    )
    assert all(
        "MAIN_BOT_LAZY_BOT_USERNAME" not in projection
        for service, projection in snapshot.projections.items()
        if service != "main-bot"
    )


def test_main_bot_projection_rejects_missing_required_channel_id():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values["REQUIRED_CHANNEL_ID"]

    with pytest.raises(module.ContractError, match="REQUIRED_CHANNEL_ID"):
        module.build_snapshot(contract, "prod", values, services={"main-bot"})


@pytest.mark.parametrize(
    "missing_key",
    ["MAIN_BOT_LAZY_BOT_ENABLED", "MAIN_BOT_LAZY_BOT_USERNAME"],
)
def test_prod_main_bot_projection_requires_dedicated_lazy_bot_config(missing_key):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values[missing_key]

    with pytest.raises(module.ContractError, match=missing_key):
        module.build_snapshot(contract, "prod", values, services={"main-bot"})


def test_main_bot_lazy_config_only_impacts_main_bot():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    changed_keys = {
        "MAIN_BOT_LAZY_BOT_ENABLED",
        "MAIN_BOT_LAZY_BOT_USERNAME",
    }

    assert module.affected_services(contract, changed_keys) == {"main-bot"}
    assert module.unknown_changed_keys(contract, changed_keys) == set()


def test_main_bot_lazy_config_keeps_non_target_projection_bytes_and_revisions():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    before_values = _environment("prod")
    after_values = dict(before_values)
    after_values["MAIN_BOT_LAZY_BOT_USERNAME"] = "@QQCC777_bot"

    before = module.build_snapshot(contract, "prod", before_values)
    after = module.build_snapshot(contract, "prod", after_values)

    assert before.service_revisions["main-bot"] != after.service_revisions["main-bot"]
    assert before.projections.keys() == after.projections.keys()
    for service in before.projections.keys() - {"main-bot"}:
        assert before.projections[service] == after.projections[service]
        assert before.service_revisions[service] == after.service_revisions[service]


def test_missing_required_service_key_fails_closed_without_value_disclosure():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    del values["BOT_TOKEN"]

    with pytest.raises(module.ContractError) as exc:
        module.build_snapshot(contract, "prod", values, services={"main-bot"})

    assert "BOT_TOKEN" in str(exc.value)
    assert "prod-bot-token" not in str(exc.value)


def test_web_api_rejects_missing_telegram_api_base_without_value_disclosure():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    telegram_url = values.pop("TELEGRAM_API_BASE_URL")

    with pytest.raises(module.ContractError) as exc:
        module.build_snapshot(contract, "prod", values, services={"web-api"})

    assert "TELEGRAM_API_BASE_URL" in str(exc.value)
    assert telegram_url not in str(exc.value)


def test_disabled_optional_service_does_not_receive_or_require_projection():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    values["PRIVATE_QQCC_BOT_ENABLED"] = "false"
    del values["PRIVATE_QQCC_BOT_TOKEN_KEYRING"]
    del values["PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY"]

    snapshot = module.build_snapshot(contract, "prod", values)

    assert "private-bot-worker" not in snapshot.projections


def test_environment_identity_mismatch_is_rejected():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    with pytest.raises(module.ContractError, match="ALLBOT_ENV"):
        module.build_snapshot(contract, "prod", _environment("test"))


def test_changed_key_names_expand_to_affected_services_and_unknown_is_all():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    services = set(contract["services"])

    assert module.affected_services(contract, {"BOT_TOKEN"}) == {
        "dashboard-backend",
        "main-bot",
        "web-api",
    }
    assert module.affected_services(contract, {"HUANYUY_KEY"}) == {
        "main-bot",
        "payment-api",
        "web-api",
    }
    assert module.affected_services(contract, {"DB_POOL_SIZE"}) == set(
        contract["shared_defaults"]["services"]
    )
    assert module.unknown_changed_keys(contract, {"DB_POOL_SIZE"}) == set()
    assert module.affected_services(contract, {"NEW_UNKNOWN_KEY"}) == services


def test_gpu_worker_keys_are_outside_control_plane_revision_and_impact():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    original_values = _environment("test")
    original_values.update(
        {
            "ALLBOT_WORKER_I2I_PRO_IMAGE": "registry.example/worker@sha256:old",
            "CLOUD_TEST_WORKER_ENABLED": "false",
            "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED": "false",
        }
    )
    changed_values = dict(original_values)
    changed_values.update(
        {
            "ALLBOT_WORKER_I2I_PRO_IMAGE": "registry.example/worker@sha256:new",
            "CLOUD_TEST_WORKER_ENABLED": "true",
            "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED": "true",
        }
    )

    original = module.build_snapshot(contract, "test", original_values)
    changed = module.build_snapshot(contract, "test", changed_values)
    active = {
        "key_hashes": original.key_hashes,
        "contract_revision": original.contract_revision,
    }

    assert changed.environment_revision == original.environment_revision
    assert changed.service_revisions == original.service_revisions
    assert "ALLBOT_WORKER_I2I_PRO_IMAGE" not in changed.key_hashes
    assert "CLOUD_TEST_WORKER_ENABLED" not in changed.key_hashes
    assert "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED" not in changed.key_hashes
    assert module.changed_keys(changed, active) == set()
    assert (
        module.affected_services(
            contract,
            {
                "ALLBOT_WORKER_I2I_PRO_IMAGE",
                "CLOUD_TEST_WORKER_ENABLED",
                "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED",
            },
        )
        == set()
    )
    assert (
        module.unknown_changed_keys(
            contract,
            {
                "ALLBOT_WORKER_I2I_PRO_IMAGE",
                "CLOUD_TEST_WORKER_ENABLED",
                "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED",
            },
        )
        == set()
    )
    assert all(
        "ALLBOT_WORKER_I2I_PRO_IMAGE" not in projection
        and "CLOUD_TEST_WORKER_ENABLED" not in projection
        and "CLOUD_TEST_SHARED_AIO_PREFETCH_ENABLED" not in projection
        for projection in changed.projections.values()
    )


def test_external_worker_key_does_not_hide_unknown_control_plane_key():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)

    changed = {"ALLBOT_WORKER_I2I_PRO_IMAGE", "NEW_UNKNOWN_KEY"}

    assert module.affected_services(contract, changed) == set(contract["services"])
    assert module.unknown_changed_keys(contract, changed) == {"NEW_UNKNOWN_KEY"}


def test_contract_change_alters_revision_and_impacts_all_services():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("prod")
    original = module.build_snapshot(contract, "prod", values)
    changed_contract = __import__("copy").deepcopy(contract)
    changed_contract["services"]["web-api"]["patterns"].append("NEW_SETTING")
    changed = module.build_snapshot(changed_contract, "prod", values)
    active = {
        "key_hashes": original.key_hashes,
        "contract_revision": original.contract_revision,
    }

    assert changed.environment_revision != original.environment_revision
    changed_keys = module.changed_keys(changed, active)
    assert changed_keys == {"ALLBOT_SERVICE_CONTRACT_REVISION"}
    assert module.affected_services(changed_contract, changed_keys) == set(
        changed_contract["services"]
    )


def test_snapshot_json_contains_revisions_and_key_names_but_not_values():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    snapshot = module.build_snapshot(contract, "test", _environment("test"))
    document = module.snapshot_summary(snapshot, changed_keys={"API_TOKEN"})
    rendered = module.dumps_summary(document)

    assert "API_TOKEN" in rendered
    assert snapshot.environment_revision in rendered
    assert "test-api-token" not in rendered
    assert "test-agent-token" not in rendered


def test_activation_writes_immutable_scoped_env_files_and_can_roll_back(tmp_path):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    first = module.build_snapshot(contract, "prod", _environment("prod"))
    module.activate_snapshot(tmp_path, first)

    current = tmp_path / "current"
    web_file = current / "web-api.env"
    assert current.resolve().name == first.environment_revision
    assert oct(web_file.stat().st_mode & 0o777) == "0o600"
    assert "PAID_GROUP_BOT_TOKEN" not in web_file.read_text(encoding="utf-8")

    changed = _environment("prod")
    changed["API_TOKEN"] = "rotated-prod-api-token"
    second = module.build_snapshot(contract, "prod", changed)
    second_state = module.activate_snapshot(tmp_path, second)
    assert second_state["previous_revision"] == first.environment_revision
    assert current.resolve().name == second.environment_revision

    module.rollback_activation(tmp_path, second.environment_revision)
    assert current.resolve().name == first.environment_revision
    assert (
        module.load_active_state(tmp_path)["environment_revision"]
        == first.environment_revision
    )


def test_activation_history_allows_returning_to_an_earlier_revision(tmp_path):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    first_values = _environment("prod")
    first = module.build_snapshot(contract, "prod", first_values)
    module.activate_snapshot(tmp_path, first)

    second_values = dict(first_values)
    second_values["API_TOKEN"] = "rotated-prod-api-token"
    second = module.build_snapshot(contract, "prod", second_values)
    module.activate_snapshot(tmp_path, second)

    returned = module.activate_snapshot(tmp_path, first)

    assert returned["environment_revision"] == first.environment_revision
    assert returned["previous_revision"] == second.environment_revision
    assert len(list((tmp_path / "states" / "activations").glob("*.json"))) == 3


def test_active_projection_integrity_rejects_tampering(tmp_path):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    snapshot = module.build_snapshot(contract, "prod", _environment("prod"))
    active = module.activate_snapshot(tmp_path, snapshot)
    projection = tmp_path / snapshot.environment_revision / "web-api.env"
    projection.write_text(
        projection.read_text(encoding="utf-8") + "TAMPERED=value\n",
        encoding="utf-8",
    )

    with pytest.raises(module.ContractError, match="integrity"):
        module.validate_active_projection_integrity(tmp_path, active)


def test_cli_merges_versioned_defaults_before_host_env_override(tmp_path):
    module = _load_module()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        '{"schema_version":1,"shared_defaults":{"services":["api"],'
        '"keys":["DB_POOL_SIZE"]},"services":{"api":'
        '{"required":["ALLBOT_ENV"],"patterns":[]}}}',
        encoding="utf-8",
    )
    defaults = tmp_path / "defaults.env"
    defaults.write_text("DB_POOL_SIZE=5\n", encoding="utf-8")
    env_file = tmp_path / "prod.env"
    env_file.write_text("ALLBOT_ENV=prod\nDB_POOL_SIZE=9\n", encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"

    assert (
        module.main(
            [
                "activate",
                "--environment",
                "prod",
                "--env-file",
                str(env_file),
                "--defaults",
                str(defaults),
                "--contract",
                str(contract_path),
                "--root",
                str(root),
            ]
        )
        == 0
    )
    projection = (root / "current" / "api.env").read_text(encoding="utf-8")
    assert "DB_POOL_SIZE=9\n" in projection


def test_cli_external_worker_change_is_not_control_plane_drift(tmp_path, capsys):
    module = _load_module()
    env_file = tmp_path / "test.env"
    values = _environment("test")
    values["ALLBOT_WORKER_I2I_PRO_IMAGE"] = "worker@sha256:old"
    values["CLOUD_TEST_WORKER_ENABLED"] = "false"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "test",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert module.main(["activate", *common]) == 0
    activated = json.loads(capsys.readouterr().out)
    values["ALLBOT_WORKER_I2I_PRO_IMAGE"] = "worker@sha256:new"
    values["CLOUD_TEST_WORKER_ENABLED"] = "true"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(["inspect", *common]) == 0
    inspected = json.loads(capsys.readouterr().out)

    assert inspected["environment_revision"] == activated["environment_revision"]
    assert inspected["active_revision"] == activated["environment_revision"]
    assert inspected["drift"] is False
    assert inspected["changed_keys"] == []
    assert inspected["unknown_keys"] == []
    assert inspected["affected_services"] == []


def test_full_inspect_detects_services_missing_from_scoped_initial_activation(
    tmp_path, capsys
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(_environment("prod")), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "dashboard-backend",
                "--service",
                "dashboard-frontend",
            ]
        )
        == 0
    )
    scoped = json.loads(capsys.readouterr().out)
    assert scoped["drift"] is False

    assert module.main(["inspect", *common]) == 0
    full = json.loads(capsys.readouterr().out)

    assert full["active_revision"] == scoped["environment_revision"]
    assert full["drift"] is True
    assert "web-api" in full["affected_services"]


def test_scoped_activation_adds_module_without_rewriting_active_projections(
    tmp_path, capsys
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(_environment("prod")), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "dashboard-backend",
                "--service",
                "dashboard-frontend",
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    dashboard_backend = root / "current" / "dashboard-backend.env"
    dashboard_frontend = root / "current" / "dashboard-frontend.env"
    before = {
        "dashboard-backend": dashboard_backend.read_bytes(),
        "dashboard-frontend": dashboard_frontend.read_bytes(),
    }

    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "qqcc-config-backend",
                "--service",
                "qqcc-config-frontend",
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    active = module.load_active_state(root)

    assert active is not None
    assert set(active["service_revisions"]) == {
        "dashboard-backend",
        "dashboard-frontend",
        "qqcc-config-backend",
        "qqcc-config-frontend",
    }
    assert dashboard_backend.read_bytes() == before["dashboard-backend"]
    assert dashboard_frontend.read_bytes() == before["dashboard-frontend"]
    assert first["environment_revision"] == second["environment_revision"]
    assert active["previous_revision"] is None
    assert second["drift"] is False
    activation_history = root / "states" / "activations"
    history_files = sorted(activation_history.glob("*.json"))
    assert len(history_files) == 2
    assert activation_history.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in history_files)


def test_scoped_activation_updates_target_and_preserves_non_target_with_rollback(
    tmp_path, capsys
):
    module = _load_module()
    values = _environment("prod")
    old_contract = module.load_contract(CONTRACT_PATH)
    old_contract["services"]["dashboard-backend"]["required"].remove(
        "AGENT_SECRET_TOKEN"
    )
    old_contract_path = tmp_path / "old-contract.json"
    old_contract_path.write_text(json.dumps(old_contract), encoding="utf-8")
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"

    old_common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(old_contract_path),
        "--root",
        str(root),
    ]
    assert (
        module.main(
            [
                "activate",
                *old_common,
                "--service",
                "dashboard-backend",
                "--service",
                "qqcc-config-backend",
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    dashboard_path = root / "current" / "dashboard-backend.env"
    qqcc_path = root / "current" / "qqcc-config-backend.env"
    old_dashboard = dashboard_path.read_bytes()
    old_qqcc = qqcc_path.read_bytes()
    assert b"AGENT_SECRET_TOKEN" not in old_dashboard

    values["AGENT_SECRET_TOKEN"] = "rotated-prod-agent-token"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    new_common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert module.main(["inspect", *new_common, "--service", "dashboard-backend"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["affected_services"] == ["dashboard-backend"]
    assert inspected["unknown_keys"] == []

    assert module.main(["activate", *new_common, "--service", "dashboard-backend"]) == 0
    second = json.loads(capsys.readouterr().out)
    active = module.load_active_state(root)
    assert active is not None
    assert active["previous_revision"] == first["environment_revision"]
    assert dashboard_path.read_bytes() != old_dashboard
    assert b"AGENT_SECRET_TOKEN=rotated-prod-agent-token" in dashboard_path.read_bytes()
    assert qqcc_path.read_bytes() == old_qqcc
    assert len(list((root / "states" / "activations").glob("*.json"))) == 2

    assert (
        module.main(
            [
                "rollback",
                *new_common,
                "--expected-revision",
                second["environment_revision"],
            ]
        )
        == 0
    )
    capsys.readouterr()
    restored = module.load_active_state(root)
    assert restored is not None
    assert restored["environment_revision"] == first["environment_revision"]
    assert dashboard_path.read_bytes() == old_dashboard
    assert qqcc_path.read_bytes() == old_qqcc


def test_scoped_activation_preserves_retired_non_target_projections(tmp_path, capsys):
    module = _load_module()
    values = _environment("prod")
    legacy_contract = module.load_contract(CONTRACT_PATH)
    legacy_contract["services"]["postgres"].pop("environments", None)
    legacy_contract["services"]["redis"].pop("environments", None)
    legacy_contract["services"]["qqcc-config-backend"]["required"].remove("API_TOKEN")
    legacy_contract_path = tmp_path / "legacy-contract.json"
    legacy_contract_path.write_text(json.dumps(legacy_contract), encoding="utf-8")
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            [
                "activate",
                *common,
                "--contract",
                str(legacy_contract_path),
                "--service",
                "postgres",
                "--service",
                "redis",
                "--service",
                "qqcc-config-backend",
                "--service",
                "qqcc-config-frontend",
            ]
        )
        == 0
    )
    capsys.readouterr()
    postgres_path = root / "current" / "postgres.env"
    redis_path = root / "current" / "redis.env"
    qqcc_path = root / "current" / "qqcc-config-backend.env"
    before = {
        "postgres": postgres_path.read_bytes(),
        "redis": redis_path.read_bytes(),
    }
    assert b"API_TOKEN" not in qqcc_path.read_bytes()
    current_common = [*common, "--contract", str(CONTRACT_PATH)]
    target = [
        "--service",
        "qqcc-config-backend",
        "--service",
        "qqcc-config-frontend",
    ]

    assert module.main(["inspect", *current_common, *target]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["affected_services"] == ["qqcc-config-backend"]
    assert inspected["retired_services"] == []

    assert module.main(["activate", *current_common, *target]) == 0
    activated = json.loads(capsys.readouterr().out)
    active = module.load_active_state(root)

    assert active is not None
    assert set(active["service_revisions"]) == {
        "postgres",
        "qqcc-config-backend",
        "qqcc-config-frontend",
        "redis",
    }
    assert activated["retired_services"] == []
    assert postgres_path.read_bytes() == before["postgres"]
    assert redis_path.read_bytes() == before["redis"]
    assert b"API_TOKEN=prod-api-token" in qqcc_path.read_bytes()


def test_scoped_inspect_reports_change_to_an_active_service(tmp_path, capsys):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    values = _environment("prod")
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 0
    first = module.load_active_state(root)
    assert first is not None
    dashboard_path = root / "current" / "dashboard-backend.env"
    old_dashboard = dashboard_path.read_bytes()
    capsys.readouterr()
    values["DASHBOARD_SECRET_KEY"] = "rotated-dashboard-secret"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(["inspect", *common, "--service", "qqcc-config-backend"]) == 0
    inspected = json.loads(capsys.readouterr().out)

    assert "dashboard-backend" in inspected["affected_services"]
    assert "qqcc-config-backend" in inspected["affected_services"]

    assert module.main(["activate", *common, "--service", "qqcc-config-backend"]) == 2
    assert "would change active service projections" in capsys.readouterr().err
    assert module.load_active_state(root) == first
    assert dashboard_path.read_bytes() == old_dashboard


def test_target_inspect_ignores_unknown_non_target_active_service(tmp_path, capsys):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(_environment("prod")), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]
    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 0
    capsys.readouterr()

    active = module.load_active_state(root)
    assert active is not None
    active["service_revisions"]["historical-support-bot"] = "f" * 64
    (root / "current.json").write_text(
        json.dumps(active, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "current.json").chmod(0o600)

    assert (
        module.main(["inspect-target", *common, "--service", "dashboard-backend"]) == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["status"] == "target-inspected"
    assert inspected["drift"] is False
    assert set(inspected["service_revisions"]) == {"dashboard-backend"}


def test_target_inspect_rejects_tampered_target_projection(tmp_path, capsys):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(_environment("prod")), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]
    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 0
    capsys.readouterr()
    projection = root / "current" / "dashboard-backend.env"
    projection.write_text(projection.read_text(encoding="utf-8") + "TAMPERED=1\n")
    projection.chmod(0o600)

    assert (
        module.main(["inspect-target", *common, "--service", "dashboard-backend"]) == 2
    )
    assert (
        "target service environment integrity check failed" in capsys.readouterr().err
    )


def test_target_inspect_reports_only_target_revision_drift(tmp_path, capsys):
    module = _load_module()
    values = _environment("prod")
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]
    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 0
    capsys.readouterr()
    values["DASHBOARD_SECRET_KEY"] = "rotated-dashboard-secret"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert (
        module.main(["inspect-target", *common, "--service", "dashboard-backend"]) == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["drift"] is True
    assert inspected["affected_services"] == ["dashboard-backend"]


def test_test_snapshot_includes_dashboard_services():
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    values = _environment("test")

    snapshot = module.build_snapshot(contract, "test", values)

    assert "central-api" in snapshot.projections
    assert "qqcc-config-backend" in snapshot.projections
    assert "dashboard-backend" in snapshot.projections
    assert "dashboard-frontend" in snapshot.projections
    assert "payment-api" not in snapshot.projections
    assert "paid-group-bot" not in snapshot.projections
    assert "support-bot" not in snapshot.projections


def test_full_test_inspect_preserves_dashboard_service(tmp_path, capsys):
    module = _load_module()
    contract = module.load_contract(CONTRACT_PATH)
    legacy_contract = json.loads(json.dumps(contract))
    legacy_contract["services"]["dashboard-backend"].pop("environments", None)
    legacy_contract_path = tmp_path / "legacy-contract.json"
    legacy_contract_path.write_text(json.dumps(legacy_contract), encoding="utf-8")
    values = _environment("test")
    env_file = tmp_path / "test.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "test",
        "--env-file",
        str(env_file),
        "--root",
        str(root),
    ]

    assert (
        module.main(
            [
                "activate",
                *common,
                "--contract",
                str(legacy_contract_path),
                "--service",
                "central-api",
                "--service",
                "dashboard-backend",
            ]
        )
        == 0
    )
    capsys.readouterr()
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    current_common = [*common, "--contract", str(CONTRACT_PATH)]

    assert module.main(["inspect", *current_common]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["retired_services"] == []

    assert module.main(["activate", *current_common]) == 0
    activated = json.loads(capsys.readouterr().out)
    assert activated["retired_services"] == []
    assert "dashboard-backend" in activated["service_revisions"]
    assert "dashboard-backend" in module.load_active_state(root)["service_revisions"]


def test_target_inspect_uses_active_revision_and_ignores_non_target_host_change(
    tmp_path, capsys
):
    module = _load_module()
    values = _environment("prod")
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]
    assert module.main(["activate", *common]) == 0
    activated = json.loads(capsys.readouterr().out)
    values["DASHBOARD_SECRET_KEY"] = "unapplied-dashboard-change"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(["inspect-target", *common, "--service", "central-api"]) == 0
    inspected = json.loads(capsys.readouterr().out)

    assert inspected["drift"] is False
    assert (
        inspected["effective_environment_revision"] == activated["environment_revision"]
    )
    assert inspected["environment_revision"] != activated["environment_revision"]
    assert inspected["changed_keys"] == []


def test_target_inspect_unknown_host_key_affecting_all_services_fails_closed(
    tmp_path, capsys
):
    module = _load_module()
    values = _environment("prod")
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]
    assert module.main(["activate", *common]) == 0
    capsys.readouterr()
    values["NEW_UNKNOWN_CONTROL_KEY"] = "candidate"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(["inspect-target", *common, "--service", "central-api"]) == 0
    inspected = json.loads(capsys.readouterr().out)

    assert inspected["drift"] is True
    assert inspected["unknown_keys"] == ["NEW_UNKNOWN_CONTROL_KEY"]
    assert inspected["affected_services"] == ["central-api"]


def test_target_inspect_without_container_services_is_host_only(tmp_path, capsys):
    module = _load_module()
    values = _environment("test")
    values.pop("SUPPORT_BOT_TOKEN")
    env_file = tmp_path / "test.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert (
        module.main(
            [
                "inspect-target",
                "--environment",
                "test",
                "--env-file",
                str(env_file),
                "--contract",
                str(CONTRACT_PATH),
                "--root",
                str(tmp_path / "state"),
            ]
        )
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["status"] == "target-inspected"
    assert inspected["drift"] is False
    assert inspected["service_revisions"] == {}


def test_target_inspect_skips_disabled_optional_target_without_active_projection(
    tmp_path, capsys
):
    module = _load_module()
    values = _environment("test")
    values.pop("QQCC_BOT_TOKEN")
    env_file = tmp_path / "test.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert (
        module.main(
            [
                "inspect-target",
                "--environment",
                "test",
                "--env-file",
                str(env_file),
                "--contract",
                str(CONTRACT_PATH),
                "--root",
                str(tmp_path / "state"),
                "--service",
                "qqcc-bot",
            ]
        )
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["drift"] is False
    assert inspected["service_revisions"] == {}


def test_scoped_activation_rejects_non_target_active_service_removal(tmp_path, capsys):
    module = _load_module()
    values = _environment("prod")
    env_file = tmp_path / "prod.env"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]
    assert (
        module.main(
            [
                "activate",
                *common,
                "--service",
                "dashboard-backend",
                "--service",
                "qqcc-bot",
            ]
        )
        == 0
    )
    first = module.load_active_state(root)
    assert first is not None
    qqcc_path = root / "current" / "qqcc-bot.env"
    old_qqcc = qqcc_path.read_bytes()
    capsys.readouterr()

    values["QQCC_BOT_TOKEN"] = ""
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 2
    assert "would remove active service projections" in capsys.readouterr().err
    assert module.load_active_state(root) == first
    assert qqcc_path.read_bytes() == old_qqcc


def test_full_activation_rollback_restores_incrementally_merged_projection_set(
    tmp_path, capsys
):
    module = _load_module()
    env_file = tmp_path / "prod.env"
    values = _environment("prod")
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    root = tmp_path / "state"
    common = [
        "--environment",
        "prod",
        "--env-file",
        str(env_file),
        "--contract",
        str(CONTRACT_PATH),
        "--root",
        str(root),
    ]

    assert module.main(["activate", *common, "--service", "dashboard-backend"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert module.main(["activate", *common, "--service", "qqcc-bot"]) == 0
    capsys.readouterr()
    merged = module.load_active_state(root)
    assert merged is not None
    assert set(merged["service_revisions"]) == {"dashboard-backend", "qqcc-bot"}

    values["API_TOKEN"] = "rotated-prod-api-token"
    env_file.write_text(module._env_text(values), encoding="utf-8")
    env_file.chmod(0o600)
    assert module.main(["activate", *common]) == 0
    full = json.loads(capsys.readouterr().out)
    assert full["environment_revision"] != first["environment_revision"]

    assert (
        module.main(
            [
                "rollback",
                *common,
                "--expected-revision",
                full["environment_revision"],
            ]
        )
        == 0
    )
    capsys.readouterr()
    restored = module.load_active_state(root)
    assert restored is not None
    assert set(restored["service_revisions"]) == {
        "dashboard-backend",
        "qqcc-bot",
    }
