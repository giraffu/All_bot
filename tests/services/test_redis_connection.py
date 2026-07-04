from src.services.redis_connection import (
    DEFAULT_REDIS_CONNECTION_KWARGS,
    build_redis_client,
)


def test_build_redis_client_applies_resilient_connection_defaults():
    calls = []
    sentinel = object()

    def fake_from_url(url, **kwargs):
        calls.append((url, kwargs))
        return sentinel

    result = build_redis_client(
        "redis://example/0",
        decode_responses=True,
        from_url_func=fake_from_url,
    )

    assert result is sentinel
    assert calls == [
        (
            "redis://example/0",
            {
                **DEFAULT_REDIS_CONNECTION_KWARGS,
                "decode_responses": True,
            },
        )
    ]


def test_build_redis_client_allows_call_site_overrides():
    calls = []

    def fake_from_url(url, **kwargs):
        calls.append((url, kwargs))
        return object()

    build_redis_client(
        "redis://example/0",
        from_url_func=fake_from_url,
        socket_timeout=1,
    )

    assert calls[0][1]["socket_timeout"] == 1
    assert calls[0][1]["socket_connect_timeout"] == 5
