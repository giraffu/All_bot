from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class AffiliateCoreRepositoryBindings:
    lock_affiliate_balance_owner_func: object
    get_referral_for_invitee_func: object
    get_existing_successful_paid_order_id_func: object
    insert_affiliate_commission_transaction_func: object


@lru_cache(maxsize=1)
def get_default_affiliate_core_repository_bindings() -> AffiliateCoreRepositoryBindings:
    from src.services.affiliate_commission_repository import (
        get_existing_successful_paid_order_id,
        get_referral_for_invitee,
        insert_affiliate_commission_transaction,
        lock_affiliate_balance_owner,
    )

    return AffiliateCoreRepositoryBindings(
        lock_affiliate_balance_owner_func=lock_affiliate_balance_owner,
        get_referral_for_invitee_func=get_referral_for_invitee,
        get_existing_successful_paid_order_id_func=(
            get_existing_successful_paid_order_id
        ),
        insert_affiliate_commission_transaction_func=(
            insert_affiliate_commission_transaction
        ),
    )
