"""A2A: capability boundary — discovery AND execution both bounded.

Capability withholding: a specialist must not even SEE tools outside its
allowlist, and forcing a call to a non-allowlisted tool must fail FORBIDDEN
before any backend runs.
"""
from agent.tooling import (
    SearchKnowledgeArgs,
    ToolDefinition,
    ToolPermission,
    ToolRuntime,
    ToolStatus,
    ScopedToolGateway,
    support_tool_registry,
)


def _rt():
    return ToolRuntime(user_id="u-1", ticket_text="x")


def _gateway(specialist):
    return ScopedToolGateway(support_tool_registry(), specialist=specialist)


def test_knowledge_discovery_only_search():
    gw = _gateway("knowledge")
    assert {d.name for d in gw.available_tools()} == {"search_knowledge_base"}


def test_knowledge_forced_get_ticket_forbidden():
    gw = _gateway("knowledge")
    res = gw.execute("c1", "get_ticket", {"ticket_id": "T-1"}, _rt(), turn_index=0)
    assert res.status is ToolStatus.FORBIDDEN
    assert res.error_code == "specialist_tool_not_allowed"


def test_knowledge_forced_customer_context_forbidden():
    gw = _gateway("knowledge")
    res = gw.execute("c1", "get_customer_context", {}, _rt(), turn_index=0)
    assert res.status is ToolStatus.FORBIDDEN


def test_support_allowlist_policy_prepared_not_exercised():
    gw = _gateway("support")
    names = {d.name for d in gw.available_tools()}
    assert names == {"search_knowledge_base", "get_customer_context", "get_ticket_history"}
    # get_ticket is service-level; not in Support's discovery view either.
    assert "get_ticket" not in names


def test_write_descriptor_not_discoverable_and_not_executable():
    def _write(_args, _rt):  # pragma: no cover
        return None

    reg = support_tool_registry()
    reg["send_reply_fake"] = ToolDefinition(
        "send_reply_fake", "fake side effect", SearchKnowledgeArgs,
        ToolPermission.EXTERNAL_OR_IRREVERSIBLE, _write,
    )
    gw = ScopedToolGateway(reg, specialist="knowledge")
    # Discovery withholds the write tool.
    assert "send_reply_fake" not in {d.name for d in gw.available_tools()}
    # Even a forced execution is refused before the handler runs.
    res = gw.execute("c1", "send_reply_fake", {"query": "x"}, _rt(), turn_index=0)
    assert res.status is ToolStatus.FORBIDDEN
    assert res.error_code == "specialist_tool_not_allowed"
