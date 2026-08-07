"""Local stdio MCP server for the same read-only Support domain services.

Run: py -B -m agent.support_mcp_server
"""
from __future__ import annotations
import os
import sys
from typing import Any

from pydantic import BaseModel, Field

# Several established support modules retain flat imports for direct script
# execution. The server is launched as a package, so keep that compatibility
# path available before invoking the shared domain service.
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import MCPServer
from .tooling import CustomerContextArgs, SearchKnowledgeArgs, TicketHistoryArgs, ToolRuntime, get_customer_context as _get_customer_context, get_ticket_history as _get_ticket_history, search_knowledge_base as _search_knowledge_base

mcp = MCPServer(name="support-copilot-operations", instructions="Read-only local support knowledge, context, and history. These tools never authorize customer actions.")


class MCPToolEvidenceDTO(BaseModel):
    source_id: str
    source_type: str
    locator: str


class MCPToolResultDTO(BaseModel):
    """Protocol-only DTO: no internal enum or runtime model crosses MCP."""
    status: str
    data: Any = None
    evidence: list[MCPToolEvidenceDTO] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False


def _to_mcp_result(result) -> MCPToolResultDTO:
    return MCPToolResultDTO.model_validate(result.model_dump(mode="json"))


@mcp.tool(structured_output=True)
def search_knowledge_base(query: str, top_k: int = 3) -> MCPToolResultDTO:
    """Read matching local KB excerpts. Does not authorize a reply."""
    return _to_mcp_result(search_knowledge_base_service(SearchKnowledgeArgs(query=query, top_k=top_k)))


def search_knowledge_base_service(args):
    return _search_knowledge_base(args, ToolRuntime(user_id="mcp", ticket_text=args.query))


@mcp.tool(structured_output=True)
def get_customer_context(customer_context: dict | None = None) -> MCPToolResultDTO:
    """Read supplied local/synthetic customer context; never changes it."""
    args = CustomerContextArgs(customer_context=customer_context or {})
    return _to_mcp_result(get_customer_context_service(args))


def get_customer_context_service(args):
    return _get_customer_context(args, ToolRuntime(user_id="mcp", ticket_text="", customer_context=args.customer_context))


@mcp.tool(structured_output=True)
def get_ticket_history(user_id: str) -> MCPToolResultDTO:
    """Read local in-memory history. A fresh stdio server has no persisted CRM data."""
    return _to_mcp_result(_get_ticket_history(TicketHistoryArgs(user_id=user_id), ToolRuntime(user_id=user_id, ticket_text="")))


if __name__ == "__main__":
    mcp.run(transport="stdio")
