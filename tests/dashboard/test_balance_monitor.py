from dashboard.backend.services.balance_monitor import _configured_proxy_url


def test_balance_monitor_uses_direct_connection_when_proxy_is_not_configured(monkeypatch):
    monkeypatch.delenv("PROXY_URL", raising=False)

    assert _configured_proxy_url() is None


def test_balance_monitor_preserves_explicit_proxy(monkeypatch):
    monkeypatch.setenv("PROXY_URL", "http://proxy.internal:7890")

    assert _configured_proxy_url() == "http://proxy.internal:7890"
