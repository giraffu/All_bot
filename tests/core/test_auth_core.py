import hashlib
import hmac
import json
import urllib.parse
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.core import auth_core
from src.core import auth_core_password_hash
from src.core import auth_core_telegram_validation
from src.core import auth_core_telegram_verify
from src.core.auth_core_dependencies import AuthCoreDependencies
from src.core.auth_core_password_hash import (
    get_password_hash as get_password_hash_helper,
    verify_password as verify_password_helper,
)
from src.core.auth_core_password_binding import bind_password_to_user, get_bindable_user
from src.core.auth_core_password_login import (
    DUMMY_PASSWORD_HASH,
    authenticate_password_credentials,
)
from src.core.auth_core_telegram_auth import build_telegram_auth_profile
from src.core.auth_core_telegram_verify import (
    build_telegram_data_check_string,
    get_telegram_tokens_to_try,
    is_telegram_auth_date_fresh,
)
from src.core.auth_core_telegram_validation import (
    verify_telegram_authorization as verify_telegram_authorization_helper,
    verify_telegram_webapp_initdata as verify_telegram_webapp_initdata_helper,
)
from src.core.auth_core_password_version import (
    blacklist_password_version,
    build_password_version_blacklist_key,
    is_password_version_blacklisted,
)
from src.core.auth_core_rate_limit import (
    build_bind_rate_limit_keys,
    build_login_rate_limit_keys,
    clear_rate_limit,
    increment_rate_limit,
    is_rate_limited,
)


class _FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, *, execute_result=None, get_result=None, flush_side_effect=None):
        self._execute_result = execute_result
        self._get_result = get_result
        self._flush_side_effect = flush_side_effect
        self.execute = AsyncMock(return_value=execute_result)
        self.get = AsyncMock(return_value=get_result)
        self.flush = AsyncMock(side_effect=flush_side_effect)
        self.rollback = AsyncMock()
        self.commit = AsyncMock()
        self.add = MagicMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_auth_core_dependencies(
    *,
    redis,
    session_factory,
    get_or_create_user_by_telegram_func=None,
    get_user_detailed_stats_func=None,
    check_web_access_func=None,
):
    return AuthCoreDependencies(
        redis=redis,
        session_factory=session_factory,
        get_or_create_user_by_telegram_func=(
            get_or_create_user_by_telegram_func or AsyncMock()
        ),
        get_user_detailed_stats_func=get_user_detailed_stats_func or AsyncMock(),
        check_web_access_func=check_web_access_func or AsyncMock(return_value=True),
    )


@pytest.mark.asyncio
async def test_telegram_verify_helpers_validate_auth_date_and_tokens():
    logger = MagicMock()

    assert build_telegram_data_check_string({"b": "2", "a": "1"}) == "a=1\nb=2"

    assert (
        is_telegram_auth_date_fresh(
            "100",
            stale_log_message="stale",
            logger=logger,
            time_func=lambda: 999,
        )
        is True
    )
    assert (
        is_telegram_auth_date_fresh(
            "100",
            stale_log_message="stale",
            logger=logger,
            time_func=lambda: 1001,
        )
        is False
    )
    logger.error.assert_called_once_with("stale")

    assert get_telegram_tokens_to_try(
        bot_token="prod-token",
        logger=logger,
    ) == ["prod-token"]
    assert (
        get_telegram_tokens_to_try(
            bot_token=None,
            logger=logger,
        )
        == []
    )
    assert logger.error.call_args_list[-1].args == ("No BOT_TOKEN configured!",)


def test_telegram_verify_helper_uses_runtime_default_time_binding(monkeypatch):
    logger = MagicMock()
    runtime_time = MagicMock(return_value=1001)

    monkeypatch.setattr(auth_core_telegram_verify.time, "time", runtime_time)

    assert (
        auth_core_telegram_verify.is_telegram_auth_date_fresh(
            "100",
            stale_log_message="stale",
            logger=logger,
        )
        is False
    )
    runtime_time.assert_called_once_with()
    logger.error.assert_called_once_with("stale")


@pytest.mark.asyncio
async def test_password_hash_helpers_round_trip():
    hashed_password = await get_password_hash_helper("secret")

    assert hashed_password != "secret"
    assert await verify_password_helper("secret", hashed_password) is True
    assert await verify_password_helper("wrong", hashed_password) is False


@pytest.mark.asyncio
async def test_password_hash_helpers_use_runtime_default_bindings(monkeypatch):
    runtime_to_thread = AsyncMock(return_value="hashed-value")
    runtime_get_password_hash_sync = MagicMock(return_value="ignored")

    monkeypatch.setattr(auth_core_password_hash.asyncio, "to_thread", runtime_to_thread)
    monkeypatch.setattr(
        auth_core_password_hash,
        "get_password_hash_sync",
        runtime_get_password_hash_sync,
    )

    result = await auth_core_password_hash.get_password_hash("secret")

    assert result == "hashed-value"
    runtime_to_thread.assert_awaited_once_with(runtime_get_password_hash_sync, "secret")


@pytest.mark.asyncio
async def test_verify_password_helper_uses_runtime_default_bindings(monkeypatch):
    runtime_to_thread = AsyncMock(return_value=True)
    runtime_verify_password_sync = MagicMock(return_value=True)

    monkeypatch.setattr(auth_core_password_hash.asyncio, "to_thread", runtime_to_thread)
    monkeypatch.setattr(
        auth_core_password_hash,
        "verify_password_sync",
        runtime_verify_password_sync,
    )

    result = await auth_core_password_hash.verify_password("secret", "hashed")

    assert result is True
    runtime_to_thread.assert_awaited_once_with(
        runtime_verify_password_sync,
        "secret",
        "hashed",
    )


def test_telegram_validation_helpers_accept_valid_widget_and_webapp_payloads():
    logger = MagicMock()
    token = "prod-token"

    def auth_date_checker(*_args, **_kwargs):
        return True

    widget_payload = {
        "id": "42",
        "auth_date": "1700000000",
        "first_name": "Test",
    }
    widget_hash = hmac.new(
        hashlib.sha256(token.encode()).digest(),
        build_telegram_data_check_string(widget_payload).encode(),
        hashlib.sha256,
    ).hexdigest()

    assert (
        verify_telegram_authorization_helper(
            {**widget_payload, "hash": widget_hash},
            bot_token=token,
            logger=logger,
            is_auth_date_fresh_func=auth_date_checker,
        )
        is True
    )

    webapp_user = {"id": 42, "first_name": "Test"}
    webapp_payload = {
        "auth_date": "1700000000",
        "query_id": "query-1",
        "user": json.dumps(webapp_user, separators=(",", ":")),
    }
    webapp_hash = hmac.new(
        hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(),
        build_telegram_data_check_string(webapp_payload).encode(),
        hashlib.sha256,
    ).hexdigest()
    init_data = urllib.parse.urlencode({**webapp_payload, "hash": webapp_hash})

    assert (
        verify_telegram_webapp_initdata_helper(
            init_data,
            bot_token=token,
            logger=logger,
            is_auth_date_fresh_func=auth_date_checker,
        )
        == webapp_user
    )


def test_telegram_validation_helpers_use_runtime_default_bindings(monkeypatch):
    logger = MagicMock()
    runtime_build_data_check_string = MagicMock(return_value="payload")
    runtime_get_tokens_to_try = MagicMock(return_value=["prod-token"])
    runtime_is_auth_date_fresh = MagicMock(return_value=True)

    monkeypatch.setattr(
        auth_core_telegram_validation,
        "build_telegram_data_check_string",
        runtime_build_data_check_string,
    )
    monkeypatch.setattr(
        auth_core_telegram_validation,
        "get_telegram_tokens_to_try",
        runtime_get_tokens_to_try,
    )
    monkeypatch.setattr(
        auth_core_telegram_validation,
        "is_telegram_auth_date_fresh",
        runtime_is_auth_date_fresh,
    )
    monkeypatch.setattr(
        auth_core_telegram_validation.hmac,
        "compare_digest",
        lambda *_args, **_kwargs: True,
    )

    assert auth_core_telegram_validation.verify_telegram_authorization(
        {
            "id": "42",
            "auth_date": "1700000000",
            "first_name": "Test",
            "hash": "valid-signature",
        },
        bot_token="prod-token",
        logger=logger,
    )

    runtime_is_auth_date_fresh.assert_called_once()
    runtime_build_data_check_string.assert_called_once()
    runtime_get_tokens_to_try.assert_called_once()


def test_telegram_webapp_validation_helper_uses_runtime_default_bindings(monkeypatch):
    logger = MagicMock()
    runtime_build_data_check_string = MagicMock(return_value="payload")
    runtime_get_tokens_to_try = MagicMock(return_value=["prod-token"])
    runtime_is_auth_date_fresh = MagicMock(return_value=True)
    webapp_user = {"id": 42}
    init_data = urllib.parse.urlencode(
        {
            "auth_date": "1700000000",
            "query_id": "query-1",
            "user": json.dumps(webapp_user, separators=(",", ":")),
            "hash": "valid-signature",
        }
    )

    monkeypatch.setattr(
        auth_core_telegram_validation,
        "build_telegram_data_check_string",
        runtime_build_data_check_string,
    )
    monkeypatch.setattr(
        auth_core_telegram_validation,
        "get_telegram_tokens_to_try",
        runtime_get_tokens_to_try,
    )
    monkeypatch.setattr(
        auth_core_telegram_validation,
        "is_telegram_auth_date_fresh",
        runtime_is_auth_date_fresh,
    )
    monkeypatch.setattr(
        auth_core_telegram_validation.hmac,
        "compare_digest",
        lambda *_args, **_kwargs: True,
    )

    assert (
        auth_core_telegram_validation.verify_telegram_webapp_initdata(
            init_data,
            bot_token="prod-token",
            logger=logger,
        )
        == webapp_user
    )

    runtime_is_auth_date_fresh.assert_called_once()
    runtime_build_data_check_string.assert_called_once()
    runtime_get_tokens_to_try.assert_called_once()


@pytest.mark.asyncio
async def test_build_telegram_auth_profile_normalizes_name_and_optional_fields():
    profile = build_telegram_auth_profile(
        {
            "id": 42,
            "first_name": "Test",
            "last_name": "User",
            "username": "tester",
            "language_code": "zh-hans",
        }
    )

    assert profile.tg_id == 42
    assert profile.username == "tester"
    assert profile.full_name == "Test User"
    assert profile.language_code == "zh-hans"


@pytest.mark.asyncio
async def test_authenticate_and_get_user_uses_widget_profile_for_user_creation(
    monkeypatch,
):
    user = SimpleNamespace(telegram_id=42)
    stats = {"identity": "inner"}

    monkeypatch.setattr(auth_core, "verify_telegram_authorization", lambda _data: True)
    get_or_create_user = AsyncMock(return_value=(user, False))
    monkeypatch.setattr(
        auth_core,
        "build_auth_core_dependencies",
        lambda: _build_auth_core_dependencies(
            redis=SimpleNamespace(),
            session_factory=lambda: None,
            get_or_create_user_by_telegram_func=get_or_create_user,
            get_user_detailed_stats_func=AsyncMock(return_value=stats),
        ),
    )

    result_user, result_stats = await auth_core.authenticate_and_get_user(
        widget_data={
            "id": 42,
            "hash": "sig",
            "auth_date": "1700000000",
            "first_name": "Test",
            "last_name": "User",
            "username": "tester",
            "language_code": "zh-hans",
        }
    )

    assert result_user is user
    assert result_stats == stats
    get_or_create_user.assert_awaited_once_with(
        tg_id=42,
        username="tester",
        full_name="Test User",
        language_code="zh-hans",
    )


@pytest.mark.asyncio
async def test_authenticate_password_credentials_uses_dummy_hash_when_user_missing():
    session = _FakeSession(execute_result=_FakeResult(None))
    verify_password = AsyncMock(return_value=False)

    attempt = await authenticate_password_credentials(
        session=session,
        username="TesTer",
        password="wrong",
        verify_password_func=verify_password,
    )

    assert attempt.user is None
    assert attempt.is_valid is False
    verify_password.assert_awaited_once_with("wrong", DUMMY_PASSWORD_HASH)


@pytest.mark.asyncio
async def test_authenticate_password_credentials_returns_valid_user_when_password_matches():
    user = SimpleNamespace(id=1, hashed_password="stored-hash")
    session = _FakeSession(execute_result=_FakeResult(user))
    verify_password = AsyncMock(return_value=True)

    attempt = await authenticate_password_credentials(
        session=session,
        username="TesTer",
        password="secret",
        verify_password_func=verify_password,
    )

    assert attempt.user is user
    assert attempt.is_valid is True
    verify_password.assert_awaited_once_with("secret", "stored-hash")


@pytest.mark.asyncio
async def test_auth_core_rate_limit_helpers_build_expected_keys_and_delegate_to_redis():
    redis = SimpleNamespace(eval=AsyncMock(return_value=1), delete=AsyncMock())

    assert build_login_rate_limit_keys(client_ip="127.0.0.1", username="TesTer") == (
        "allbot:ratelimit:login:ip:127.0.0.1",
        "allbot:ratelimit:login:user:tester",
    )
    assert build_bind_rate_limit_keys(client_ip="127.0.0.1", user_id=9) == (
        "allbot:ratelimit:bind:ip:127.0.0.1",
        "allbot:ratelimit:bind:user:9",
    )

    assert (
        await is_rate_limited(
            redis=redis,
            ip_key="ip-key",
            user_key="user-key",
            max_attempts=5,
            check_script="check-script",
        )
        is True
    )
    await increment_rate_limit(
        redis=redis,
        ip_key="ip-key",
        user_key="user-key",
        expire_seconds=900,
        incr_script="incr-script",
    )
    await clear_rate_limit(redis=redis, ip_key="ip-key", user_key="user-key")

    assert redis.eval.await_args_list[0].args == (
        "check-script",
        2,
        "ip-key",
        "user-key",
        5,
    )
    assert redis.eval.await_args_list[1].args == (
        "incr-script",
        2,
        "ip-key",
        "user-key",
        900,
    )
    redis.delete.assert_awaited_once_with("ip-key", "user-key")


@pytest.mark.asyncio
async def test_auth_core_password_version_helpers_build_and_delegate_to_redis():
    redis = SimpleNamespace(get=AsyncMock(return_value="1"), setex=AsyncMock())

    assert build_password_version_blacklist_key(user_id=9, password_version=3) == (
        "allbot:auth:blacklist:9:3"
    )

    await blacklist_password_version(
        redis=redis,
        user_id=9,
        password_version=3,
    )
    assert (
        await is_password_version_blacklisted(
            redis=redis,
            user_id=9,
            password_version=3,
        )
        is True
    )

    redis.setex.assert_awaited_once_with("allbot:auth:blacklist:9:3", 604800, "1")
    redis.get.assert_awaited_once_with("allbot:auth:blacklist:9:3")


@pytest.mark.asyncio
async def test_get_bindable_user_raises_when_user_missing():
    session = _FakeSession(get_result=None)
    check_web_access = AsyncMock()

    with pytest.raises(auth_core.AuthCoreError, match="用户不存在。"):
        await get_bindable_user(
            session=session,
            user_id=9,
            check_web_access_func=check_web_access,
            user_not_found_error_factory=lambda: auth_core.AuthCoreError(
                "用户不存在。"
            ),
            insufficient_permission_error_factory=lambda: (
                auth_core.InsufficientPermissionError("权限不足")
            ),
        )

    check_web_access.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_bindable_user_raises_when_web_access_denied():
    user = SimpleNamespace(id=9)
    session = _FakeSession(get_result=user)
    check_web_access = AsyncMock(return_value=False)

    with pytest.raises(auth_core.InsufficientPermissionError, match="权限不足"):
        await get_bindable_user(
            session=session,
            user_id=9,
            check_web_access_func=check_web_access,
            user_not_found_error_factory=lambda: auth_core.AuthCoreError(
                "用户不存在。"
            ),
            insufficient_permission_error_factory=lambda: (
                auth_core.InsufficientPermissionError("权限不足")
            ),
        )

    check_web_access.assert_awaited_once_with(9)


@pytest.mark.asyncio
async def test_bind_password_to_user_hashes_updates_and_flushes_session():
    user = SimpleNamespace(
        id=9, username="old", hashed_password="old-hash", password_version=3
    )
    session = _FakeSession()
    get_password_hash = AsyncMock(return_value="new-hash")

    previous_password_version = await bind_password_to_user(
        session=session,
        user=user,
        username="new-name",
        password="secret",
        get_password_hash_func=get_password_hash,
    )

    assert previous_password_version == 3
    assert user.username == "new-name"
    assert user.hashed_password == "new-hash"
    assert user.password_version == 4
    session.add.assert_called_once_with(user)
    session.flush.assert_awaited_once()
    get_password_hash.assert_awaited_once_with("secret")


@pytest.mark.asyncio
async def test_authenticate_user_by_password_raises_rate_limit_before_db(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(return_value=1), delete=AsyncMock())
    session_factory = MagicMock()

    monkeypatch.setattr(
        auth_core,
        "build_auth_core_dependencies",
        lambda: _build_auth_core_dependencies(
            redis=redis,
            session_factory=session_factory,
        ),
    )

    with pytest.raises(auth_core.RateLimitError):
        await auth_core.authenticate_user_by_password("tester", "secret", "127.0.0.1")

    session_factory.assert_not_called()
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_user_by_password_increments_rate_limit_on_invalid_credentials(
    monkeypatch,
):
    redis = SimpleNamespace(eval=AsyncMock(side_effect=[0, 1]), delete=AsyncMock())
    session = _FakeSession(execute_result=_FakeResult(None))

    monkeypatch.setattr(
        auth_core,
        "build_auth_core_dependencies",
        lambda: _build_auth_core_dependencies(
            redis=redis,
            session_factory=lambda: session,
        ),
    )
    monkeypatch.setattr(auth_core, "verify_password", AsyncMock(return_value=False))

    with pytest.raises(auth_core.InvalidCredentialsError):
        await auth_core.authenticate_user_by_password("tester", "wrong", "127.0.0.1")

    assert redis.eval.await_count == 2
    assert redis.eval.await_args_list[1].args[0] == auth_core.INCR_RATE_LIMIT_SCRIPT
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_user_by_password_returns_stats_and_clears_rate_limit(
    monkeypatch,
):
    user = SimpleNamespace(id=1, telegram_id=42, hashed_password="stored-hash")
    stats = {"level": "inner"}
    redis = SimpleNamespace(eval=AsyncMock(return_value=0), delete=AsyncMock())
    session = _FakeSession(execute_result=_FakeResult(user))

    monkeypatch.setattr(
        auth_core,
        "build_auth_core_dependencies",
        lambda: _build_auth_core_dependencies(
            redis=redis,
            session_factory=lambda: session,
            get_user_detailed_stats_func=AsyncMock(return_value=stats),
            check_web_access_func=AsyncMock(return_value=True),
        ),
    )
    monkeypatch.setattr(auth_core, "verify_password", AsyncMock(return_value=True))

    result_user, result_stats = await auth_core.authenticate_user_by_password(
        "tester", "secret", "127.0.0.1"
    )

    assert result_user is user
    assert result_stats == stats
    redis.delete.assert_awaited_once_with(
        "allbot:ratelimit:login:ip:127.0.0.1",
        "allbot:ratelimit:login:user:tester",
    )


@pytest.mark.asyncio
async def test_bind_user_password_rolls_back_and_increments_rate_limit_on_integrity_error(
    monkeypatch,
):
    user = SimpleNamespace(
        id=7, username="old", hashed_password="old-hash", password_version=2
    )
    redis = SimpleNamespace(
        eval=AsyncMock(side_effect=[0, 1]), delete=AsyncMock(), setex=AsyncMock()
    )
    session = _FakeSession(
        get_result=user,
        flush_side_effect=IntegrityError("duplicate", {}, None),
    )

    monkeypatch.setattr(
        auth_core,
        "build_auth_core_dependencies",
        lambda: _build_auth_core_dependencies(
            redis=redis,
            session_factory=lambda: session,
            check_web_access_func=AsyncMock(return_value=True),
        ),
    )
    monkeypatch.setattr(
        auth_core, "get_password_hash", AsyncMock(return_value="new-hash")
    )

    with pytest.raises(auth_core.AuthCoreError, match="道号已被其他道友占用"):
        await auth_core.bind_user_password(7, "new-name", "secret", "127.0.0.1")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    assert redis.eval.await_count == 2
    assert redis.eval.await_args_list[1].args[0] == auth_core.INCR_RATE_LIMIT_SCRIPT
    redis.delete.assert_not_awaited()
    redis.setex.assert_not_awaited()


@pytest.mark.asyncio
async def test_bind_user_password_commits_and_blacklists_previous_password_version(
    monkeypatch,
):
    user = SimpleNamespace(
        id=9, username="old", hashed_password="old-hash", password_version=3
    )
    redis = SimpleNamespace(
        eval=AsyncMock(return_value=0), delete=AsyncMock(), setex=AsyncMock()
    )
    session = _FakeSession(get_result=user)

    monkeypatch.setattr(
        auth_core,
        "build_auth_core_dependencies",
        lambda: _build_auth_core_dependencies(
            redis=redis,
            session_factory=lambda: session,
            check_web_access_func=AsyncMock(return_value=True),
        ),
    )
    monkeypatch.setattr(
        auth_core, "get_password_hash", AsyncMock(return_value="new-hash")
    )

    await auth_core.bind_user_password(9, "new-name", "secret", "127.0.0.1")

    assert user.username == "new-name"
    assert user.hashed_password == "new-hash"
    assert user.password_version == 4
    session.add.assert_called_once_with(user)
    session.commit.assert_awaited_once()
    redis.delete.assert_awaited_once_with(
        "allbot:ratelimit:bind:ip:127.0.0.1",
        "allbot:ratelimit:bind:user:9",
    )
    redis.setex.assert_awaited_once_with("allbot:auth:blacklist:9:3", 604800, "1")
