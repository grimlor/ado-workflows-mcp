"""ADO Workflows MCP server entry point."""

from __future__ import annotations

# Importing the tools package triggers @mcp.tool() registration for every
# tool function re-exported via tools/__init__.py.
import ado_workflows_mcp.tools as _tools  # noqa: F401
from ado_workflows_mcp.mcp_instance import mcp


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
