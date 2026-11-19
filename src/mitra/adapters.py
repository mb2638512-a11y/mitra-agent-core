"""Small, typed contract for capability adapters.

Adapters are deliberately not auto-discovered or executed by the task queue.
A host must explicitly construct and register each adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from mitra.security import RiskLevel
from mitra.registry import get_capability


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



@dataclass(frozen=True)
class AdapterExecutionPermit:
    task_id: str
    capability_id: str
    operation: str
    adapter: CapabilityAdapter
    context: AdapterContext


def authorize_adapter_execution(
    *, store: Any, registry: AdapterRegistry, instance_id: str,
    data_dir: Path, task_id: str, lease_token: str,
    capability_id: str, operation: str,
) -> AdapterExecutionPermit:
    """Validate every execution boundary immediately before an adapter side effect.

    This function returns permission only; callers remain responsible for recording
    a receipt and invoking the adapter exactly once.
    """
    task = store.get_task(task_id)
    if task is None:
        raise ValueError("task not found")
    now = datetime.now(timezone.utc).isoformat()
    if (
        task["status"] != "running"
        or task["lease_token"] != lease_token
        or not task["lease_until"]
        or task["lease_until"] <= now
    ):
        raise PermissionError("adapter execution requires an active running-task lease")

    capability = get_capability(capability_id)
    if capability is None or capability.status != "ready":
        raise PermissionError("capability is not registered as ready")
    adapter = registry.get(capability_id)
    if adapter is None:
        raise PermissionError("capability adapter is not installed")
    if operation not in adapter.operations:
        raise PermissionError("operation is not allowlisted by this adapter")

    order = {
        RiskLevel.READ: 0,
        RiskLevel.WRITE: 1,
        RiskLevel.EXTERNAL: 2,
        RiskLevel.FINANCIAL: 3,
        RiskLevel.DESTRUCTIVE: 4,
    }
    if order[adapter.risk] < order[capability.risk]:
        raise PermissionError("adapter risk is below the registered capability minimum")
    if order[RiskLevel(task["risk"])] < order[adapter.risk]:
        raise PermissionError("task risk is below the adapter's minimum risk")

    return AdapterExecutionPermit(
        task_id=task_id,
        capability_id=capability_id,
        operation=operation,
        adapter=adapter,
        context=AdapterContext(instance_id, data_dir),
    )
