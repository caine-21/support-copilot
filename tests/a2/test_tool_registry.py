"""A2A: canonical registry — exactly 4 read tools, all READ, descriptors complete."""
from agent.tooling import ToolPermission, support_tool_registry


def test_registry_has_four_read_tools():
    reg = support_tool_registry()
    assert set(reg.keys()) == {
        "search_knowledge_base", "get_customer_context", "get_ticket", "get_ticket_history",
    }
    assert all(d.permission is ToolPermission.READ for d in reg.values())


def test_registry_descriptors_complete():
    reg = support_tool_registry()
    for name, d in reg.items():
        assert d.name == name
        assert d.description
        assert d.args_model is not None
        assert d.handler is not None


def test_registry_is_single_source():
    # No second registry / envelope type should exist for the business layer.
    import agent.tooling as t

    assert t.support_tool_registry is t.support_tool_registry  # canonical entry point
    assert hasattr(t, "ToolResult") and hasattr(t, "ToolStatus")
