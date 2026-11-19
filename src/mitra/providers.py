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
