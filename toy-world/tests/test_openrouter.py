"""Ticket #30 - the default live provider must fail loud on a missing key even
on a `[test]`-only install.

`OpenRouterClient` is the default and documented live client. Its constructor
imports the `openai` SDK lazily so that replay mode never needs the `[live]`
extra; the same must hold for its fail-loud path, or the error a user sees when
they forget the key is a ModuleNotFoundError about `openai` rather than the
sentence naming OPENROUTER_API_KEY. This test runs on the documented test
install, where `openai` is deliberately absent.
"""

import pytest

from toyworld.openrouter import OpenRouterClient


def test_missing_key_fails_loud_naming_the_env_var(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterClient()


def test_explicit_api_key_beats_a_missing_env_var(monkeypatch):
    """An injected key must not be second-guessed by the env check - the guard
    exists to catch an absent key, not to require the env var specifically."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Reaching the SDK import is the pass condition: the key check let it
    # through. Whether `openai` is installed is an install-shape question, not
    # this guard's, so either outcome proves the check did not fire.
    try:
        OpenRouterClient(api_key="sk-test-not-a-real-key")
    except ModuleNotFoundError as exc:
        assert "openai" in str(exc)
    except RuntimeError as exc:  # pragma: no cover - the regression this guards
        pytest.fail(f"key check rejected an explicitly supplied key: {exc}")
