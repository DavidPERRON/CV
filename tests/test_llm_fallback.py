"""Tests for the multi-provider fallback chain in LLMClient.

We don't import the real anthropic / openai SDKs — we monkeypatch the per-provider
dispatch methods on the client to simulate success / failure.
"""
from __future__ import annotations

import json

import pytest

from cv_agent.llm.client import LLMClient, LLMError, _is_retryable_provider_error
from cv_agent.settings import Settings


def _settings():
    return Settings(
        llm_provider="anthropic",
        llm_model="claude-opus-4-6",
        llm_fallback_provider="openai",
        llm_fallback_model="gpt-4o",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-openai-test",
    )


class _FakeCreditError(Exception):
    """Looks like an Anthropic credit-exhaustion error."""


def test_chain_uses_primary_when_it_works(monkeypatch):
    client = LLMClient(_settings())
    calls = []

    def fake_anthropic(system, user, model):
        calls.append(("anthropic", model))
        return '{"ok": true}'

    def fake_openai(system, user, model):
        calls.append(("openai", model))
        raise AssertionError("openai should not be called when anthropic succeeds")

    monkeypatch.setattr(client, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(client, "_call_openai", fake_openai)

    out = client.call_json(system="sys", user="u")
    assert out == {"ok": True}
    assert calls == [("anthropic", "claude-opus-4-6")]


def test_chain_falls_back_to_openai_on_anthropic_credit_error(monkeypatch):
    client = LLMClient(_settings())
    calls = []

    def fake_anthropic(system, user, model):
        calls.append(("anthropic", model))
        # Message that matches the credit-exhaustion heuristic
        raise _FakeCreditError("Your credit balance is too low to use this model")

    def fake_openai(system, user, model):
        calls.append(("openai", model))
        return '{"ok": "fallback"}'

    monkeypatch.setattr(client, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(client, "_call_openai", fake_openai)

    out = client.call_json(system="sys", user="u")
    assert out == {"ok": "fallback"}
    assert calls == [
        ("anthropic", "claude-opus-4-6"),
        ("openai", "gpt-4o"),
    ]


def test_chain_falls_back_on_json_parse_error(monkeypatch):
    client = LLMClient(_settings())
    calls = []

    def fake_anthropic(system, user, model):
        calls.append(("anthropic", model))
        return "not json at all, just prose"

    def fake_openai(system, user, model):
        calls.append(("openai", model))
        return '{"ok": "recovered"}'

    monkeypatch.setattr(client, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(client, "_call_openai", fake_openai)

    out = client.call_json(system="sys", user="u")
    assert out == {"ok": "recovered"}
    assert [c[0] for c in calls] == ["anthropic", "openai"]


def test_chain_raises_when_all_providers_fail(monkeypatch):
    client = LLMClient(_settings())

    def fake_anthropic(system, user, model):
        raise _FakeCreditError("quota exceeded")

    def fake_openai(system, user, model):
        raise _FakeCreditError("insufficient_quota: billing limit reached")

    monkeypatch.setattr(client, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(client, "_call_openai", fake_openai)

    with pytest.raises(_FakeCreditError):
        client.call_json(system="sys", user="u")


def test_non_retryable_error_is_not_swallowed(monkeypatch):
    """Programming errors (ValueError, TypeError) must surface immediately."""
    client = LLMClient(_settings())

    def fake_anthropic(system, user, model):
        raise ValueError("bad argument in caller code")

    monkeypatch.setattr(client, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(client, "_call_openai", lambda *a, **k: '{"ok": true}')

    with pytest.raises(ValueError):
        client.call_json(system="sys", user="u")


def test_is_retryable_recognises_credit_messages():
    assert _is_retryable_provider_error(Exception("Your credit balance is too low"))
    assert _is_retryable_provider_error(Exception("insufficient_quota"))
    assert _is_retryable_provider_error(Exception("Rate limit reached"))
    assert not _is_retryable_provider_error(ValueError("typo in JD parser"))
