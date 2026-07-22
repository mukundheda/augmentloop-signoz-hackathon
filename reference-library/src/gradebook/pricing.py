"""Cost from a single per-model pricing table.

Per ADR 0002, cost is a pricing table applied to token counts OpenTelemetry
already reports - not a new cost-observability system, a dollar figure attached
to standard token data so cost and correctness can be divided together. Edit
prices in ONE place: the `PRICES` table below.

Rates are US dollars per 1,000,000 tokens (the industry-standard unit). Values
are vendor list prices and drift - re-check them before submission. The model
roster itself is explicitly low-stakes and changeable (CONTEXT.md).
"""

from __future__ import annotations

from dataclasses import dataclass

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelRate:
    """USD per 1,000,000 tokens, split by direction."""

    input_per_mtok: float
    output_per_mtok: float


# OpenRouter-style model slug -> rate. The default roster (CONTEXT.md): two Claude
# price tiers for the right-sizing story plus a cross-provider contrast.
PRICES: dict[str, ModelRate] = {
    "anthropic/claude-3.5-haiku": ModelRate(0.80, 4.00),
    "anthropic/claude-sonnet-4": ModelRate(3.00, 15.00),
    "google/gemini-2.0-flash": ModelRate(0.10, 0.40),
}


class UnknownModelError(KeyError):
    """Raised when a model has no entry in the pricing table.

    We fail loud rather than emit a decision with no or a wrong cost: a silently
    missing cost would quietly corrupt the headline "cost per correct decision".
    """


class InvalidTokenCountError(ValueError):
    """Raised when token counts are negative.

    Same fail-loud reasoning as `UnknownModelError`: a malformed token count
    would produce a wrong-signed cost and silently corrupt the headline metric.
    """


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost of one model call from the pricing table."""
    if input_tokens < 0 or output_tokens < 0:
        raise InvalidTokenCountError(
            f"token counts must be non-negative, got "
            f"input={input_tokens}, output={output_tokens}"
        )
    try:
        rate = PRICES[model]
    except KeyError:
        raise UnknownModelError(
            f"no price for model {model!r}; add it to gradebook.pricing.PRICES"
        ) from None
    return (
        input_tokens * rate.input_per_mtok + output_tokens * rate.output_per_mtok
    ) / PER_MILLION
