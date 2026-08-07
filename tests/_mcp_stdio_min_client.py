from __future__ import annotations

import asyncio
import os
import sys
import time

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    root = os.path.dirname(os.path.dirname(__file__))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-u", "-B", "tests/_mcp_stdio_min_server.py"],
        cwd=root,
        env={"PYTHONPATH": root, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    started = time.monotonic()
    client = Client(stdio_client(params), raise_exceptions=True)
    async with asyncio.timeout(60):
        await client.__aenter__()
    print(f"enter_elapsed={time.monotonic()-started:.3f}")
    try:
        async with asyncio.timeout(10):
            tools = await client.list_tools()
        print(f"list_elapsed={time.monotonic()-started:.3f} names={[tool.name for tool in tools.tools]}")
        async with asyncio.timeout(10):
            result = await client.call_tool("ping", {})
        print(f"call_elapsed={time.monotonic()-started:.3f} is_error={result.is_error} structured={result.structured_content}")
    finally:
        async with asyncio.timeout(15):
            await client.__aexit__(None, None, None)
    print(f"exit_elapsed={time.monotonic()-started:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
