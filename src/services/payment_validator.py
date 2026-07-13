import asyncio
import logging
import os
from datetime import datetime

import aiohttp
from sqlalchemy.dialects.postgresql import insert

from config import VITE_MERCHANT_ADDRESS
from src.database.core import AsyncSessionLocal
from src.database.models import RuntimeCheckpoint
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import settle_membership_plan_in_session
from src.services.payment_fulfillment_service import (
    PaymentFulfillmentCommand,
    PaymentFulfillmentDependencies,
    PaymentFulfillmentResult,
    fulfill_payment_command,
)
from src.services.order_v2_service import (
    parse_order_payload,
)

logger = logging.getLogger(__name__)


def parse_payload_boc(boc_str: str) -> str:
    """
    Parses a BOC payload (base64 or hex) and returns the text comment.
    """
    import base64

    try:
        from pytoniq_core import Cell

        boc_bytes = None

        # Try base64 first
        try:
            boc_bytes = base64.b64decode(boc_str)
            cell = Cell.one_from_boc(boc_bytes)
        except Exception:
            # If base64 fails or Cell parsing fails, try hex
            boc_bytes = bytes.fromhex(boc_str)
            cell = Cell.one_from_boc(boc_bytes)

        slice = cell.begin_parse()
        opcode = slice.load_uint(32)
        if opcode == 0:
            return slice.load_snake_string()
        return None
    except Exception:
        return None


class TonPaymentValidator:
    def __init__(
        self,
        bot_app,
        api_base: str | None = None,
        api_key: str | None = None,
        poll_interval_seconds: int | None = None,
        max_poll_interval_seconds: int | None = None,
    ):
        self.api_base = api_base or os.getenv(
            "TONCENTER_API_BASE", "https://toncenter.com/api/v2/jsonRPC"
        )
        self.api_key = api_key if api_key is not None else os.getenv("TONCENTER_API_KEY")
        self.bot_app = bot_app
        self.merchant_address = VITE_MERCHANT_ADDRESS
        self.last_lt = 0  # Logical time of the last processed transaction
        self.poll_interval_seconds = max(
            1, int(poll_interval_seconds or os.getenv("TON_POLL_INTERVAL_SECONDS", "15"))
        )
        self.max_poll_interval_seconds = max(
            self.poll_interval_seconds,
            int(
                max_poll_interval_seconds
                or os.getenv("TON_POLL_BACKOFF_MAX_SECONDS", "120")
            ),
        )
        self.current_poll_interval_seconds = self.poll_interval_seconds
        self._last_lt_loaded = False

    @property
    def _last_lt_checkpoint_key(self) -> str:
        return f"ton:{self.merchant_address}:last_lt"

    def _reset_poll_interval(self) -> None:
        self.current_poll_interval_seconds = self.poll_interval_seconds

    def _increase_poll_interval(self) -> int:
        self.current_poll_interval_seconds = min(
            self.max_poll_interval_seconds,
            max(self.poll_interval_seconds, self.current_poll_interval_seconds * 2),
        )
        return self.current_poll_interval_seconds

    @staticmethod
    def _extract_rate_limit_message(data) -> str | None:
        candidates = []
        if isinstance(data, dict):
            candidates.extend(
                [
                    data.get("result"),
                    data.get("message"),
                    data.get("error"),
                ]
            )
            error_obj = data.get("error")
            if isinstance(error_obj, dict):
                candidates.extend([error_obj.get("message"), error_obj.get("data")])
        else:
            candidates.append(data)

        for candidate in candidates:
            if isinstance(candidate, str):
                lowered = candidate.lower()
                if "ratelimit" in lowered or "rate limit" in lowered:
                    return candidate
        return None

    async def poll_transactions(self):
        """
        Background task to poll transactions continuously.
        """
        logger.info(
            f"Starting TON payment polling for address: {self.merchant_address}"
        )

        while True:
            try:
                await self._check_new_transactions()
            except Exception as e:
                logger.error(f"Error in TON polling task: {e}")

            await asyncio.sleep(self.current_poll_interval_seconds)

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
                    self.last_lt = max(self.last_lt, int(value.get("last_lt", 0) or 0))
        except Exception as exc:
            logger.warning("Failed to load TON last_lt checkpoint: %s", exc)

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
            logger.warning("Failed to persist TON last_lt checkpoint: %s", exc)

    async def _advance_last_lt(self, tx_lt: int) -> None:
        if tx_lt <= self.last_lt:
            return
        self.last_lt = tx_lt
        await self._persist_last_lt()

    async def _check_new_transactions(self):
        headers = {"X-API-Key": self.api_key} if self.api_key else None
        async with aiohttp.ClientSession() as session:
            payload = {
                "method": "getTransactions",
                "params": {
                    "address": self.merchant_address,
                    "limit": 20,
                    "archival": True,
                },
                "id": 1,
                "jsonrpc": "2.0",
            }

            async with session.post(self.api_base, json=payload, headers=headers) as resp:
                if resp.status == 429:
                    next_interval = self._increase_poll_interval()
                    logger.warning(
                        "TON API rate limited with HTTP 429, backing off polling to %ss",
                        next_interval,
                    )
                    return
                try:
                    data = await resp.json()
                except Exception as e:
                    logger.warning(
                        f"Failed to decode JSON from TON API: {e}. Status: {resp.status}"
                    )
                    return

                if not isinstance(data, dict) or "result" not in data:
                    rate_limit_message = self._extract_rate_limit_message(data)
                    if rate_limit_message:
                        next_interval = self._increase_poll_interval()
                        logger.warning(
                            "TON API rate limited: %s. Backing off polling to %ss",
                            rate_limit_message,
                            next_interval,
                        )
                        return
                    logger.error(f"Failed to fetch transactions or invalid format: {data}")
                    return

                transactions = data["result"]
                if not isinstance(transactions, list):
                    rate_limit_message = self._extract_rate_limit_message(data)
                    if rate_limit_message:
                        next_interval = self._increase_poll_interval()
                        logger.warning(
                            "TON API rate limited: %s. Backing off polling to %ss",
                            rate_limit_message,
                            next_interval,
                        )
                        return
                    logger.error(f"Transactions is not a list: {transactions}")
                    return

                self._reset_poll_interval()
                if transactions:
                    await self._ensure_last_lt_loaded()

                # Process from oldest to newest in the current batch
                for tx in reversed(transactions):
                    if not isinstance(tx, dict):
                        continue

                    tx_id_info = tx.get("transaction_id", {})
                    if not isinstance(tx_id_info, dict):
                        tx_id_info = {}

                    try:
                        tx_lt = int(tx_id_info.get("lt", 0))
                    except (ValueError, TypeError):
                        tx_lt = 0

                    tx_hash = tx_id_info.get("hash", "")

                    if tx_lt <= self.last_lt:
                        continue  # Already processed

                    in_msg = tx.get("in_msg", {})
                    if not isinstance(in_msg, dict) or not in_msg:
                        await self._advance_last_lt(tx_lt)
                        continue

                    try:
                        amount_nanotons = int(in_msg.get("value", 0))
                    except (ValueError, TypeError):
                        amount_nanotons = 0

                    if amount_nanotons <= 0:
                        await self._advance_last_lt(tx_lt)
                        continue

                    # Extract message/payload
                    msg_data = in_msg.get("message", "")
                    if not isinstance(msg_data, str):
                        msg_data = ""

                    msg_data_info = in_msg.get("msg_data", {})
                    if not isinstance(msg_data_info, dict):
                        msg_data_info = {}
                    msg_data_boc = msg_data_info.get("body", "")  # Might be in body

                    # Try to parse payload
                    order_id = None
                    if msg_data_boc:
                        order_id = parse_payload_boc(msg_data_boc)
                    elif msg_data and msg_data.startswith("ORDER:"):
                        # If it's plain text somehow
                        order_id = msg_data

                    parsed_payload = parse_order_payload(order_id) if order_id else None
                    if parsed_payload and parsed_payload.kind in {"legacy", "v2"}:
                        success = await self._process_order(
                            order_id, amount_nanotons, tx_hash
                        )
                        if success:
                            await self._advance_last_lt(tx_lt)
                        else:
                            # If a transaction fails to process (e.g. DB error), we should stop
                            # advancing last_lt and break, so it can be retried in the next poll.
                            break
                    else:
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

    async def _notify_successful_ton_payment(
        self,
        result: PaymentFulfillmentResult,
    ) -> None:
        if result.status != "success" or result.notify_chat_id is None:
            return
        msg_text = (
            f"🎉 <b>充值成功！</b>\n\n"
            f"恭喜道友，您已成功购买【{result.plan_name}】。\n"
            f"💎 获得灵石：+{result.credits_granted}\n"
        )
        if result.is_downgrade:
            msg_text += f"🪪 当前身份保持为：<b>{result.final_identity}</b>\n"
            if result.converted_days > 0:
                msg_text += (
                    "⚖️ 新套餐价值已折算为 "
                    f"<b>{result.converted_days}</b> 天当前高级身份时长\n"
                )
        else:
            msg_text += f"🪪 当前身份晋升为：<b>{result.final_identity}</b>\n"
            if result.converted_days > 0:
                msg_text += (
                    "⚖️ 老套餐残值已折算为 "
                    f"<b>{result.converted_days}</b> 天新套餐时长\n"
                )

        if result.final_expire_at:
            msg_text += f"⏳ 到期时间：{result.final_expire_at}\n\n祝您仙途坦荡！"
        else:
            msg_text += "\n祝您仙途坦荡！"

        await self.bot_app.bot.send_message(
            chat_id=result.notify_chat_id,
            text=msg_text,
            parse_mode="HTML",
        )

    async def _process_order(
        self, order_id: str, amount_nanotons: int, tx_hash: str
    ) -> bool:
        """
        Process a found order: verify amount, fulfill, and notify user.
        Returns True if processing is complete (success or definitive failure), False if it should be retried.
        """
        logger.info(
            f"Processing order from blockchain: {order_id} with amount {amount_nanotons}"
        )

        try:
            parsed_payload = parse_order_payload(order_id)
            if parsed_payload.kind == "unknown":
                logger.warning(f"Invalid order format: {order_id}")
                return True

            legacy_internal_user_id = None
            legacy_display_user_id = None
            legacy_plan_id = None
            order_lookup = None
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
                    channel="TON",
                    order_lookup=order_lookup,
                    external_tx_id=tx_hash,
                    paid_amount=amount_nanotons,
                    paid_unit="nanoton",
                    source="ton_payment_validator",
                    affiliate_source="ton_payment_validator",
                    audit_source="ton_payment_validator",
                    legacy_order_id=order_id if parsed_payload.kind == "legacy" else None,
                    legacy_internal_user_id=legacy_internal_user_id,
                    legacy_display_user_id=legacy_display_user_id,
                    legacy_plan_id=legacy_plan_id,
                    notify=self._notify_successful_ton_payment,
                ),
                dependencies=self._build_fulfillment_dependencies(),
            )
            return result.status in {"success", "amount_mismatch", "noop"}

        except Exception as e:
            logger.error(f"Error processing order {order_id}: {e}")
            return False
