from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import aiohttp
from sqlalchemy.dialects.postgresql import insert

from src.database.core import AsyncSessionLocal
from src.database.models import RuntimeCheckpoint
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import settle_membership_plan_in_session
from src.services.order_v2_service import parse_order_payload
from src.services.payment_fulfillment_service import (
    PaymentFulfillmentCommand,
    PaymentFulfillmentDependencies,
    PaymentFulfillmentResult,
    fulfill_payment_command,
)
from src.services.payment_validator import parse_payload_boc
from src.services.ton_payment_config import validate_ton_merchant_address
from src.services.usdt_ton_payment_config import (
    USDT_TON_JETTON_MASTER_ADDRESS,
    USDT_TON_SCALE,
    UsdtTonPaymentAvailability,
    get_usdt_ton_payment_availability,
)

logger = logging.getLogger(__name__)


class UsdtTonPaymentValidator:
    def __init__(
        self,
        bot_app,
        merchant_address: str | None,
        api_base: str | None = None,
        api_key: str | None = None,
        poll_interval_seconds: int | None = None,
    ):
        self.bot_app = bot_app
        self.merchant_address = validate_ton_merchant_address(merchant_address)
        self.jetton_master_address = USDT_TON_JETTON_MASTER_ADDRESS
        self.api_base = (
            api_base
            or os.getenv("TONCENTER_V3_API_BASE")
            or "https://toncenter.com/api/v3"
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("TONCENTER_API_KEY")
        self.poll_interval_seconds = max(
            1,
            int(
                poll_interval_seconds
                or os.getenv("USDT_TON_POLL_INTERVAL_SECONDS", "15")
            ),
        )
        self.last_lt = 0
        self._last_lt_loaded = False

    @property
    def _last_lt_checkpoint_key(self) -> str:
        return (
            f"usdt_ton:{self.merchant_address}:"
            f"{self.jetton_master_address}:last_lt"
        )

    async def poll_transactions(self) -> None:
        logger.info(
            "Starting USDT-TON payment polling for address: %s",
            self.merchant_address,
        )
        while True:
            try:
                await self._check_new_transfers()
            except Exception:
                logger.exception("Error in USDT-TON polling task")
            await asyncio.sleep(self.poll_interval_seconds)

    async def _ensure_last_lt_loaded(self) -> None:
        if self._last_lt_loaded:
            return
        self._last_lt_loaded = True
        try:
            async with AsyncSessionLocal() as db:
                checkpoint = await db.get(
                    RuntimeCheckpoint,
                    self._last_lt_checkpoint_key,
                )
                value = getattr(checkpoint, "value", None)
                if isinstance(value, dict):
                    self.last_lt = max(
                        self.last_lt,
                        int(value.get("last_lt", 0) or 0),
                    )
        except Exception as exc:
            logger.warning("Failed to load USDT-TON last_lt checkpoint: %s", exc)

    async def _persist_last_lt(self) -> None:
        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    insert(RuntimeCheckpoint)
                    .values(
                        key=self._last_lt_checkpoint_key,
                        value={"last_lt": self.last_lt},
                        updated_at=datetime.now(),
                    )
                    .on_conflict_do_update(
                        index_elements=["key"],
                        set_={
                            "value": {"last_lt": self.last_lt},
                            "updated_at": datetime.now(),
                        },
                    )
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as exc:
            logger.warning("Failed to persist USDT-TON last_lt checkpoint: %s", exc)

    async def _advance_last_lt(self, tx_lt: int) -> None:
        if tx_lt <= self.last_lt:
            return
        self.last_lt = tx_lt
        await self._persist_last_lt()

    @staticmethod
    def _same_address(left: str | None, right: str | None) -> bool:
        try:
            return validate_ton_merchant_address(left) == validate_ton_merchant_address(
                right
            )
        except ValueError:
            return False

    async def _check_new_transfers(self) -> None:
        await self._ensure_last_lt_loaded()
        params = {
            "owner_address": self.merchant_address,
            "jetton_master": self.jetton_master_address,
            "direction": "in",
            "limit": 20,
            "sort": "asc",
        }
        if self.last_lt > 0:
            params["start_lt"] = self.last_lt + 1
        headers = {"X-API-Key": self.api_key} if self.api_key else None

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base}/jetton/transfers",
                params=params,
                headers=headers,
            ) as response:
                if response.status == 429:
                    logger.warning("USDT-TON indexer rate limited with HTTP 429")
                    return
                data = await response.json()
                if response.status != 200 or not isinstance(data, dict):
                    logger.warning(
                        "USDT-TON indexer returned invalid response status=%s",
                        response.status,
                    )
                    return

        transfers = data.get("jetton_transfers")
        if not isinstance(transfers, list):
            logger.warning("USDT-TON indexer response has no transfer list")
            return

        for transfer in transfers:
            if not isinstance(transfer, dict):
                continue
            try:
                tx_lt = int(transfer.get("transaction_lt", 0))
            except (TypeError, ValueError):
                tx_lt = 0
            if tx_lt <= self.last_lt:
                continue

            valid_contract = self._same_address(
                transfer.get("jetton_master"),
                self.jetton_master_address,
            )
            valid_destination = self._same_address(
                transfer.get("destination"),
                self.merchant_address,
            )
            tx_hash = str(transfer.get("transaction_hash") or "").strip()
            try:
                amount_microusdt = int(transfer.get("amount", 0))
                forward_ton_amount = int(transfer.get("forward_ton_amount", 0))
            except (TypeError, ValueError):
                amount_microusdt = 0
                forward_ton_amount = 0

            order_comment = parse_payload_boc(
                str(transfer.get("forward_payload") or "")
            )
            parsed_payload = (
                parse_order_payload(order_comment) if order_comment else None
            )
            is_valid = (
                transfer.get("transaction_aborted") is False
                and valid_contract
                and valid_destination
                and bool(tx_hash)
                and amount_microusdt > 0
                and forward_ton_amount >= 1
                and parsed_payload is not None
                and parsed_payload.kind in {"legacy", "v2"}
            )
            if not is_valid:
                await self._advance_last_lt(tx_lt)
                continue

            completed = await self._process_order(
                order_comment,
                amount_microusdt,
                tx_hash,
            )
            if not completed:
                break
            await self._advance_last_lt(tx_lt)

    def _build_fulfillment_dependencies(self) -> PaymentFulfillmentDependencies:
        from src.core.affiliate_core import (
            calculate_and_set_commission_for_paid_order,
            invalidate_invitation_recharge_cache,
            record_affiliate_commission_transaction,
        )

        return PaymentFulfillmentDependencies(
            session_factory=AsyncSessionLocal,
            is_settlement_v2_enabled=is_membership_settlement_v2_enabled,
            settle_membership_plan_in_session_func=settle_membership_plan_in_session,
            calculate_commission_func=calculate_and_set_commission_for_paid_order,
            record_affiliate_transaction_func=record_affiliate_commission_transaction,
            invalidate_invitation_cache_func=invalidate_invitation_recharge_cache,
            warning_func=logger.warning,
        )

    async def _notify_success(
        self,
        result: PaymentFulfillmentResult,
    ) -> None:
        if result.status != "success" or result.notify_chat_id is None:
            return
        await self.bot_app.bot.send_message(
            chat_id=result.notify_chat_id,
            text=(
                "🎉 <b>USDT-TON 充值成功！</b>\n\n"
                f"已购买【{result.plan_name}】\n"
                f"💎 灵石：+{result.credits_granted}\n"
                f"🪪 当前身份：<b>{result.final_identity}</b>"
            ),
            parse_mode="HTML",
        )

    async def _process_order(
        self,
        order_comment: str,
        amount_microusdt: int,
        tx_hash: str,
    ) -> bool:
        try:
            parsed_payload = parse_order_payload(order_comment)
            if parsed_payload.kind == "unknown":
                return True

            order_lookup = None
            legacy_internal_user_id = None
            legacy_display_user_id = None
            legacy_plan_id = None
            if parsed_payload.kind == "v2" and parsed_payload.business_order_id:
                order_lookup = parsed_payload.business_order_id
            else:
                from src.core.user_core import get_or_create_user_by_telegram

                legacy_display_user_id = int(parsed_payload.telegram_user_id)
                internal_user, _ = await get_or_create_user_by_telegram(
                    legacy_display_user_id
                )
                legacy_internal_user_id = internal_user.id
                legacy_plan_id = int(parsed_payload.plan_id)

            result = await fulfill_payment_command(
                PaymentFulfillmentCommand(
                    channel="USDT_TON",
                    order_lookup=order_lookup,
                    external_tx_id=tx_hash,
                    paid_amount=amount_microusdt,
                    paid_unit="micro_usdt",
                    source="usdt_ton_payment_validator",
                    affiliate_source="usdt_ton_payment_validator",
                    audit_source="usdt_ton_payment_validator",
                    legacy_order_id=(
                        order_comment if parsed_payload.kind == "legacy" else None
                    ),
                    legacy_internal_user_id=legacy_internal_user_id,
                    legacy_display_user_id=legacy_display_user_id,
                    legacy_plan_id=legacy_plan_id,
                    legacy_original_price=(
                        amount_microusdt / USDT_TON_SCALE
                        if parsed_payload.kind == "legacy"
                        else None
                    ),
                    notify=self._notify_success,
                ),
                dependencies=self._build_fulfillment_dependencies(),
            )
            return result.status in {"success", "amount_mismatch", "noop"}
        except Exception:
            logger.exception(
                "Error processing USDT-TON order %s",
                order_comment,
            )
            return False


def build_usdt_ton_payment_validator_if_available(
    bot_app,
    *,
    availability: UsdtTonPaymentAvailability | None = None,
    validator_factory=None,
) -> UsdtTonPaymentValidator | None:
    availability = availability or get_usdt_ton_payment_availability()
    if not availability.enabled or not availability.merchant_address:
        if availability.requested_enabled:
            logger.error(
                "event=usdt_ton_payment_configuration_invalid "
                "polling_started=false reason=%s",
                availability.error_reason,
            )
        return None
    factory = validator_factory or UsdtTonPaymentValidator
    return factory(
        bot_app=bot_app,
        merchant_address=availability.merchant_address,
    )
