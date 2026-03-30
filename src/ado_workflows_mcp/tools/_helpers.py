"""
Shared helpers for MCP tool modules.

This is a package-internal module (note the ``_`` prefix on the file name).
Functions here are intentionally *not* ``_``-prefixed themselves so that
sibling tool modules can import them without triggering private-usage
diagnostics — the module name is the visibility boundary.
"""

from __future__ import annotations

from typing import Any

from ado_workflows.auth import ConnectionFactory
from ado_workflows.client import AdoClient
from ado_workflows.context import RepositoryContext


def get_context(working_directory: str | None = None) -> dict[str, Any]:
    """
    Return cached repository context, resolving if needed.

    Raises:
        ActionableError: When no context is set and *working_directory*
            is not provided or discovery fails.

    """
    return RepositoryContext.get(working_directory=working_directory)


def get_client(
    working_directory: str | None = None,
    *,
    org_url: str | None = None,
) -> AdoClient:
    """
    Build an authenticated AdoClient.

    When *org_url* is supplied (e.g. from a parsed PR context), it is used
    directly.  Otherwise the organisation URL is resolved from the cached
    repository context (or *working_directory*).
    """
    if not org_url:
        ctx = get_context(working_directory)
        org_url = ctx.get("org_url") or f"https://dev.azure.com/{ctx['organization']}"
    connection = ConnectionFactory().get_connection(str(org_url))
    return AdoClient(connection)
