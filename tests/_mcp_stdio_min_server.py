from __future__ import annotations

import os
import sys
from typing import TypedDict

from mcp.server import MCPServer


class PingDTO(TypedDict):
    value: str


server = MCPServer("stdio-minimal")


@server.tool(structured_output=True)
def ping() -> PingDTO:
    return {"value": "pong"}


if __name__ == "__main__":
    print(f"MCP_MIN_SERVER_PID={os.getpid()}", file=sys.stderr, flush=True)
    server.run(transport="stdio")
