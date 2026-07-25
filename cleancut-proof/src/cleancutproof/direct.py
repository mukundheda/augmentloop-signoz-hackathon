"""Direct-provider caller for the CleanCut capture (#11), no OpenRouter.

Mirrors the stopgap `toyworld.direct` (#9) for the same reason it exists there:
OpenRouter credit was never provisioned, and the capture that produces the real
blog/screencast numbers should not be blocked on it. The difference is which
keys we reach for - this capture runs on the keys **the CleanCut product itself
already holds**, so no new credential is needed to grade CleanCut's own jobs:

- `openai/*`  -> api.openai.com, `OPENAI_API_KEY`
- `google/*`  -> Gemini's OpenAI-compatible endpoint, `GOOGLE_API_KEY`
  (also accepts `GEMINI_API_KEY`, the name `toyworld.direct` uses)

Both are OpenAI-wire-format, so one client shape covers both - only the base URL
and key differ. Returns the same `ModelReply` the OpenRouter caller does, so
`run_detections` is unchanged and the emitted telemetry is identical.

Budget: the same fail-loud-before-spending guard as `openrouter_caller` -
the cap is checked *before* each call, so a run aborts rather than overspends.
"""

from __future__ import annotations

import os
from typing import Optional

from gradebook.pricing import price

from .runner import BudgetExceededError, ModelCaller, ModelReply

OPENAI_BASE = "https://api.openai.com/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


def _provider_for(model: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, bare_model_name) for a roster slug."""
    if model.startswith("openai/"):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; the direct provider needs it for "
                f"{model!r}"
            )
        return OPENAI_BASE, key, model.split("/", 1)[1]
    if model.startswith("google/"):
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set; the direct "
                f"provider needs it for {model!r}"
            )
        return GEMINI_BASE, key, model.split("/", 1)[1]
    raise RuntimeError(
        f"direct provider handles openai/* and google/* only, got {model!r}. "
        "anthropic/* needs ANTHROPIC_API_KEY via toyworld.direct's path."
    )


def direct_caller(*, budget_usd: float = 0.50, timeout: int = 120) -> ModelCaller:
    """A `ModelCaller` that reaches OpenAI and Gemini directly.

    Drop-in replacement for `openrouter_caller`; same budget semantics.
    """
    import json
    import urllib.request

    spent = {"usd": 0.0}

    def call(model: str, prompt: str) -> ModelReply:
        if spent["usd"] >= budget_usd:
            raise BudgetExceededError(
                f"per-run budget ${budget_usd:.2f} reached "
                f"(spent ${spent['usd']:.4f})"
            )
        base, key, bare = _provider_for(model)
        body = json.dumps(
            {
                "model": bare,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode()
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)

        usage = payload.get("usage") or {}
        reply = ModelReply(
            text=(payload["choices"][0]["message"]["content"] or "").strip(),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            response_id=str(payload.get("id", f"direct-{bare}")),
        )
        spent["usd"] += price(model, reply.input_tokens, reply.output_tokens)
        return reply

    return call


def spent_so_far(caller: ModelCaller) -> Optional[float]:  # pragma: no cover
    """Not part of the seam; kept out deliberately so callers price from the
    same table the grades do rather than trusting a side channel."""
    return None
