"""Optional OpenAI-compatible model provider; credentials stay in environment variables."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ModelReply:
    content: str
    model: str
    usage: dict


class ModelProvider(Protocol):
    def complete(self, messages: list[ChatMessage]) -> ModelReply: ...


class OpenAICompatibleProvider:
    """Small stdlib-only adapter for providers exposing /v1/chat/completions."""

    def __init__(self, *, base_url: str, model: str, api_key_env: str,
                 timeout_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.api_key_env = api_key_env.strip()
        self.timeout_seconds = timeout_seconds
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if not self.model or not self.api_key_env:
            raise ValueError("model and api_key_env are required")
        if not 1 <= timeout_seconds <= 180:
            raise ValueError("timeout_seconds must be between 1 and 180")

    def complete(self, messages: list[ChatMessage]) -> ModelReply:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {self.api_key_env}")
        if not messages or any(m.role not in {"system", "user", "assistant"} for m in messages):
            raise ValueError("messages must use system, user or assistant roles")
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Never include request headers or the API key in surfaced errors.
            raise RuntimeError(f"Model provider returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Model provider connection failed: {type(exc).__name__}") from None
        try:
            content = result["choices"][0]["message"]["content"]
            returned_model = str(result.get("model") or self.model)
            usage = result.get("usage") or {}
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Model provider returned an unexpected response shape") from exc
        if not isinstance(content, str):
            raise RuntimeError("Model provider response content must be text")
        return ModelReply(content=content, model=returned_model, usage=usage)


def configured_provider() -> OpenAICompatibleProvider | None:
    """Build a provider only when all non-secret settings are configured."""
    base_url = os.getenv("MITRA_MODEL_BASE_URL")
    model = os.getenv("MITRA_MODEL_NAME")
    key_env = os.getenv("MITRA_MODEL_API_KEY_ENV", "MITRA_MODEL_API_KEY")
    if not base_url or not model:
        return None
    return OpenAICompatibleProvider(base_url=base_url, model=model, api_key_env=key_env)



class ModelRouter:
    """Explicit, deterministic model routing with configured fallback chains."""

    def __init__(
        self,
        providers: dict[str, ModelProvider],
        *,
        default_provider: str,
        routes: dict[str, list[str]] | None = None,
    ):
        if not providers or default_provider not in providers:
            raise ValueError("default provider must exist in the provider registry")
        if any(not key or len(key) > 64 for key in providers):
            raise ValueError("provider IDs must contain 1-64 characters")
        self.providers = dict(providers)
        self.default_provider = default_provider
        self.routes = dict(routes or {})
        for route, chain in self.routes.items():
            if not route or not isinstance(chain, list) or not chain:
                raise ValueError("each route must have a non-empty provider chain")
            if len(set(chain)) != len(chain) or any(item not in self.providers for item in chain):
                raise ValueError("route contains duplicate or unknown provider IDs")

    def chain_for(self, route: str | None = None) -> list[str]:
        if route is None:
            return [self.default_provider]
        if not isinstance(route, str) or not route.strip():
            raise ValueError("route name must be non-empty text")
        return list(self.routes.get(route, [self.default_provider]))

    def complete(self, messages: list[ChatMessage], route: str | None = None) -> ModelReply:
        errors = []
        for provider_id in self.chain_for(route):
            try:
                return self.providers[provider_id].complete(messages)
            except Exception as exc:
                # Surface only exception class and provider ID; provider errors may contain secrets.
                errors.append(f"{provider_id}:{type(exc).__name__}")
        raise RuntimeError("all configured model providers failed (" + ", ".join(errors) + ")")

    def status(self) -> dict:
        return {
            "default_provider": self.default_provider,
            "providers": sorted(self.providers),
            "routes": {key: list(value) for key, value in self.routes.items()},
        }


def configured_router() -> ModelRouter | None:
    """Load provider metadata from env; API keys remain in their named env variables.

    MITRA_MODEL_PROVIDERS is a JSON array of objects containing id, base_url, model
    and api_key_env. MITRA_MODEL_ROUTES is an optional JSON object mapping route
    names to ordered provider-ID fallback lists.
    """
    raw = os.getenv("MITRA_MODEL_PROVIDERS")
    if raw:
        try:
            items = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("MITRA_MODEL_PROVIDERS must be valid JSON") from exc
        if not isinstance(items, list) or not items:
            raise ValueError("MITRA_MODEL_PROVIDERS must be a non-empty JSON array")
        providers: dict[str, ModelProvider] = {}
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "base_url", "model", "api_key_env"}:
                raise ValueError("each model provider needs exactly id, base_url, model and api_key_env")
            provider_id = item["id"]
            if not isinstance(provider_id, str) or not provider_id or provider_id in providers:
                raise ValueError("model provider IDs must be unique non-empty strings")
            providers[provider_id] = OpenAICompatibleProvider(
                base_url=item["base_url"], model=item["model"], api_key_env=item["api_key_env"]
            )
        default_id = os.getenv("MITRA_MODEL_DEFAULT", next(iter(providers)))
        try:
            routes = json.loads(os.getenv("MITRA_MODEL_ROUTES", "{}"))
        except json.JSONDecodeError as exc:
            raise ValueError("MITRA_MODEL_ROUTES must be valid JSON") from exc
        if not isinstance(routes, dict) or any(
            not isinstance(key, str) or not isinstance(value, list) for key, value in routes.items()
        ):
            raise ValueError("MITRA_MODEL_ROUTES must map route names to provider-ID arrays")
        return ModelRouter(providers, default_provider=default_id, routes=routes)

    # Backward-compatible single-provider environment configuration.
    provider = configured_provider()
    if provider is None:
        return None
    return ModelRouter({"default": provider}, default_provider="default")
