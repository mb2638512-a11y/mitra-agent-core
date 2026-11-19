from mitra.registry import get_capability, list_capabilities


def test_registry_contains_core_and_planned_integrations():
    entries = {item["id"]: item for item in list_capabilities()}
    assert entries["mcp-core"]["status"] == "ready"
    assert entries["gmail"]["status"] == "planned"
    assert entries["browser"]["status"] == "planned"


def test_registry_can_filter_to_installed_capabilities():
    entries = list_capabilities(include_planned=False)
    assert all(item["status"] in {"ready", "optional"} for item in entries)
    assert not any(item["id"] == "gmail" for item in entries)


def test_get_capability_returns_risk_and_scopes():
    capability = get_capability("gmail")
    assert capability is not None
    value = capability.to_dict()
    assert value["risk"] == "external"
    assert "gmail.send" in value["scopes"]


def test_unknown_capability_returns_none():
    assert get_capability("not-a-real-capability") is None
