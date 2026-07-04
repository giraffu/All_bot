import httpx
import pytest

from src.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
)


@pytest.mark.asyncio
async def test_circuit_breaker_does_not_count_filtered_exceptions():
    breaker = CircuitBreaker(
        failure_threshold=1,
        reset_timeout=30,
        should_record_failure=lambda _exc: False,
    )

    async def raise_client_error():
        raise ValueError("client error")

    with pytest.raises(ValueError):
        await breaker.call(raise_client_error)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_counts_matching_exceptions_and_opens():
    breaker = CircuitBreaker(
        failure_threshold=1,
        reset_timeout=30,
        should_record_failure=lambda _exc: True,
    )

    async def raise_transport_error():
        raise httpx.ConnectError("connection lost")

    with pytest.raises(httpx.ConnectError):
        await breaker.call(raise_transport_error)

    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpenException):
        await breaker.call(raise_transport_error)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_allows_single_probe(monkeypatch):
    now = 1000.0
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=30)
    monkeypatch.setattr("src.circuit_breaker.time.time", lambda: now)

    async def fail_once():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await breaker.call(fail_once)
    assert breaker.state == CircuitState.OPEN

    now = 1031.0
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow_request() is False

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
