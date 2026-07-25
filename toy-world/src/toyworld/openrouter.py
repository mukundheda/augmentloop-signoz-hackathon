"""The default live-mode model client: OpenRouter (ticket #9, extended by #33).

OpenRouter is OpenAI-compatible, so one client and one key reach every roster
model by its slug (the same slugs the pricing table already holds). This module
imports the `openai` SDK lazily inside `__init__`, so importing `toyworld.live`
or running replay never requires the `[live]` extra to be installed. The
prompt text and reply parsing live on the `Query` itself (`world.py`), so this
client is decision-type-agnostic: it sends `query.prompt` and calls
`query.parse` on the reply, the same way regardless of whether the query is a
route_choice, eta_estimate, or next_hop - `direct.py` does the same, so every
provider answers the exact same question.

Requires `OPENROUTER_API_KEY` (or an explicit `api_key=`). Install with
`pip install -e 'toy-world[live]'`.
"""

from __future__ import annotations

import os
from typing import Optional

from .live import ModelDecision
from .world import Query


class OpenRouterClient:
    """Ask a model, via OpenRouter, to answer one query."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        max_output_tokens: int = 64,
    ):
        from openai import OpenAI  # lazy: only needed for a real live run

        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; live mode needs an OpenRouter key "
                "(replay mode needs no key - use `python -m toyworld`)."
            )
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._max_output_tokens = max_output_tokens

    def decide(self, *, model: str, query: Query) -> ModelDecision:
        response = self._client.chat.completions.create(
            model=model,
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
