"""Small, typed contract for capability adapters.

Adapters are deliberately not auto-discovered or executed by the task queue.
A host must explicitly construct and register each adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from mitra.security import RiskLevel


@dataclass(frozen=True)
class AdapterContext:
    instance_id: str
    data_dir: Path


@dataclass(frozen=True)
class AdapterResult:
    capability_id: str
    operation: str
    success: bool
    data: Any = None
    error: str | None = None


@runtime_checkable
class CapabilityAdapter(Protocol):
    capability_id: str
    risk: RiskLevel
    operations: frozenset[str]

    def execute(
        self, operation: str, arguments: dict[str, Any], context: AdapterContext
    ) -> AdapterResult: ...


class AdapterRegistry:
    """Explicit allowlist of adapter objects for one MITRA process."""

    def __init__(self) -> None:
        self._adapters: dict[str, CapabilityAdapter] = {}

    def register(self, adapter: CapabilityAdapter) -> None:
        if not adapter.capability_id or adapter.capability_id in self._adapters:
            raise ValueError("adapter capability ID must be unique and non-empty")
        if not adapter.operations:
            raise ValueError("adapter must declare at least one operation")
        self._adapters[adapter.capability_id] = adapter

    def get(self, capability_id: str) -> CapabilityAdapter | None:
        return self._adapters.get(capability_id)

    def list_registered(self) -> list[str]:
        return sorted(self._adapters)
