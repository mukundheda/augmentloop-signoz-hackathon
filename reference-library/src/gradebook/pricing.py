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
    # Retired slugs (claude-3.5-haiku retired by Anthropic 2026-02-19;
    # claude-sonnet-4 past its announced retirement; gemini-2.0-flash delisted),
    # no longer in DEFAULT_ROSTER. As of the replay-v2 recording NO committed
    # recording references them any more, so they are kept for older local
    # recordings rather than for anything in this repo: `toyworld.replay`
    # re-prices a recording from this table at run time, and a missing slug
    # fails the whole run loud rather than skipping one row.
    "anthropic/claude-3.5-haiku": ModelRate(0.80, 4.00),
    "anthropic/claude-sonnet-4": ModelRate(3.00, 15.00),
    "google/gemini-2.0-flash": ModelRate(0.10, 0.40),
    # Current roster (refreshed 2026-07-24, ticket #9), grounded against
    # OpenRouter's public /models API: Claude Haiku 4.5 (cheap tier), Claude
    # Sonnet 4.6 (premium tier), Gemini 2.5 Flash Lite (cross-provider cheap
    # contrast - gemini-2.0-flash is no longer listed there).
    "anthropic/claude-haiku-4.5": ModelRate(1.00, 5.00),
    "anthropic/claude-sonnet-4.6": ModelRate(3.00, 15.00),
    "google/gemini-2.5-flash-lite": ModelRate(0.10, 0.40),
    # Roster widened 2026-07-26, every rate re-grounded against OpenRouter's
    # public /models catalog the same day. The point of the wider roster is that
    # right-sizing is a cross-provider question, not an Anthropic-tier question:
    # these five vendors span roughly 100x on input price for the same decision.
    "mistralai/mistral-small-24b-instruct-2501": ModelRate(0.05, 0.08),
    "meta-llama/llama-3.3-70b-instruct": ModelRate(0.13, 0.40),
    "openai/gpt-4o-mini": ModelRate(0.15, 0.60),
    "deepseek/deepseek-chat": ModelRate(0.20, 0.80),
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
