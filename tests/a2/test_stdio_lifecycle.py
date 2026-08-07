"""A2A: stdio connection lifecycle — documented, lazy, per-execute (no pooling).

Current design: MCPToolAdapter constructs a fresh Client per execute call, so
each tool call is one stdio subprocess. No connection pooling yet (A5/A6 may
optimize). A high-risk early stop never pays a cold-start cost.
"""
from agent.tooling import MCPToolAdapter


def test_mcp_adapter_has_no_persistent_session():
    adapter = MCPToolAdapter()
    # The adapter must not keep a reusable client/session between calls; each
    # execute() opens and closes its own stdio process.
    assert not hasattr(adapter, "session")
    assert not hasattr(adapter, "client")


def test_gateway_backend_exposed_for_trace():
    from agent.tooling import ScopedToolGateway, support_tool_registry

    local = ScopedToolGateway(support_tool_registry(), specialist="knowledge", backend="local")
    mcp = ScopedToolGateway(support_tool_registry(), specialist="knowledge", backend="mcp")
    assert local.backend == "local"
    assert mcp.backend == "mcp"
