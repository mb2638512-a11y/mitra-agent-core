import json
from unittest.mock import MagicMock, patch

import pytest

from mitra.providers import ChatMessage, OpenAICompatibleProvider, configured_provider


def test_provider_requires_https_or_http():
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(base_url="file:///tmp", model="x", api_key_env="KEY")


def test_provider_requires_environment_key(monkeypatch):
    monkeypatch.delenv("MITRA_TEST_KEY", raising=False)
    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1", model="model-a", api_key_env="MITRA_TEST_KEY"
    )
    with pytest.raises(RuntimeError, match="Missing API key"):
        provider.complete([ChatMessage("user", "hello")])


def test_provider_sends_openai_compatible_request(monkeypatch):
    monkeypatch.setenv("MITRA_TEST_KEY", "secret-value")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({
        "model": "model-a", "choices": [{"message": {"content": "hello back"}}],
        "usage": {"total_tokens": 8},
    }).encode()
    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1/", model="model-a", api_key_env="MITRA_TEST_KEY"
    )
    with patch("urllib.request.urlopen", return_value=response) as mocked:
        reply = provider.complete([ChatMessage("user", "hello")])
    assert reply.content == "hello back"
    assert reply.usage["total_tokens"] == 8
    request = mocked.call_args.args[0]
    assert request.full_url == "https://example.test/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer secret-value"


def test_provider_is_opt_in(monkeypatch):
    monkeypatch.delenv("MITRA_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MITRA_MODEL_NAME", raising=False)
    assert configured_provider() is None
