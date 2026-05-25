from src.api_client import get_system_status
from src.core.billing_core import (
    BillingCoreProviders,
    configure_billing_core_providers,
    get_configured_billing_core_providers,
)
from src.quota import QuotaManager
from src.services.permission_service import permission_service
from src.services.redis_client import redis_client

_quota_manager = QuotaManager()


def ensure_billing_core_providers_registered() -> BillingCoreProviders:
    configured = get_configured_billing_core_providers()
    if configured is not None:
        return configured

    return configure_billing_core_providers(
        BillingCoreProviders(
            get_system_status_func=get_system_status,
            get_permission_service_func=lambda: permission_service,
            get_redis_client_func=lambda: redis_client,
            get_quota_manager_func=lambda: _quota_manager,
        )
    )
