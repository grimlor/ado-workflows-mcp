"""BDD tests for server.py — MCP server entry point.

Covers:
- TestServerEntryPoint: importing server module registers tools, main() runs server

Public API surface (from src/ado_workflows_mcp/server.py):
    main() -> None  (runs the MCP server)

I/O boundary:
    mcp.run() — starts the MCP transport loop (blocked in tests)
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import ado_workflows_mcp.tools as _tools  # noqa: F401  # pyright: ignore[reportUnusedImport]  # side-effect: registers tools
from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.server import main


class TestServerEntryPoint:
    """
    REQUIREMENT: Server module boots the MCP server with all tools registered.

    WHO: MCP clients connecting to the server.
    WHAT: Importing server triggers tool registration; main() calls mcp.run().
    WHY: Entry point must work for the server to be usable.

    MOCK BOUNDARY:
        Mock:  mcp.run() (starts transport — I/O boundary)
        Real:  module import, tool registration side-effects
        Never: FastMCP internals
    """

    def test_import_registers_tools(self) -> None:
        """
        When the server module is imported
        Then tools are registered on the mcp instance
        """
        # When/Then: mcp has registered tools (import at module level triggers registration)
        tools = asyncio.run(mcp.list_tools())
        assert len(tools) == 12, (
            f"Expected 12 registered tools, got {len(tools)}: "
            f"{[t.name for t in tools]}"
        )

    def test_main_calls_mcp_run(self) -> None:
        """
        When main() is called
        Then it invokes mcp.run()
        """
        # Given: mcp.run is mocked so it doesn't start a real server
        with patch("ado_workflows_mcp.server.mcp") as mock_mcp:
            # When: main is called
            main()

        # Then: mcp.run() was called exactly once
        mock_mcp.run.assert_called_once_with()
