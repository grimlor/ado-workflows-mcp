"""ADO Workflows MCP server entry point."""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP(
    "ado-workflows-mcp",
    instructions="Azure DevOps workflow automation tools",
)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
