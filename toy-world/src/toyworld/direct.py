"""TEMPORARY direct-provider live-mode client (ticket #9), used while
OpenRouter credits are provisioned. OpenRouter (`openrouter.py`) remains the
default client and the one this build is designed around; this module is a
stopgap that reaches the same roster models without OpenRouter in the middle,
so live mode can still produce real numbers before the OpenRouter key lands.

Anthropic slugs (`anthropic/*`) go through the native `anthropic` SDK. Google
slugs (`google/*`) go through the `openai` SDK pointed at Gemini's
OpenAI-compatible endpoint - same chat-completions shape `openrouter.py`
already speaks. Both providers send the same `query.prompt` and call the same
`query.parse` (ticket #33's `Query`, `world.py`), so the comparison stays fair
regardless of which client answered or which decision type the query is.

Requires `ANTHROPIC_API_KEY` for anthropic/* roster models and `GEMINI_API_KEY`
for google/* roster models, each checked lazily on the first call that needs
that provider - a single-provider roster never demands the other provider's
key. Install with `pip install -e 'toy-world[live]'`.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .live import ModelDecision
from .world import Query

# OpenRouter-style slug -> native Anthropic model id. Only the roster's Claude
# slugs need an entry here; an anthropic/* slug with no mapping fails loud
# rather than guessing a native id.
ANTHROPIC_MODEL_IDS: dict[str, str] = {
    "anthropic/claude-haiku-4.5": "claude-haiku-4-5",
    "anthropic/claude-sonnet-4.6": "claude-sonnet-4-6",
    # Forward-looking entry only: NOT in DEFAULT_ROSTER or gradebook.PRICES yet.
    # It exists to exercise the adaptive-thinking content-block parse (test_direct).
    # Add a PRICES row before ever putting it in a live roster, or price() will raise.
    "anthropic/claude-sonnet-5": "claude-sonnet-5",
}


class DirectClient:
    """Route each roster slug straight to its provider, no OpenRouter in the middle.

    `anthropic/*` slugs call the native `anthropic` SDK; `google/*` slugs call
    the `openai` SDK against Gemini's OpenAI-compatible endpoint. Both provider
    SDKs are imported and constructed lazily, only on the first call that
    actually needs them - an Anthropic-only roster never imports `openai` or
    demands GEMINI_API_KEY, and a replay-only run never imports either.

    Pass `anthropic_client=` / `gemini_client=` to inject a pre-built (or
    duck-typed fake) client, bypassing both the lazy import and the key check -
    this is how tests exercise routing and response parsing with no SDK and no
    key.
    """

    def __init__(
        self,
        *,
        anthropic_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        anthropic_client: Optional[Any] = None,
        gemini_client: Optional[Any] = None,
        max_output_tokens: int = 64,
    ):
        self._anthropic_api_key = anthropic_api_key
        self._gemini_api_key = gemini_api_key
        self._anthropic_client = anthropic_client
        self._gemini_client = gemini_client
        self._max_output_tokens = max_output_tokens

    def decide(self, *, model: str, query: Query) -> ModelDecision:
        if model.startswith("anthropic/"):
            return self._decide_anthropic(model=model, query=query)
        if model.startswith("google/"):
            return self._decide_google(model=model, query=query)
        raise RuntimeError(
            f"DirectClient has no route for model {model!r}; only anthropic/* "
            "(native Anthropic SDK) and google/* (Gemini OpenAI-compatible "
            "endpoint) slugs are supported. OpenRouter (openrouter.py) can "
            "reach any provider it lists - this direct path is a temporary "
            "stopgap for two providers only."
        )

    def _anthropic(self) -> Any:
        if self._anthropic_client is None:
            # Key check BEFORE the SDK import: a missing key is the far more
            # likely mistake, and it must fail loud naming the env var even on
            # an install without the `[live]` extra. Importing first would
            # shadow that with a ModuleNotFoundError.
            key = self._anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set; the direct provider needs an "
                    "Anthropic key for anthropic/* roster models (replay mode "
                    "needs no key - use `python -m toyworld`; the OpenRouter "
                    "provider needs OPENROUTER_API_KEY instead)."
                )
            from anthropic import Anthropic  # lazy: only needed for a real Anthropic call

            self._anthropic_client = Anthropic(api_key=key)
        return self._anthropic_client

    def _gemini(self) -> Any:
        if self._gemini_client is None:
            # Key check before the SDK import - see _anthropic above.
            key = self._gemini_api_key or os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set; the direct provider needs a "
                    "Gemini key for google/* roster models (replay mode needs "
                    "no key - use `python -m toyworld`; the OpenRouter provider "
                    "needs OPENROUTER_API_KEY instead)."
                )
            from openai import OpenAI  # lazy: only needed for a real Gemini call

            self._gemini_client = OpenAI(
                api_key=key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
        return self._gemini_client

    def _decide_anthropic(self, *, model: str, query: Query) -> ModelDecision:
        native_id = ANTHROPIC_MODEL_IDS.get(model)
        if native_id is None:
            raise RuntimeError(
                f"no native Anthropic model id mapped for slug {model!r}; add it "
                "to toyworld.direct.ANTHROPIC_MODEL_IDS"
            )
        client = self._anthropic()
        # No temperature: the budget guard only cares about token counts, and
        # Anthropic's default sampling is fine for a single-letter answer.
        response = client.messages.create(
            model=native_id,
            max_tokens=self._max_output_tokens,
            messages=[{"role": "user", "content": query.prompt}],
        )
        # First TEXT block, not content[0]: on models where adaptive thinking
        # is on by default (e.g. claude-sonnet-5, already in the mapping above),
        # a thinking block precedes the text block and content[0].text would
        # crash. Current roster models (Haiku 4.5 / Sonnet 4.6) run thinking-off
        # when the param is omitted, but the guard keeps a future swap safe.
        text = next(
            (block.text for block in response.content if block.type == "text"), ""
        )
        return ModelDecision(
            chosen=query.parse(text),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            response_id=response.id,
        )

    def _decide_google(self, *, model: str, query: Query) -> ModelDecision:
        native_id = model.split("/", 1)[1]
        client = self._gemini()
        response = client.chat.completions.create(
            model=native_id,
            max_tokens=self._max_output_tokens,
            temperature=0,
            messages=[{"role": "user", "content": query.prompt}],
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return ModelDecision(
            chosen=query.parse(content),
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            response_id=response.id,
        )
