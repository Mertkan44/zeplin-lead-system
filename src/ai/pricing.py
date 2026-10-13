"""Provider prices and token accounting for AI calls.

Rates come from `ai_model_rates` (provider + model + start date, entered from
the provider's official price list). Unknown models stay unpriced (cost
None) rather than guessed. Every result says which source it used, so a
ledger row can be reconciled with the provider's invoice later.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any

from src.config import env
from src.ai.billing_calendar import billing_period

logger = logging.getLogger(__name__)

# Share of input tokens assumed when estimating a job before it runs.
ESTIMATE_INPUT_SHARE = 0.75
ESTIMATE_TOKENS_PER_LEAD = {True: 9000, False: 5200}  # deep research on / off

_RATE_TTL_SECONDS = 600
_rate_rows: tuple[float, list[dict[str, Any]]] | None = None


def usage_split(usage: dict[str, Any] | None) -> dict[str, int]:
    """Token counts from any provider's usage object (DeepSeek, OpenAI-style, Groq)."""
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int(
        usage.get("prompt_cache_hit_tokens")
        or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        or usage.get("cached_tokens")
        or 0
    )
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or prompt + completion)
    return {
        "prompt_tokens": prompt,
        "cached_tokens": min(cached, prompt),
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _table_rows() -> list[dict[str, Any]]:
    global _rate_rows
    now = time.monotonic()
    if _rate_rows and now - _rate_rows[0] < _RATE_TTL_SECONDS:
        return _rate_rows[1]
    try:
        from src.storage.supabase import fetch_model_rates, is_enabled

        rows = fetch_model_rates() if is_enabled() else []
    except Exception as exc:  # a pricing lookup must not stop generation
        logger.warning("ai_model_rates lookup failed: %s", exc)
        rows = []
    _rate_rows = (now, rows)
    return rows


def rates_for(provider: str, model: str | None, *, on: date | None = None,
              at: datetime | None = None, for_estimate: bool = False) -> dict[str, Any] | None:
    """USD per million tokens: {input, cached_input, output, source, effective_from}."""
    date_only = on is not None and at is None
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("Pricing timestamp must include a timezone")
    on = on or at.astimezone(timezone.utc).date()
    candidates = [
        row for row in _table_rows()
        if row.get("provider") == provider and row.get("model") == model
        and str(row.get("effective_from") or "") <= on.isoformat()
    ]
    if candidates:
        row = max(candidates, key=lambda item: str(item.get("effective_from")))
        multiplier = 1.0
        period = "flat"
        if row.get("pricing_policy") == "deepseek_peak_2026":
            if date_only and not for_estimate:
                return None
            # A queued job may begin in a different billing window: reserve peak.
            period = "peak_upper_bound" if for_estimate else billing_period(at)
            if period is None:
                return None
            if period == "off_peak":
                multiplier = float(row["off_peak_multiplier"])
        elif row.get("pricing_policy"):
            return None  # Unknown policy is not silently treated as flat pricing.
        return {
            "input": float(row["input_usd_per_m"]) * multiplier,
            "cached_input": float(row["cached_input_usd_per_m"]) * multiplier,
            "output": float(row["output_usd_per_m"]) * multiplier,
            "source": "ai_model_rates",
            "effective_from": str(row.get("effective_from")),
            "billing_period": period,
            "priced_at": at.astimezone(timezone.utc).isoformat(),
        }
    return None  # A generic legacy rate must not price an unknown model.


def cost_usd(split: dict[str, int], rates: dict[str, Any] | None) -> float | None:
    if rates is None:
        return None
    uncached = max(split["prompt_tokens"] - split["cached_tokens"], 0)
    return round(
        (uncached * rates["input"] + split["cached_tokens"] * rates["cached_input"] + split["completion_tokens"] * rates["output"])
        / 1_000_000,
        6,
    )


def models_for_mode(ai_mode: str) -> list[str]:
    flash = env("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash") or "deepseek-v4-flash"
    pro = env("DEEPSEEK_PRO_MODEL", env("DEEPSEEK_MODEL", "deepseek-v4-pro")) or "deepseek-v4-pro"
    return {"flash": [flash], "pro": [pro]}.get(ai_mode, [flash, pro])


def estimate_search(*, max_results: int, deep_research: bool, ai_mode: str) -> dict[str, Any]:
    """The one estimate for a search job: shown in the panel and stored as the reservation."""
    tokens = max(1, int(max_results)) * ESTIMATE_TOKENS_PER_LEAD[bool(deep_research)]
    rates = [rates_for("deepseek", model, for_estimate=True) for model in models_for_mode(ai_mode)]
    cost = None
    if all(rates):
        blended = sum(
            ESTIMATE_INPUT_SHARE * rate["input"] + (1 - ESTIMATE_INPUT_SHARE) * rate["output"] for rate in rates
        ) / len(rates)
        cost = round(tokens / 1_000_000 * blended, 4)
    return {
        "estimated_tokens": tokens,
        "estimated_cost_usd": cost if cost is not None else 0,
        "priced": cost is not None,
        "model_mix": "flash+pro" if ai_mode == "smart" else ai_mode,
        "rate_sources": sorted({rate["source"] for rate in rates if rate}),
    }
