"""Per-call AI usage: one ledger row per provider call and per cache hit.

The caller says who the work is for with `usage_context(job_id=..., actor_email=...,
lead_id=...)`; generation code calls `record(...)` without having to pass that
along. The context also counts provider calls and cache hits, so an endpoint
can tell whether anything was paid for.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from src.ai.pricing import cost_usd, rates_for, usage_split
from src.config import env

logger = logging.getLogger(__name__)

_context: ContextVar[dict[str, Any] | None] = ContextVar("ai_usage_context", default=None)

PAID_OUTCOMES = {"success", "empty", "error"}


class BudgetExceeded(RuntimeError):
    """The daily AI budget (AI_DAILY_BUDGET_USD) is spent."""


@contextmanager
def usage_context(**fields: Any) -> Iterator[dict[str, int]]:
    parent = _context.get() or {}
    counters = parent.get("_counters")
    if counters is None:
        counters = {"provider_calls": 0, "cache_hits": 0, "cost_usd": 0.0, "ledger_errors": 0}
    token = _context.set({**parent, **{k: v for k, v in fields.items() if v is not None}, "_counters": counters})
    try:
        yield counters
    finally:
        _context.reset(token)


def current() -> dict[str, Any]:
    return {key: value for key, value in (_context.get() or {}).items() if not key.startswith("_")}


def record(
    *,
    task: str,
    provider: str,
    requested_model: str | None,
    model: str | None,
    outcome: str,
    usage: dict[str, Any] | None = None,
    cache_key: str | None = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one usage row. outcome: success | empty | error | cache_hit."""
    context = current()
    split = usage_split(usage)
    rates = rates_for(provider, model) if outcome in PAID_OUTCOMES else None
    cost = cost_usd(split, rates) if outcome in PAID_OUTCOMES and split["total_tokens"] else (0 if outcome == "cache_hit" else None)
    row = {
        "kind": "usage",
        "task": task,
        "provider": provider,
        "requested_model": requested_model,
        "model": model,
        "outcome": outcome,
        "cache_key": cache_key,
        "job_id": context.get("job_id"),
        "lead_id": context.get("lead_id"),
        "actor_email": context.get("actor_email"),
        "estimated_tokens": 0,
        "estimated_cost_usd": 0,
        "actual_tokens": split["total_tokens"],
        "actual_cost_usd": cost,
        "prompt_tokens": split["prompt_tokens"],
        "cached_tokens": split["cached_tokens"],
        "completion_tokens": split["completion_tokens"],
        "rates": rates,
        "meta": {**(meta or {}), **({"error": error[:300]} if error else {})},
    }
    counters = (_context.get() or {}).get("_counters")
    if counters is not None:
        if outcome == "cache_hit":
            counters["cache_hits"] += 1
        else:
            counters["provider_calls"] += 1
            counters["cost_usd"] += cost or 0
    try:
        from src.storage.supabase import insert_usage_event, is_enabled

        if is_enabled():
            insert_usage_event(row)
    except Exception as exc:  # the call already happened; losing the row must be visible, not fatal
        if counters is not None:
            counters["ledger_errors"] = counters.get("ledger_errors", 0) + 1
        logger.warning("AI usage row not recorded (%s %s): %s", task, outcome, exc)
    return row


def business_day_start(now: datetime | None = None) -> datetime:
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Europe/Istanbul"))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def check_budget() -> None:
    """Refuse a paid call when today's spend reached AI_DAILY_BUDGET_USD (unset: no cap)."""
    raw = env("AI_DAILY_BUDGET_USD")
    if not raw:
        return
    cap = float(raw)
    from src.storage.supabase import fetch_spend_summary, is_enabled

    if not is_enabled():
        return
    spent = float(fetch_spend_summary(today_start=business_day_start()).get("today_cost_usd") or 0)
    if spent >= cap:
        raise BudgetExceeded(f"daily AI budget reached ({spent:.4f} / {cap:.2f} USD)")


def check_job_lease() -> None:
    """Before every paid attempt, including fallback, fail closed on cancellation."""
    context = current()
    if context.get("job_owner"):
        from src.storage.supabase import heartbeat_search_job
        if not heartbeat_search_job(context["job_id"], context["job_owner"]):
            raise RuntimeError("search job lease lost")
