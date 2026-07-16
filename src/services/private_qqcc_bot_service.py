from __future__ import annotations

import copy
import hashlib
import os
import re
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncContextManager, Awaitable, Callable, Protocol
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.database.models import PrivateQqccBot, PrivateQqccBotAuditLog
from src.services.private_qqcc_bot_credentials import (
    PrivateBotCredentialCipher,
    build_token_fingerprint,
)

PRIVATE_QQCC_BOT_CLIENT_TYPE_PREFIX = "bot:qqcc-private:"
PRIVATE_QQCC_BOT_TOKEN_PATTERN = re.compile(
    r"^(?P<bot_id>[1-9][0-9]{0,19}):[A-Za-z0-9_-]{8,128}$"
)


class PrivateBotServiceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PrivateBotValidationError(PrivateBotServiceError):
    pass


class PrivateBotConflictError(PrivateBotServiceError):
    pass


class PrivateBotNotFoundError(PrivateBotServiceError):
    pass


@dataclass(frozen=True, slots=True)
class PrivateBotTelegramIdentity:
    bot_id: int
    username: str
    display_name: str
    webhook_url: str = ""


@dataclass(frozen=True, slots=True)
class PrivateBotProvisionResult:
    private_bot_id: int
    telegram_bot_id: int
    telegram_username: str
    runtime_status: str
    created: bool


class PrivateBotTelegramGateway(Protocol):
    async def inspect_token(self, token: str) -> PrivateBotTelegramIdentity: ...

    async def set_webhook(
        self,
        *,
        token: str,
        url: str,
        secret_token: str,
        drop_pending_updates: bool,
    ) -> None: ...

    async def delete_webhook(
        self,
        *,
        token: str,
        drop_pending_updates: bool,
    ) -> None: ...


class PrivateBotRepository(Protocol):
    async def get_owner_binding_for_update(self, owner_user_id: int): ...

    async def get_by_telegram_bot_id(self, telegram_bot_id: int): ...

    def add_bot(self, bot: PrivateQqccBot) -> None: ...

    def add_audit(self, bot: PrivateQqccBot, **values) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def delete(self, bot: PrivateQqccBot) -> None: ...


class SqlAlchemyPrivateBotRepository:
    def __init__(self, session):
        self.session = session

    async def get_owner_binding_for_update(self, owner_user_id: int):
        result = await self.session.execute(
            select(PrivateQqccBot)
            .where(PrivateQqccBot.owner_user_id == owner_user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_bot_id(self, telegram_bot_id: int):
        result = await self.session.execute(
            select(PrivateQqccBot).where(
                PrivateQqccBot.telegram_bot_id == telegram_bot_id
            )
        )
        return result.scalar_one_or_none()

    def add_bot(self, bot: PrivateQqccBot) -> None:
        self.session.add(bot)

    def add_audit(self, bot: PrivateQqccBot, **values) -> None:
        self.session.add(
            PrivateQqccBotAuditLog(
                private_bot=bot,
                owner_user_id=bot.owner_user_id,
                telegram_bot_id=bot.telegram_bot_id,
                **values,
            )
        )

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def delete(self, bot: PrivateQqccBot) -> None:
        await self.session.delete(bot)


ActiveTaskChecker = Callable[[int], Awaitable[bool]]
ConfigCloner = Callable[[dict, int], Awaitable[dict]]
OperationLockFactory = Callable[[int], AsyncContextManager[None]]
AdmissionLockFactory = Callable[[int], AsyncContextManager[None]]
TenantMediaCleanup = Callable[[int], Awaitable[None]]


async def _no_active_tasks(_private_bot_id: int) -> bool:
    return False


async def _copy_config_in_memory(source_config: dict, _private_bot_id: int) -> dict:
    return copy.deepcopy(source_config)


async def _no_media_cleanup(_private_bot_id: int) -> None:
    return None


@asynccontextmanager
async def _no_operation_lock(_owner_user_id: int):
    yield


@asynccontextmanager
async def _no_admission_lock(_private_bot_id: int):
    yield


def build_private_bot_client_type(private_bot_id: int) -> str:
    return f"{PRIVATE_QQCC_BOT_CLIENT_TYPE_PREFIX}{int(private_bot_id)}"


def parse_private_bot_client_type(client_type: str | None) -> int | None:
    normalized = str(client_type or "")
    if not normalized.startswith(PRIVATE_QQCC_BOT_CLIENT_TYPE_PREFIX):
        return None
    try:
        private_bot_id = int(normalized.removeprefix(PRIVATE_QQCC_BOT_CLIENT_TYPE_PREFIX))
    except ValueError:
        return None
    return private_bot_id if private_bot_id > 0 else None


def configured_forbidden_telegram_bot_ids() -> set[int]:
    explicit = os.getenv("PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS", "").strip()
    if not explicit:
        raise PrivateBotValidationError(
            "forbidden_bot_ids_missing",
            "Private Bot registration safety configuration is unavailable",
        )
    result: set[int] = set()
    for value in re.split(r"[,\s]+", explicit):
        if not value:
            continue
        if not value.isdigit() or int(value) <= 0:
            raise PrivateBotValidationError(
                "forbidden_bot_ids_invalid",
                "Private Bot registration safety configuration is invalid",
            )
        result.add(int(value))
    for name in (
        "BOT_TOKEN",
        "BOT_TOKEN_TEST",
        "BOT_TOKEN_test",
        "FILE_BOT_TOKEN",
        "QQCC_BOT_TOKEN",
        "QQCC_BOT_TOKEN_TEST",
        "QQCC_BOT_TOKEN_test",
        "PAID_GROUP_BOT_TOKEN",
    ):
        prefix = os.getenv(name, "").strip().partition(":")[0]
        if prefix.isdigit():
            result.add(int(prefix))
    return result


class PrivateQqccBotLifecycleService:
    def __init__(
        self,
        *,
        repository: PrivateBotRepository,
        telegram_gateway: PrivateBotTelegramGateway,
        credential_cipher: PrivateBotCredentialCipher,
        fingerprint_secret: str | None,
        webhook_base_url: str,
        forbidden_bot_ids: set[int] | None = None,
        active_task_checker: ActiveTaskChecker = _no_active_tasks,
        config_cloner: ConfigCloner = _copy_config_in_memory,
        operation_lock: OperationLockFactory = _no_operation_lock,
        admission_lock: AdmissionLockFactory = _no_admission_lock,
        tenant_media_cleanup: TenantMediaCleanup = _no_media_cleanup,
    ):
        base_url = webhook_base_url.strip().rstrip("/")
        parsed_webhook_url = urlsplit(base_url)
        if (
            parsed_webhook_url.scheme != "https"
            or not parsed_webhook_url.hostname
            or parsed_webhook_url.username
            or parsed_webhook_url.password
            or parsed_webhook_url.query
            or parsed_webhook_url.fragment
            or parsed_webhook_url.path.rstrip("/")
            != "/api/private-bots/webhook"
        ):
            raise PrivateBotValidationError(
                "webhook_base_url_invalid",
                "Private Bot webhook URL must use the configured HTTPS ingress path",
            )
        self.repository = repository
        self.telegram_gateway = telegram_gateway
        self.credential_cipher = credential_cipher
        self.fingerprint_secret = fingerprint_secret
        self.webhook_base_url = base_url
        self.forbidden_bot_ids = (
            configured_forbidden_telegram_bot_ids()
            if forbidden_bot_ids is None
            else set(forbidden_bot_ids)
        )
        self.active_task_checker = active_task_checker
        self.config_cloner = config_cloner
        self.operation_lock = operation_lock
        self.admission_lock = admission_lock
        self.tenant_media_cleanup = tenant_media_cleanup

    def _webhook_url(self, bot) -> str:
        return f"{self.webhook_base_url}/{bot.webhook_public_id}"

    def _result(self, bot, *, created: bool) -> PrivateBotProvisionResult:
        return PrivateBotProvisionResult(
            private_bot_id=int(bot.id),
            telegram_bot_id=int(bot.telegram_bot_id),
            telegram_username=str(bot.telegram_username or ""),
            runtime_status=str(bot.runtime_status),
            created=created,
        )

    @staticmethod
    def _config_requires_tenant_media_clone(config: dict) -> bool:
        for section in ("video_scenes", "ai_video_scenes", "draw_scenes", "filter_scenes"):
            for scene in config.get(section, []):
                for field in ("demo_input_media", "demo_output_media"):
                    media = scene.get(field)
                    if isinstance(media, dict) and str(
                        media.get("object_key") or ""
                    ).startswith("qqcc/demo/"):
                        return True
        return False

    async def _clone_initial_config(self, bot, source_config: dict) -> bool:
        try:
            bot.config = await self.config_cloner(source_config, int(bot.id))
        except Exception:
            before_status = str(bot.runtime_status)
            bot.runtime_status = "error"
            bot.last_error_code = "config_clone_failed"
            bot.last_error_message = "Private Bot configuration initialization failed"
            self.repository.add_audit(
                bot,
                actor_type="system",
                actor_identifier=None,
                action="config_clone_failed",
                before_status=before_status,
                after_status="error",
                details={"error_code": bot.last_error_code},
            )
            await self.repository.commit()
            return False
        bot.last_error_code = None
        bot.last_error_message = None
        await self.repository.commit()
        return True

    async def _persist_binding(self) -> None:
        try:
            await self.repository.flush()
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise PrivateBotConflictError(
                "binding_conflict", "The user or Telegram Bot is already registered"
            ) from exc

    async def _rotate_existing_credentials(
        self,
        *,
        bot,
        identity: PrivateBotTelegramIdentity,
        token: str,
        owner_user_id: int,
    ) -> None:
        async with self.admission_lock(int(bot.id)):
            expected_webhook_url = self._webhook_url(bot)
            if identity.webhook_url and identity.webhook_url != expected_webhook_url:
                raise PrivateBotValidationError(
                    "token_has_existing_webhook",
                    "This Telegram Bot is already connected to another webhook",
                )
            encrypted = self.credential_cipher.encrypt(
                token,
                associated_data=bot.webhook_public_id,
            )
            bot.telegram_username = identity.username
            bot.telegram_display_name = identity.display_name
            bot.token_ciphertext = encrypted.ciphertext
            bot.token_key_version = encrypted.key_version
            bot.token_fingerprint = build_token_fingerprint(
                token,
                secret=self.fingerprint_secret,
            )
            before_status = str(bot.runtime_status)
            bot.runtime_status = (
                "disabled"
                if not bot.admin_enabled
                else "paused"
                if not bot.owner_enabled
                else "provisioning"
            )
            self.repository.add_audit(
                bot,
                actor_type="owner",
                actor_identifier=str(owner_user_id),
                action="token_rotated",
                before_status=before_status,
                after_status=bot.runtime_status,
                details={},
            )
            # Commit provisioning while holding the admission fence. Any later
            # update sees a non-active state before the new token is activated.
            await self._persist_binding()

    async def provision(
        self,
        *,
        owner_user_id: int,
        token: str,
        source_config: dict,
    ) -> PrivateBotProvisionResult:
        async with self.operation_lock(owner_user_id):
            return await self._provision_locked(
                owner_user_id=owner_user_id,
                token=token,
                source_config=source_config,
            )

    async def rotate_credentials(
        self,
        *,
        owner_user_id: int,
        token: str,
    ) -> PrivateBotProvisionResult:
        """Rotate only the owner's existing Telegram Bot binding.

        Owner WebApp credentials are a rotation surface, not a second
        provisioning entry point. Loading the row inside the lifecycle lock
        also prevents an earlier route-level identity-map snapshot from
        overwriting a concurrently saved tenant config.
        """

        async with self.operation_lock(owner_user_id):
            return await self._provision_locked(
                owner_user_id=owner_user_id,
                token=token,
                source_config={},
                require_existing=True,
            )

    async def _provision_locked(
        self,
        *,
        owner_user_id: int,
        token: str,
        source_config: dict,
        require_existing: bool = False,
    ) -> PrivateBotProvisionResult:
        normalized_token = token.strip()
        token_match = PRIVATE_QQCC_BOT_TOKEN_PATTERN.fullmatch(normalized_token)
        if token_match is None:
            raise PrivateBotValidationError("invalid_token", "Telegram Bot token is invalid")

        try:
            identity = await self.telegram_gateway.inspect_token(normalized_token)
        except PrivateBotServiceError:
            raise
        except Exception as exc:
            code = str(getattr(exc, "code", "telegram_unavailable"))
            if code == "invalid_token":
                raise PrivateBotValidationError(
                    "invalid_token", "Telegram Bot token is invalid"
                ) from exc
            raise PrivateBotServiceError(
                code,
                "Telegram Bot validation is temporarily unavailable",
            ) from exc
        if int(token_match.group("bot_id")) != identity.bot_id:
            raise PrivateBotValidationError(
                "invalid_token", "Telegram Bot token is invalid"
            )
        if identity.bot_id in self.forbidden_bot_ids:
            raise PrivateBotValidationError(
                "reserved_bot", "This Telegram Bot cannot be registered"
            )
        if not identity.username:
            raise PrivateBotValidationError(
                "invalid_bot_identity", "Telegram Bot username is unavailable"
            )

        existing = await self.repository.get_owner_binding_for_update(owner_user_id)
        if require_existing and existing is None:
            raise PrivateBotNotFoundError(
                "not_found",
                "Private Bot was not found",
            )
        duplicate = await self.repository.get_by_telegram_bot_id(identity.bot_id)
        if duplicate is not None and duplicate is not existing:
            raise PrivateBotConflictError(
                "telegram_bot_already_bound", "This Telegram Bot is already registered"
            )
        if existing is not None and int(existing.telegram_bot_id) != identity.bot_id:
            raise PrivateBotConflictError(
                "owner_already_bound", "Each user can register only one private Bot"
            )

        created = existing is None
        if created:
            if identity.webhook_url:
                raise PrivateBotValidationError(
                    "token_has_existing_webhook",
                    "This Telegram Bot is already connected to another webhook",
                )
            public_id = secrets.token_urlsafe(24)
            encrypted = self.credential_cipher.encrypt(
                normalized_token,
                associated_data=public_id,
            )
            bot = PrivateQqccBot(
                owner_user_id=int(owner_user_id),
                telegram_bot_id=identity.bot_id,
                telegram_username=identity.username,
                telegram_display_name=identity.display_name,
                token_ciphertext=encrypted.ciphertext,
                token_key_version=encrypted.key_version,
                token_fingerprint=build_token_fingerprint(
                    normalized_token,
                    secret=self.fingerprint_secret,
                ),
                webhook_public_id=public_id,
                config=copy.deepcopy(source_config),
                config_version=1,
                owner_enabled=True,
                admin_enabled=True,
                runtime_status="provisioning",
            )
            self.repository.add_bot(bot)
            self.repository.add_audit(
                bot,
                actor_type="owner",
                actor_identifier=str(owner_user_id),
                action="created",
                before_status=None,
                after_status="provisioning",
                details={"telegram_bot_id": identity.bot_id},
            )
        else:
            bot = existing
            await self._rotate_existing_credentials(
                bot=bot,
                identity=identity,
                token=normalized_token,
                owner_user_id=owner_user_id,
            )

        if created:
            await self._persist_binding()

        if created or self._config_requires_tenant_media_clone(bot.config or {}):
            config_source = source_config if created else dict(bot.config or {})
            if not await self._clone_initial_config(bot, config_source):
                return self._result(bot, created=created)

        if not bot.admin_enabled:
            bot.runtime_status = "disabled"
            await self.repository.commit()
            return self._result(bot, created=created)
        if not bot.owner_enabled:
            bot.runtime_status = "paused"
            await self.repository.commit()
            return self._result(bot, created=created)

        await self._activate(
            bot,
            token=normalized_token,
            actor_type="owner",
            success_action="webhook_activated",
        )
        return self._result(bot, created=created)

    async def _activate(
        self,
        bot,
        *,
        token: str,
        actor_type: str,
        success_action: str,
        actor_identifier: str | None = None,
    ) -> None:
        webhook_secret = secrets.token_urlsafe(32)
        before_status = str(bot.runtime_status)
        bot.runtime_status = "provisioning"
        await self.repository.commit()
        try:
            await self.telegram_gateway.set_webhook(
                token=token,
                url=self._webhook_url(bot),
                secret_token=webhook_secret,
                drop_pending_updates=True,
            )
        except Exception:
            bot.runtime_status = "error"
            # A timed-out setWebhook request may still have been accepted by Telegram.
            # Retaining the candidate hash lets ingress authenticate and safely drop
            # updates while this tenant is in the error state.
            bot.webhook_secret_hash = hashlib.sha256(
                webhook_secret.encode("utf-8")
            ).hexdigest()
            bot.last_error_code = "webhook_registration_failed"
            bot.last_error_message = "Telegram webhook registration failed"
            self.repository.add_audit(
                bot,
                actor_type="system",
                actor_identifier=None,
                action="webhook_failed",
                before_status=before_status,
                after_status="error",
                details={
                    "error_code": bot.last_error_code,
                    "requested_action": success_action,
                },
            )
            await self.repository.commit()
            return

        bot.webhook_secret_hash = hashlib.sha256(
            webhook_secret.encode("utf-8")
        ).hexdigest()
        bot.runtime_status = "active"
        bot.last_error_code = None
        bot.last_error_message = None
        self.repository.add_audit(
            bot,
            actor_type=actor_type,
            actor_identifier=(
                actor_identifier
                if actor_identifier is not None
                else str(bot.owner_user_id)
                if actor_type == "owner"
                else None
            ),
            action=success_action,
            before_status=before_status,
            after_status="active",
            details={},
        )
        await self.repository.commit()

    def decrypt_token(self, bot) -> str:
        return self.credential_cipher.decrypt(
            bot.token_ciphertext,
            key_version=bot.token_key_version,
            associated_data=bot.webhook_public_id,
        )

    async def pause(self, *, owner_user_id: int):
        async with self.operation_lock(owner_user_id):
            return await self._pause_locked(owner_user_id=owner_user_id)

    async def _pause_locked(self, *, owner_user_id: int):
        bot = await self._require_owner_bot(owner_user_id)
        async with self.admission_lock(int(bot.id)):
            bot.owner_enabled = False
            await self._deactivate(
                bot,
                status="disabled" if not bot.admin_enabled else "paused",
                actor_type="owner",
                actor_identifier=str(owner_user_id),
                action="owner_paused",
            )
        return bot

    async def resume(self, *, owner_user_id: int):
        async with self.operation_lock(owner_user_id):
            return await self._resume_locked(owner_user_id=owner_user_id)

    async def _resume_locked(self, *, owner_user_id: int):
        bot = await self._require_owner_bot(owner_user_id)
        async with self.admission_lock(int(bot.id)):
            bot.owner_enabled = True
            if not bot.admin_enabled:
                bot.runtime_status = "disabled"
                self.repository.add_audit(
                    bot,
                    actor_type="owner",
                    actor_identifier=str(owner_user_id),
                    action="owner_resumed",
                    before_status="disabled",
                    after_status="disabled",
                    details={"blocked_by_admin": True},
                )
                await self.repository.commit()
                return bot
            await self._activate(
                bot,
                token=self.decrypt_token(bot),
                actor_type="owner",
                success_action="owner_resumed",
            )
        return bot

    async def retry(self, *, owner_user_id: int):
        async with self.operation_lock(owner_user_id):
            return await self._retry_locked(owner_user_id=owner_user_id)

    async def _retry_locked(self, *, owner_user_id: int):
        bot = await self._require_owner_bot(owner_user_id)
        async with self.admission_lock(int(bot.id)):
            if not bot.admin_enabled:
                raise PrivateBotConflictError(
                    "admin_disabled", "This private Bot is disabled"
                )
            if not bot.owner_enabled:
                raise PrivateBotConflictError(
                    "owner_paused", "This private Bot is paused"
                )
            if self._config_requires_tenant_media_clone(bot.config or {}):
                if not await self._clone_initial_config(bot, dict(bot.config or {})):
                    return bot
            await self._activate(
                bot,
                token=self.decrypt_token(bot),
                actor_type="owner",
                success_action="webhook_retried",
            )
        return bot

    async def set_admin_enabled(
        self,
        *,
        owner_user_id: int,
        enabled: bool,
        admin_identifier: str,
        expected_private_bot_id: int,
    ):
        async with self.operation_lock(owner_user_id):
            return await self._set_admin_enabled_locked(
                owner_user_id=owner_user_id,
                enabled=enabled,
                admin_identifier=admin_identifier,
                expected_private_bot_id=expected_private_bot_id,
            )

    async def _set_admin_enabled_locked(
        self,
        *,
        owner_user_id: int,
        enabled: bool,
        admin_identifier: str,
        expected_private_bot_id: int,
    ):
        bot = await self._require_owner_bot(
            owner_user_id,
            expected_private_bot_id=expected_private_bot_id,
        )
        async with self.admission_lock(int(bot.id)):
            bot.admin_enabled = bool(enabled)
            if not enabled:
                await self._deactivate(
                    bot,
                    status="disabled",
                    actor_type="admin",
                    actor_identifier=admin_identifier,
                    action="admin_disabled",
                )
            elif bot.owner_enabled:
                await self._activate(
                    bot,
                    token=self.decrypt_token(bot),
                    actor_type="admin",
                    success_action="admin_restored",
                    actor_identifier=admin_identifier,
                )
            else:
                before_status = str(bot.runtime_status)
                bot.runtime_status = "paused"
                self.repository.add_audit(
                    bot,
                    actor_type="admin",
                    actor_identifier=admin_identifier,
                    action="admin_restored",
                    before_status=before_status,
                    after_status="paused",
                    details={"owner_paused": True},
                )
                await self.repository.commit()
        return bot

    async def delete_binding(
        self,
        *,
        owner_user_id: int,
        admin_identifier: str,
        expected_private_bot_id: int,
    ) -> None:
        async with self.operation_lock(owner_user_id):
            await self._delete_binding_locked(
                owner_user_id=owner_user_id,
                admin_identifier=admin_identifier,
                expected_private_bot_id=expected_private_bot_id,
            )

    async def _delete_binding_locked(
        self,
        *,
        owner_user_id: int,
        admin_identifier: str,
        expected_private_bot_id: int,
    ) -> None:
        bot = await self._require_owner_bot(
            owner_user_id,
            expected_private_bot_id=expected_private_bot_id,
        )
        async with self.admission_lock(int(bot.id)):
            if await self.active_task_checker(int(bot.id)):
                raise PrivateBotConflictError(
                    "active_tasks",
                    "Permanent unlink is unavailable while tasks are active",
                )
            before_status = str(bot.runtime_status)
            bot.admin_enabled = False
            bot.runtime_status = "disabled"
            await self.repository.commit()
            try:
                await self.telegram_gateway.delete_webhook(
                    token=self.decrypt_token(bot),
                    drop_pending_updates=True,
                )
            except Exception:
                bot.last_error_code = "webhook_delete_failed"
                bot.last_error_message = "Telegram webhook removal failed"
                self.repository.add_audit(
                    bot,
                    actor_type="admin",
                    actor_identifier=admin_identifier,
                    action="permanent_unbind_failed",
                    before_status=before_status,
                    after_status="disabled",
                    details={"error_code": bot.last_error_code},
                )
                await self.repository.commit()
                raise PrivateBotConflictError(
                    "webhook_delete_failed",
                    "Telegram webhook removal must succeed before permanent unlink",
                ) from None
            try:
                await self.tenant_media_cleanup(int(bot.id))
            except Exception:
                bot.last_error_code = "tenant_media_cleanup_failed"
                bot.last_error_message = "Private Bot media cleanup failed"
                self.repository.add_audit(
                    bot,
                    actor_type="admin",
                    actor_identifier=admin_identifier,
                    action="permanent_unbind_failed",
                    before_status=before_status,
                    after_status="disabled",
                    details={"error_code": bot.last_error_code},
                )
                await self.repository.commit()
                raise PrivateBotConflictError(
                    "tenant_media_cleanup_failed",
                    "Tenant media cleanup must succeed before permanent unlink",
                ) from None
            self.repository.add_audit(
                bot,
                actor_type="admin",
                actor_identifier=admin_identifier,
                action="permanent_unbound",
                before_status=before_status,
                after_status=None,
                details={},
            )
            await self.repository.flush()
            await self.repository.delete(bot)
            await self.repository.commit()

    async def _require_owner_bot(
        self,
        owner_user_id: int,
        *,
        expected_private_bot_id: int | None = None,
    ):
        bot = await self.repository.get_owner_binding_for_update(owner_user_id)
        if bot is None:
            raise PrivateBotNotFoundError("not_found", "Private Bot was not found")
        if (
            expected_private_bot_id is not None
            and int(bot.id) != int(expected_private_bot_id)
        ):
            raise PrivateBotConflictError(
                "binding_changed",
                "Private Bot binding changed before the operation was applied",
            )
        return bot

    async def _deactivate(
        self,
        bot,
        *,
        status: str,
        actor_type: str,
        actor_identifier: str | None,
        action: str,
    ) -> None:
        before_status = str(bot.runtime_status)
        bot.runtime_status = status
        await self.repository.commit()
        webhook_deleted = False
        try:
            await self.telegram_gateway.delete_webhook(
                token=self.decrypt_token(bot),
                drop_pending_updates=True,
            )
            webhook_deleted = True
        except Exception:
            bot.last_error_code = "webhook_delete_failed"
            bot.last_error_message = "Telegram webhook removal failed"
        if webhook_deleted:
            bot.webhook_secret_hash = None
        self.repository.add_audit(
            bot,
            actor_type=actor_type,
            actor_identifier=actor_identifier,
            action=action,
            before_status=before_status,
            after_status=status,
            details={},
        )
        await self.repository.commit()
