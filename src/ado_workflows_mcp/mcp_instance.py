"""
Singleton FastMCP server instance.

All tool modules import ``mcp`` from here to register via ``@mcp.tool()``.
Keeping the instance in its own module avoids circular imports between
``server.py`` and the tool modules.
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP(
    "ado-workflows-mcp",
    instructions="Azure DevOps workflow automation tools",
)
