"""The real live-mode model client: OpenRouter (ticket #9).

OpenRouter is OpenAI-compatible, so one client and one key reach every roster
model by its slug (the same slugs the pricing table already holds). This module
imports the `openai` SDK lazily inside `__init__`, so importing `toyworld.live`
or running replay never requires the `[live]` extra to be installed.

Requires `OPENROUTER_API_KEY` (or an explicit `api_key=`). Install with
`pip install -e 'toy-world[live]'`.
"""

from __future__ import annotations

import os
from typing import Optional

from .live import ModelDecision
from .world import Junction


def _parse_route(text: str, options: dict[str, float]) -> str:
    """Pull the chosen route letter out of a short model reply.

    We ask the model for just the route letter, but stay robust: take the first
    offered route name that appears in the reply. If none appears, return the
    raw first token so grading records it as a (wrong) choice rather than
    crashing - a bad answer is data, not an error.
    """
    stripped = text.strip()
    for route in options:
        if route in stripped:
            return route
    return stripped.split()[0] if stripped.split() else stripped


class OpenRouterClient:
    """Ask a model, via OpenRouter, to pick the fastest route at a junction."""

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

    def decide(self, *, model: str, junction: Junction) -> ModelDecision:
        offered = ", ".join(
            f"{route}={minutes} min" for route, minutes in junction.options.items()
        )
        prompt = (
            f"At junction {junction.name} you may take one of these routes: {offered}. "
            f"Reply with ONLY the single letter of the fastest route, nothing else."
        )
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=self._max_output_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return ModelDecision(
            chosen=_parse_route(content, junction.options),
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            response_id=response.id,
        )
