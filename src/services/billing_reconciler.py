from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.services.payment_validator import build_ton_payment_validator_if_available
from src.services.usdt_ton_payment_validator import (
    build_usdt_ton_payment_validator_if_available,
)

logger = logging.getLogger("billing-reconciler")
RESTART_DELAY_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class BillingReconcilerSpec:
    name: str
    runner: Callable[[], Awaitable[None]]


def build_billing_reconciler_specs(bot_app) -> tuple[BillingReconcilerSpec, ...]:
    specs: list[BillingReconcilerSpec] = []
    ton = build_ton_payment_validator_if_available(bot_app)
    if ton is not None:
        specs.append(BillingReconcilerSpec("ton", ton.poll_transactions))
    usdt = build_usdt_ton_payment_validator_if_available(bot_app)
    if usdt is not None:
        specs.append(BillingReconcilerSpec("usdt-ton", usdt.poll_transactions))
    return tuple(specs)


async def run_billing_channel_supervisor(
    spec: BillingReconcilerSpec,
    *,
    task_states: dict[str, dict[str, Any]],
    stop_event: asyncio.Event | None = None,
) -> None:
    state = task_states.setdefault(spec.name, {"restarts": 0})
    while stop_event is None or not stop_event.is_set():
        state.update(outcome="running", updated_at=time.time())
        try:
            await spec.runner()
            state.update(
                outcome=(
                    "stopped"
                    if stop_event is not None and stop_event.is_set()
                    else "completed"
                ),
                updated_at=time.time(),
            )
            return
        except asyncio.CancelledError:
            state.update(outcome="cancelled", updated_at=time.time())
            raise
        except Exception as exc:
            state.update(
                outcome="error",
                error_type=type(exc).__name__,
                restarts=int(state.get("restarts", 0)) + 1,
                updated_at=time.time(),
            )
            logger.exception("Billing channel crashed channel=%s", spec.name)
            if stop_event is not None and stop_event.is_set():
                state.update(outcome="stopped", updated_at=time.time())
                return
            await asyncio.sleep(RESTART_DELAY_SECONDS)


async def run_billing_reconcilers(
    bot_app,
    *,
    task_states: dict[str, dict[str, Any]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    states = task_states if task_states is not None else {}
    specs = build_billing_reconciler_specs(bot_app)
    if not specs:
        if stop_event is not None:
            await stop_event.wait()
        else:
            await asyncio.Event().wait()
        return
    await asyncio.gather(
        *(
            run_billing_channel_supervisor(
                spec,
                task_states=states,
                stop_event=stop_event,
            )
            for spec in specs
        )
    )
