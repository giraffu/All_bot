import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.private_qqcc_bot_credentials import PrivateBotCredentialCipher
from src.services.private_qqcc_bot_service import (
    PrivateBotConflictError,
    PrivateBotNotFoundError,
    PrivateBotTelegramIdentity,
    PrivateQqccBotLifecycleService,
    PrivateBotValidationError,
    configured_forbidden_telegram_bot_ids,
)


class _FakeRepository:
    def __init__(self):
        self.by_owner = {}
        self.by_telegram_bot = {}
        self.audit = []
        self.commits = 0

    async def get_owner_binding_for_update(self, owner_user_id):
        return self.by_owner.get(owner_user_id)

    async def get_by_telegram_bot_id(self, telegram_bot_id):
        return self.by_telegram_bot.get(telegram_bot_id)

    def add_bot(self, bot):
        if getattr(bot, "id", None) is None:
            bot.id = len(self.by_owner) + 1
        self.by_owner[bot.owner_user_id] = bot
        self.by_telegram_bot[bot.telegram_bot_id] = bot

    def add_audit(self, bot, **values):
        self.audit.append((bot, values))

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def delete(self, bot):
        self.by_owner.pop(bot.owner_user_id, None)
        self.by_telegram_bot.pop(bot.telegram_bot_id, None)


def _service(
    repository,
    gateway,
    *,
    config_cloner=None,
    admission_lock=None,
    tenant_media_cleanup=None,
):
    kwargs = {}
    if config_cloner is not None:
        kwargs["config_cloner"] = config_cloner
    if admission_lock is not None:
        kwargs["admission_lock"] = admission_lock
    if tenant_media_cleanup is not None:
        kwargs["tenant_media_cleanup"] = tenant_media_cleanup
    return PrivateQqccBotLifecycleService(
        repository=repository,
        telegram_gateway=gateway,
        credential_cipher=PrivateBotCredentialCipher(
            keys={1: b"k" * 32}, active_version=1
        ),
        fingerprint_secret="eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg=",
        webhook_base_url="https://api.example.test/api/private-bots/webhook",
        forbidden_bot_ids={999},
        active_task_checker=AsyncMock(return_value=False),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_admin_disable_waits_for_inflight_task_admission_before_returning():
    repository = _FakeRepository()
    bot = SimpleNamespace(
        id=5,
        owner_user_id=42,
        telegram_bot_id=123,
        telegram_username="private_bot",
        webhook_public_id="public-id",
        token_ciphertext="ciphertext",
        token_key_version=1,
        token_fingerprint="fingerprint",
        webhook_secret_hash="hash",
        owner_enabled=True,
        admin_enabled=True,
        runtime_status="active",
        last_error_code=None,
        last_error_message=None,
    )
    repository.add_bot(bot)
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    lock = asyncio.Lock()

    @asynccontextmanager
    async def admission_lock(private_bot_id):
        assert private_bot_id == 5
        async with lock:
            yield

    service = _service(repository, gateway, admission_lock=admission_lock)
    encrypted = service.credential_cipher.encrypt(
        "123:valid-secret",
        associated_data=bot.webhook_public_id,
    )
    bot.token_ciphertext = encrypted.ciphertext
    await lock.acquire()
    disable_task = asyncio.create_task(
        service.set_admin_enabled(
            owner_user_id=42,
            enabled=False,
            admin_identifier="admin",
            expected_private_bot_id=5,
        )
    )
    await asyncio.sleep(0)
    assert bot.runtime_status == "active"

    lock.release()
    await asyncio.wait_for(disable_task, timeout=1)

    assert bot.admin_enabled is False
    assert bot.runtime_status == "disabled"
    gateway.delete_webhook.assert_awaited_once()


@pytest.mark.asyncio
async def test_valid_private_bot_token_creates_one_active_independent_bot():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
                webhook_url="",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    source_config = {"global_enabled": True, "draw_scenes": [{"id": "one"}]}

    result = await _service(repository, gateway).provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config=source_config,
    )

    assert result.runtime_status == "active"
    bot = repository.by_owner[42]
    assert bot.telegram_bot_id == 123
    assert bot.config is not source_config
    assert bot.config == source_config
    assert "super-secret" not in bot.token_ciphertext
    gateway.set_webhook.assert_awaited_once()
    kwargs = gateway.set_webhook.await_args.kwargs
    assert kwargs["url"].endswith(bot.webhook_public_id)
    assert kwargs["drop_pending_updates"] is True
    assert repository.audit[0][1]["action"] == "created"
    assert repository.audit[-1][1]["action"] == "webhook_activated"


@pytest.mark.asyncio
async def test_owner_cannot_bind_a_second_different_private_bot():
    repository = _FakeRepository()
    existing = SimpleNamespace(
        id=5,
        owner_user_id=42,
        telegram_bot_id=123,
        webhook_public_id="existing-public-id",
        admin_enabled=True,
        owner_enabled=True,
    )
    repository.add_bot(existing)
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=456,
                username="second_bot",
                display_name="Second",
                webhook_url="",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )

    with pytest.raises(PrivateBotConflictError) as exc_info:
        await _service(repository, gateway).provision(
            owner_user_id=42,
            token="456:another-secret",
            source_config={},
        )

    assert exc_info.value.code == "owner_already_bound"
    gateway.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_official_bot_id_is_rejected_before_binding_or_webhook_mutation():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=999,
                username="official_bot",
                display_name="Official",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )

    with pytest.raises(PrivateBotValidationError) as exc_info:
        await _service(repository, gateway).provision(
            owner_user_id=42,
            token="999:official-secret",
            source_config={},
        )

    assert exc_info.value.code == "reserved_bot"
    assert repository.by_owner == {}
    gateway.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_prefix_must_match_get_me_bot_identity():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=456,
                username="mismatch_bot",
                display_name="Mismatch",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )

    with pytest.raises(PrivateBotValidationError) as exc_info:
        await _service(repository, gateway).provision(
            owner_user_id=42,
            token="123:valid-looking-secret",
            source_config={},
        )

    assert exc_info.value.code == "invalid_token"
    gateway.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_disabled_owner_cannot_reenable_by_rotating_same_bot_token():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
                webhook_url="",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:first-secret",
        source_config={},
    )
    bot = repository.by_owner[42]
    bot.admin_enabled = False
    bot.runtime_status = "disabled"
    gateway.set_webhook.reset_mock()

    result = await service.provision(
        owner_user_id=42,
        token="123:rotated-secret",
        source_config=deepcopy(bot.config),
    )

    assert result.runtime_status == "disabled"
    assert bot.admin_enabled is False
    gateway.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_bot_token_rotation_can_rescue_already_paid_tasks():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
                webhook_url="",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:first-secret",
        source_config={},
    )
    bot = repository.by_owner[42]
    first_ciphertext = bot.token_ciphertext
    service.active_task_checker = AsyncMock(return_value=True)

    result = await service.provision(
        owner_user_id=42,
        token="123:rotated-secret",
        source_config=deepcopy(bot.config),
    )

    assert result.runtime_status == "active"
    assert bot.token_ciphertext != first_ciphertext
    assert service.decrypt_token(bot) == "123:rotated-secret"
    assert repository.audit[-2][1]["action"] == "token_rotated"
    assert repository.audit[-1][1]["action"] == "webhook_activated"


@pytest.mark.asyncio
async def test_owner_credentials_rotation_requires_an_existing_binding():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
                webhook_url="",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )

    with pytest.raises(PrivateBotNotFoundError):
        await _service(repository, gateway).rotate_credentials(
            owner_user_id=42,
            token="123:rotated-secret",
        )

    assert repository.by_owner == {}
    gateway.set_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_credentials_rotation_preserves_latest_tenant_config():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
                webhook_url="",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:first-secret",
        source_config={"global_enabled": True},
    )
    bot = repository.by_owner[42]
    latest_config = {
        "global_enabled": False,
        "draw_scenes": [{"id": "owner-latest", "prompt": "latest"}],
    }
    bot.config = deepcopy(latest_config)

    await service.rotate_credentials(
        owner_user_id=42,
        token="123:rotated-secret",
    )

    assert bot.config == latest_config
    assert service.decrypt_token(bot) == "123:rotated-secret"


@pytest.mark.asyncio
async def test_invalid_token_gateway_error_is_exposed_only_as_validation_code():
    class _GatewayError(RuntimeError):
        code = "invalid_token"

    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(side_effect=_GatewayError("upstream detail")),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )

    with pytest.raises(PrivateBotValidationError) as exc_info:
        await _service(repository, gateway).provision(
            owner_user_id=42,
            token="123:never-log-me",
            source_config={},
        )

    assert exc_info.value.code == "invalid_token"
    assert "upstream detail" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        "",
        "no-colon",
        "123:short",
        "123:contains spaces and is much too long",
        f"123:{'x' * 129}",
    ],
)
async def test_malformed_or_oversized_token_is_rejected_before_network(token):
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )

    with pytest.raises(PrivateBotValidationError) as exc_info:
        await _service(repository, gateway).provision(
            owner_user_id=42,
            token=token,
            source_config={},
        )

    assert exc_info.value.code == "invalid_token"
    gateway.inspect_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_provision_uses_tenant_config_cloner_after_id_is_allocated():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    config_cloner = AsyncMock(return_value={"tenant_media": "private/1"})

    await _service(
        repository,
        gateway,
        config_cloner=config_cloner,
    ).provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={"tenant_media": "official"},
    )

    config_cloner.assert_awaited_once_with({"tenant_media": "official"}, 1)
    assert repository.by_owner[42].config == {"tenant_media": "private/1"}


@pytest.mark.asyncio
async def test_external_webhook_and_config_io_run_after_database_commit():
    repository = _FakeRepository()
    observed = []

    async def _clone_config(source_config, private_bot_id):
        observed.append(("clone", repository.commits, private_bot_id))
        return deepcopy(source_config)

    async def _set_webhook(**_kwargs):
        observed.append(("set_webhook", repository.commits, None))

    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=_set_webhook,
        delete_webhook=AsyncMock(),
    )

    await _service(
        repository,
        gateway,
        config_cloner=_clone_config,
    ).provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={"global_enabled": True},
    )

    assert observed[0][0] == "clone"
    assert observed[0][1] >= 1
    assert observed[1][0] == "set_webhook"
    assert observed[1][1] > observed[0][1]


@pytest.mark.asyncio
async def test_pause_keeps_webhook_secret_when_telegram_delete_is_uncertain():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(side_effect=RuntimeError("network timeout")),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={},
    )
    bot = repository.by_owner[42]
    active_secret_hash = bot.webhook_secret_hash

    await service.pause(owner_user_id=42)

    assert bot.runtime_status == "paused"
    assert bot.webhook_secret_hash == active_secret_hash
    assert bot.last_error_code == "webhook_delete_failed"


@pytest.mark.asyncio
async def test_permanent_unlink_fails_closed_until_webhook_is_deleted():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(side_effect=RuntimeError("network timeout")),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={},
    )
    bot = repository.by_owner[42]
    active_secret_hash = bot.webhook_secret_hash

    with pytest.raises(PrivateBotConflictError) as exc_info:
        await service.delete_binding(
            owner_user_id=42,
            admin_identifier="root",
            expected_private_bot_id=1,
        )

    assert exc_info.value.code == "webhook_delete_failed"
    assert repository.by_owner[42] is bot
    assert bot.admin_enabled is False
    assert bot.runtime_status == "disabled"
    assert bot.webhook_secret_hash == active_secret_hash
    assert repository.audit[-1][1]["action"] == "permanent_unbind_failed"


@pytest.mark.asyncio
async def test_permanent_unlink_records_snapshot_audit_before_deleting_binding():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={},
    )

    await service.delete_binding(
        owner_user_id=42,
        admin_identifier="root",
        expected_private_bot_id=1,
    )

    assert 42 not in repository.by_owner
    assert repository.audit[-1][1]["action"] == "permanent_unbound"
    assert repository.audit[-1][1]["actor_identifier"] == "root"


@pytest.mark.asyncio
async def test_permanent_unlink_keeps_disabled_binding_when_media_cleanup_fails():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    cleanup = AsyncMock(side_effect=RuntimeError("r2 unavailable"))
    service = _service(repository, gateway, tenant_media_cleanup=cleanup)
    await service.provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={},
    )

    with pytest.raises(PrivateBotConflictError) as exc_info:
        await service.delete_binding(
            owner_user_id=42,
            admin_identifier="root",
            expected_private_bot_id=1,
        )

    assert exc_info.value.code == "tenant_media_cleanup_failed"
    assert repository.by_owner[42].runtime_status == "disabled"
    assert repository.by_owner[42].admin_enabled is False
    cleanup.assert_awaited_once_with(1)
    assert repository.audit[-1][1]["action"] == "permanent_unbind_failed"


@pytest.mark.asyncio
async def test_permanent_unlink_is_blocked_while_paid_tasks_need_delivery():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={},
    )
    service.active_task_checker = AsyncMock(return_value=True)

    with pytest.raises(PrivateBotConflictError) as exc_info:
        await service.delete_binding(
            owner_user_id=42,
            admin_identifier="root",
            expected_private_bot_id=1,
        )

    assert exc_info.value.code == "active_tasks"
    assert 42 in repository.by_owner
    gateway.delete_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_and_admin_restore_have_distinct_audit_actions():
    repository = _FakeRepository()
    gateway = SimpleNamespace(
        inspect_token=AsyncMock(
            return_value=PrivateBotTelegramIdentity(
                bot_id=123,
                username="alice_private_bot",
                display_name="Alice Bot",
            )
        ),
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    service = _service(repository, gateway)
    await service.provision(
        owner_user_id=42,
        token="123:super-secret",
        source_config={},
    )

    await service.pause(owner_user_id=42)
    await service.resume(owner_user_id=42)
    await service.set_admin_enabled(
        owner_user_id=42,
        enabled=False,
        admin_identifier="root",
        expected_private_bot_id=1,
    )
    await service.set_admin_enabled(
        owner_user_id=42,
        enabled=True,
        admin_identifier="root",
        expected_private_bot_id=1,
    )

    actions = [values["action"] for _bot, values in repository.audit]
    assert "owner_resumed" in actions
    assert "admin_disabled" in actions
    assert "admin_restored" in actions
    admin_restore = next(
        values
        for _bot, values in repository.audit
        if values["action"] == "admin_restored"
    )
    assert admin_restore["actor_identifier"] == "root"


@pytest.mark.asyncio
async def test_admin_action_does_not_follow_owner_to_a_replacement_binding():
    repository = _FakeRepository()
    replacement = SimpleNamespace(
        id=2,
        owner_user_id=42,
        telegram_bot_id=456,
        webhook_public_id="replacement-public-id",
        admin_enabled=True,
        owner_enabled=True,
        runtime_status="active",
    )
    repository.add_bot(replacement)
    service = _service(
        repository,
        SimpleNamespace(
            inspect_token=AsyncMock(),
            set_webhook=AsyncMock(),
            delete_webhook=AsyncMock(),
        ),
    )

    with pytest.raises(PrivateBotConflictError) as exc_info:
        await service.set_admin_enabled(
            owner_user_id=42,
            enabled=False,
            admin_identifier="root",
            expected_private_bot_id=1,
        )

    assert exc_info.value.code == "binding_changed"
    assert replacement.admin_enabled is True


def test_forbidden_official_bot_ids_are_explicit_and_fail_closed(monkeypatch):
    monkeypatch.delenv("PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS", raising=False)
    with pytest.raises(PrivateBotValidationError) as exc_info:
        configured_forbidden_telegram_bot_ids()
    assert exc_info.value.code == "forbidden_bot_ids_missing"

    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS",
        "1001, 1002\n1003",
    )
    monkeypatch.setenv("QQCC_BOT_TOKEN", "1004:do-not-log")
    monkeypatch.setenv("FILE_BOT_TOKEN", "1005:do-not-log-either")
    assert configured_forbidden_telegram_bot_ids() >= {
        1001,
        1002,
        1003,
        1004,
        1005,
    }


@pytest.mark.parametrize(
    "webhook_base_url",
    [
        "",
        "http://api.example.test/api/private-bots/webhook",
        "https://user:pass@api.example.test/api/private-bots/webhook",
        "https://api.example.test/wrong-path",
        "https://api.example.test/api/private-bots/webhook?token=bad",
    ],
)
def test_private_bot_webhook_base_url_fails_closed(webhook_base_url):
    with pytest.raises(PrivateBotValidationError) as exc_info:
        PrivateQqccBotLifecycleService(
            repository=_FakeRepository(),
            telegram_gateway=SimpleNamespace(),
            credential_cipher=PrivateBotCredentialCipher(
                keys={1: b"k" * 32}, active_version=1
            ),
            fingerprint_secret="eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg=",
            webhook_base_url=webhook_base_url,
            forbidden_bot_ids={999},
        )

    assert exc_info.value.code == "webhook_base_url_invalid"
