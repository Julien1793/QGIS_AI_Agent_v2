# Tests for small pure helpers that are easy to break and easy to test.
#
# AIAgent imports `from qgis.core import Qgis` at module top, so it can only
# be imported through the conftest stub. Once imported, we can call its
# helpers with a mock settings_manager — they don't touch QGIS.

from unittest.mock import MagicMock

import pytest

from qgis_ai_plugin.core.agent import AIAgent


@pytest.fixture
def agent():
    return AIAgent(MagicMock())


# ─────────────────────────────────────────────────────────────────────────
# _supports_zero_max_tokens — controls a fallback usage-only request
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1/chat/completions",
    "https://openrouter.ai/api/v1/chat/completions",
    "https://api.fireworks.ai/inference/v1/chat/completions",
    "https://api.mistral.ai/v1/chat/completions",
])
def test_known_remote_urls_support_max_tokens_zero(agent, url):
    # These providers accept max_tokens=0 to retrieve usage stats cheaply
    # without generating any output tokens.
    assert agent._supports_zero_max_tokens(url) is True


def test_lm_studio_localhost_does_not_support_max_tokens_zero(agent):
    # LM Studio rejects max_tokens=0 outright — the helper must return False
    # so the caller falls back to max_tokens=1 + temperature=0.
    assert agent._supports_zero_max_tokens(
        "http://localhost:1234/v1/chat/completions") is False


@pytest.mark.parametrize("model", [
    "mistral-small", "mixtral-8x7b", "codestral-latest", "devstral-7b",
])
def test_mistral_family_models_support_max_tokens_zero(agent, model):
    # Mistral-family models expose max_tokens=0 even when served behind a
    # custom or unknown URL (e.g. a self-hosted vLLM endpoint).
    assert agent._supports_zero_max_tokens("http://my-custom-host/v1",
                                           model) is True


def test_unknown_url_and_unknown_model_returns_false(agent):
    assert agent._supports_zero_max_tokens(
        "http://my-host/v1", "llama-3.1-70b") is False


def test_none_inputs_handled_gracefully(agent):
    assert agent._supports_zero_max_tokens(None, None) is False
    assert agent._supports_zero_max_tokens("", "") is False


# ─────────────────────────────────────────────────────────────────────────
# _extract_final_message — strips the gpt-oss "channel: final" wrapper
# ─────────────────────────────────────────────────────────────────────────

def test_plain_response_returned_unchanged(agent):
    assert agent._extract_final_message("Hello world") == "Hello world"


def test_wrapped_response_unwrapped(agent):
    raw = ("<|start|>assistant<|channel|>analysis<|message|>thinking...\n"
           "<|start|>assistant<|channel|>final<|message|>The answer is 42.")
    assert agent._extract_final_message(raw) == "The answer is 42."


def test_wrapped_response_strips_surrounding_whitespace(agent):
    raw = "<|start|>assistant<|channel|>final<|message|>  trimmed  "
    assert agent._extract_final_message(raw) == "trimmed"
