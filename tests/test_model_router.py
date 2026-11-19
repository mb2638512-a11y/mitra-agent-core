import json

import pytest

from mitra.providers import (
    ChatMessage,
    ModelReply,
    ModelRouter,
    configured_router,
)


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.result = result or ModelReply("ok", "fake", {"total_tokens": 1})
        self.error = error
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_model_router_uses_named_route_and_fallback():
    primary = FakeProvider(error=RuntimeError("secret should not leak"))
    backup = FakeProvider(ModelReply("backup", "backup-model", {}))
    router = ModelRouter(
        {"primary": primary, "backup": backup},
        default_provider="primary",
        routes={"planning": ["primary", "backup"]},
    )
    reply = router.complete([ChatMessage("user", "plan")], route="planning")
    assert reply.content == "backup"
    assert primary.calls == 1
    assert backup.calls == 1


def test_model_router_rejects_unknown_route_provider():
    with pytest.raises(ValueError, match="unknown"):
        ModelRouter(
            {"only": FakeProvider()},
            default_provider="only",
            routes={"planning": ["missing"]},
        )


def test_model_router_does_not_leak_provider_exception_text():
    router = ModelRouter(
        {"primary": FakeProvider(error=RuntimeError("api-key=secret"))},
        default_provider="primary",
    )
    with pytest.raises(RuntimeError) as error:
        router.complete([ChatMessage("user", "hello")])
    assert "api-key" not in str(error.value)
    assert "RuntimeError" in str(error.value)


def test_configured_router_loads_provider_metadata_without_inline_secrets(monkeypatch):
    monkeypatch.setenv("MITRA_MODEL_PROVIDERS", json.dumps([
        {"id": "local", "base_url": "http://127.0.0.1:11434/v1",
         "model": "local-model", "api_key_env": "LOCAL_MODEL_KEY"},
        {"id": "cloud", "base_url": "https://api.example.test/v1",
         "model": "cloud-model", "api_key_env": "CLOUD_MODEL_KEY"},
    ]))
    monkeypatch.setenv("MITRA_MODEL_DEFAULT", "local")
    monkeypatch.setenv("MITRA_MODEL_ROUTES", json.dumps({"planning": ["local", "cloud"]}))
    router = configured_router()
    assert router is not None
    assert router.status() == {
        "default_provider": "local",
        "providers": ["cloud", "local"],
        "routes": {"planning": ["local", "cloud"]},
    }



def test_remote_model_provider_rejects_plain_http():
    from mitra.providers import OpenAICompatibleProvider

    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleProvider(
            base_url="http://api.example.test/v1",
            model="unsafe-model",
            api_key_env="MODEL_KEY",
        )
