"""Machine-readable registry of MITRA capabilities and their availability."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from mitra.security import RiskLevel


@dataclass(frozen=True)
class Capability:
    id: str
    title: str
    status: str
    risk: RiskLevel
    description: str
    scopes: tuple[str, ...] = ()
    adapter: str | None = None

    def to_dict(self) -> dict:
        value = asdict(self)
        value["risk"] = self.risk.value
        value["scopes"] = list(self.scopes)
        return value


_CAPABILITIES = (
    Capability("mcp-core", "MCP server", "ready", RiskLevel.READ, "Expose local MITRA tools through MCP."),
    Capability("instance-isolation", "Instance isolation", "ready", RiskLevel.READ, "Separate data by instance identifier."),
    Capability("local-memory", "Local memory", "ready", RiskLevel.READ, "Store and retrieve instance-local notes."),
    Capability("task-queue", "Durable task queue", "ready", RiskLevel.WRITE, "Create, claim, retry, cancel and inspect task records."),
    Capability("task-audit", "Task audit history", "ready", RiskLevel.READ, "Inspect task lifecycle events."),
    Capability("plan-validation", "Plan validation", "ready", RiskLevel.READ, "Validate structured plans and declared capabilities."),
    Capability("model-provider", "OpenAI-compatible model provider", "optional", RiskLevel.EXTERNAL, "Optional remote model API; configured with environment variables.", ("model:invoke",), "providers"),
    Capability("filesystem-read", "Filesystem read adapter", "planned", RiskLevel.READ, "Scoped file listing and reading.", ("filesystem:read",), "filesystem"),
    Capability("filesystem-write", "Filesystem write adapter", "planned", RiskLevel.WRITE, "Scoped file creation and modification.", ("filesystem:write",), "filesystem"),
    Capability("browser", "Browser automation", "planned", RiskLevel.EXTERNAL, "Policy-bound browser navigation and actions.", ("browser:read", "browser:act"), "browser"),
    Capability("gmail", "Gmail integration", "planned", RiskLevel.EXTERNAL, "Gmail API through user-authorized OAuth.", ("gmail.readonly", "gmail.send"), "gmail"),
    Capability("calendar", "Calendar integration", "planned", RiskLevel.EXTERNAL, "Calendar access through user-authorized OAuth.", ("calendar.readonly", "calendar.events"), "calendar"),
    Capability("multi-agent", "Agent delegation", "planned", RiskLevel.EXTERNAL, "Scoped delegation between independently identified agents.", ("agent:delegate",), "federation"),
)


def list_capabilities(*, include_planned: bool = True) -> list[dict]:
    entries = _CAPABILITIES if include_planned else tuple(
        item for item in _CAPABILITIES if item.status in {"ready", "optional"}
    )
    return [item.to_dict() for item in entries]


def get_capability(capability_id: str) -> Capability | None:
    return next((item for item in _CAPABILITIES if item.id == capability_id), None)
