"""Ticket #9 - direct-provider live client (temporary stopgap while OpenRouter
credits are provisioned): Anthropic native SDK + Google's OpenAI-compatible
Gemini endpoint. Updated by ticket #33 for the Query-based `decide` signature
(decision-type-agnostic: the client just sends `query.prompt` and calls
`query.parse`).

Fakes are duck-typed stand-ins for the real `anthropic` and `openai` SDK
response shapes DirectClient reads from - no SDK import, no key, no spend -
same discipline as test_live.py's FakeClient. `DirectClient` accepts
pre-built clients precisely so tests never touch a real SDK or key.
"""

import pytest

from toyworld.direct import DirectClient
from toyworld.live import DEFAULT_ROSTER, MAX_OUTPUT_TOKENS, ModelDecision, run_live
from toyworld.world import ALL_QUERIES, ROUTE_CHOICE_QUERIES

Q1 = ROUTE_CHOICE_QUERIES[0]  # a lettered A/B route_choice query, like old J1


# --- fakes: duck-typed stand-ins for the real SDK response shapes ---


class _AnthropicTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _AnthropicThinkingBlock:
    """A thinking block as emitted by models with adaptive thinking on by
    default (e.g. claude-sonnet-5) - it precedes the text block and has no
    usable `.text`, so DirectClient must skip it."""

    type = "thinking"

    def __init__(self, thinking="considering the routes..."):
        self.thinking = thinking


class _AnthropicUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _AnthropicResponse:
    def __init__(self, text, input_tokens=200, output_tokens=10, response_id="msg_fake1"):
        self.content = [_AnthropicTextBlock(text)]
        self.usage = _AnthropicUsage(input_tokens, output_tokens)
        self.id = response_id


class FakeAnthropicMessages:
    """Records every create() call (so tests can assert on kwargs) and returns
    a canned response."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeAnthropicClient:
    def __init__(self, response):
        self.messages = FakeAnthropicMessages(response)


class _ChatMessage:
    def __init__(self, content):
        self.content = content


class _ChatChoice:
    def __init__(self, content):
        self.message = _ChatMessage(content)


class _ChatUsage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _ChatResponse:
    def __init__(
        self, content, prompt_tokens=150, completion_tokens=8, response_id="chatcmpl-fake1"
    ):
        self.choices = [_ChatChoice(content)]
        self.usage = _ChatUsage(prompt_tokens, completion_tokens)
        self.id = response_id


class FakeChatCompletions:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeChat:
    def __init__(self, response):
        self.completions = FakeChatCompletions(response)


class FakeGeminiClient:
    def __init__(self, response):
        self.chat = FakeChat(response)


# --- routing ---


def test_routes_anthropic_slugs_to_the_anthropic_fake():
    anthropic_client = FakeAnthropicClient(_AnthropicResponse("A"))
    gemini_client = FakeGeminiClient(_ChatResponse("A"))
    client = DirectClient(anthropic_client=anthropic_client, gemini_client=gemini_client)

    client.decide(model="anthropic/claude-haiku-4.5", query=Q1)

    assert len(anthropic_client.messages.calls) == 1
    assert len(gemini_client.chat.completions.calls) == 0


def test_routes_google_slugs_to_the_gemini_fake():
    anthropic_client = FakeAnthropicClient(_AnthropicResponse("A"))
    gemini_client = FakeGeminiClient(_ChatResponse("A"))
    client = DirectClient(anthropic_client=anthropic_client, gemini_client=gemini_client)

    client.decide(model="google/gemini-2.5-flash-lite", query=Q1)

    assert len(gemini_client.chat.completions.calls) == 1
    assert len(anthropic_client.messages.calls) == 0


# --- anthropic response parsing ---


def test_anthropic_response_parses_into_correct_model_decision_fields():
    response = _AnthropicResponse(
        "A", input_tokens=321, output_tokens=7, response_id="msg_abc123"
    )
    client = DirectClient(anthropic_client=FakeAnthropicClient(response))

    decision = client.decide(model="anthropic/claude-haiku-4.5", query=Q1)

    assert decision == ModelDecision(
        chosen="A", input_tokens=321, output_tokens=7, response_id="msg_abc123"
    )


def test_anthropic_thinking_block_before_text_block_is_skipped():
    # Models with adaptive thinking on by default (claude-sonnet-5, already in
    # ANTHROPIC_MODEL_IDS for a future roster swap) emit a thinking block
    # BEFORE the text block; parsing must find the text block, not content[0].
    response = _AnthropicResponse("A", response_id="msg_think1")
    response.content = [_AnthropicThinkingBlock(), _AnthropicTextBlock("A")]
    client = DirectClient(anthropic_client=FakeAnthropicClient(response))

    decision = client.decide(model="anthropic/claude-sonnet-5", query=Q1)

    assert decision.chosen == "A"
    assert decision.response_id == "msg_think1"


def test_anthropic_call_omits_temperature_and_sets_max_tokens():
    anthropic_client = FakeAnthropicClient(_AnthropicResponse("A"))
    client = DirectClient(anthropic_client=anthropic_client)

    client.decide(model="anthropic/claude-haiku-4.5", query=Q1)

    call_kwargs = anthropic_client.messages.calls[0]
    # Anthropic calls never pass temperature (brief, and unlike the OpenAI-
    # compatible path which is fine setting temperature=0).
    assert "temperature" not in call_kwargs
    # Bound to the shared constant, not a literal: the cap has to stay big
    # enough for a model that shows its working (see live.MAX_OUTPUT_TOKENS).
    assert call_kwargs["max_tokens"] == MAX_OUTPUT_TOKENS
    assert call_kwargs["messages"][0]["content"] == Q1.prompt


# --- fail-loud on missing keys ---


def test_missing_anthropic_key_fails_loud_naming_the_env_var(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = DirectClient()

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        client.decide(model="anthropic/claude-haiku-4.5", query=Q1)


def test_missing_gemini_key_fails_loud_naming_the_env_var(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = DirectClient()

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        client.decide(model="google/gemini-2.5-flash-lite", query=Q1)


def test_anthropic_only_use_never_raises_about_gemini(monkeypatch):
    # No GEMINI_API_KEY at all - an anthropic-only roster must never demand it.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    anthropic_client = FakeAnthropicClient(_AnthropicResponse("A"))
    client = DirectClient(anthropic_client=anthropic_client)

    decision = client.decide(model="anthropic/claude-haiku-4.5", query=Q1)

    assert decision.chosen == "A"


# --- unknown provider ---


def test_unknown_prefix_fails_loud_naming_the_slug():
    client = DirectClient()

    with pytest.raises(RuntimeError, match="mistral/foo"):
        client.decide(model="mistral/foo", query=Q1)


# --- protocol conformance end to end ---


def test_run_live_with_direct_client_fakes_produces_a_correct_summary(world):
    """DirectClient must plug into run_live exactly like OpenRouterClient or the
    test FakeClient does - proving it satisfies the ModelClient protocol, not
    just its own unit tests. Every fake answers via `query.parse`/`query.correct`
    directly (not string-matching the prompt), so it is agnostic to which of
    the three decision types it's answering."""
    provider, _ = world

    anthropic_calls = []

    class RoutingAnthropicMessages:
        def create(self, **kwargs):
            content = kwargs["messages"][0]["content"]
            query = next(q for q in ALL_QUERIES if q.prompt == content)
            chosen = str(query.correct)
            anthropic_calls.append(chosen)
            return _AnthropicResponse(chosen, response_id=f"msg-{len(anthropic_calls)}")

    class RoutingAnthropicClient:
        def __init__(self):
            self.messages = RoutingAnthropicMessages()

    gemini_calls = []

    class RoutingChatCompletions:
        def create(self, **kwargs):
            content = kwargs["messages"][0]["content"]
            query = next(q for q in ALL_QUERIES if q.prompt == content)
            chosen = str(query.correct)
            gemini_calls.append(chosen)
            return _ChatResponse(chosen, response_id=f"chat-{len(gemini_calls)}")

    class RoutingChat:
        def __init__(self):
            self.completions = RoutingChatCompletions()

    class RoutingGeminiClient:
        def __init__(self):
            self.chat = RoutingChat()

    client = DirectClient(
        anthropic_client=RoutingAnthropicClient(),
        gemini_client=RoutingGeminiClient(),
    )

    summary = run_live(client, budget_usd=10.0, world_provider=provider)

    assert summary.decisions == len(DEFAULT_ROSTER) * len(ALL_QUERIES)
    assert summary.correct == summary.decisions  # every fake always answers correctly
    assert not summary.budget_exhausted
    assert set(summary.by_model) == set(DEFAULT_ROSTER)
    assert len(anthropic_calls) == 2 * len(ALL_QUERIES)  # 2 anthropic/* slugs in the roster
    assert len(gemini_calls) == 1 * len(ALL_QUERIES)  # 1 google/* slug in the roster
