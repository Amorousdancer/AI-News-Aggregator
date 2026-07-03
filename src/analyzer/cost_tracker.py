"""Token counting and USD cost estimation for LLM API calls."""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = structlog.get_logger(__name__)


# Pricing per million tokens (input, output) — update as models/pricing change
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic models
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-4-20250514": (0.80, 4.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    # OpenAI models (for fallback)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # MiMo models (小米)
    "mimo-v2.5-pro": (0.50, 2.00),
    "mimo-v2.5": (0.30, 1.20),
    "mimo-v2-pro": (0.50, 2.00),
}


@dataclass
class CostTracker:
    """Tracks cumulative LLM API costs within a session."""

    daily_budget_usd: float = 20.00
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    daily_cost_usd: float = 0.0
    calls: list[dict] = field(default_factory=list)
    _last_reset_date: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def record_call(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        is_cached_input: bool = False,
    ) -> float:
        """Record an LLM API call and return its estimated cost in USD.

        For cached Anthropic input tokens, 90% discount is applied
        (Anthropic charges 10% of the input price for cache reads).
        """
        # Reset daily counter if date changed
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self.daily_cost_usd = 0.0
            self._last_reset_date = today

        # Get pricing for this model
        input_price, output_price = self._get_pricing(model_name)

        # Calculate cost
        if is_cached_input:
            effective_input_tokens = input_tokens * 0.1  # 90% cache discount
        else:
            effective_input_tokens = input_tokens

        input_cost = (effective_input_tokens / 1_000_000) * input_price
        output_cost = (output_tokens / 1_000_000) * output_price
        call_cost = input_cost + output_cost

        # Update totals
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += call_cost
        self.daily_cost_usd += call_cost

        self.calls.append({
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached": is_cached_input,
            "cost_usd": round(call_cost, 6),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.debug(
            "LLM call recorded",
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(call_cost, 6),
        )

        return call_cost

    def is_over_budget(self) -> bool:
        """Check if daily budget has been exceeded."""
        return self.daily_cost_usd >= self.daily_budget_usd

    @property
    def remaining_budget_usd(self) -> float:
        """Remaining daily budget in USD."""
        return max(0, self.daily_budget_usd - self.daily_cost_usd)

    @staticmethod
    def _get_pricing(model_name: str) -> tuple[float, float]:
        """Get (input_price, output_price) per million tokens for a model."""
        # Exact match first
        if model_name in MODEL_PRICING:
            return MODEL_PRICING[model_name]

        # Partial match (e.g., "claude-sonnet-4-20250514" matches "claude-sonnet-4")
        for key, pricing in MODEL_PRICING.items():
            if model_name.startswith(key.split("-20")[0]):  # Match without date suffix
                return pricing

        # Default fallback pricing (conservative estimate)
        logger.warning("Unknown model pricing, using default", model=model_name)
        return (5.00, 15.00)


# Module-level singleton instance (used by health check and other modules)
cost_tracker = CostTracker()
