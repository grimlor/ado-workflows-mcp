"""ADO Workflows MCP server entry point."""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "ado-workflows-mcp",
    description="Azure DevOps workflow automation tools",
)


def main() -> None:
    """Run the MCP server."""
    asyncio.run(mcp.run_async())


if __name__ == "__main__":
    main()
