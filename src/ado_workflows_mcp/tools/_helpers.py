"""Shared helpers for MCP tool modules."""

from __future__ import annotations

from typing import Any

from ado_workflows.auth import ConnectionFactory
from ado_workflows.client import AdoClient
from ado_workflows.context import RepositoryContext


def _get_context(working_directory: str | None = None) -> dict[str, Any]:
    """
    Return cached repository context, resolving if needed.

    Raises:
        ActionableError: When no context is set and *working_directory*
            is not provided or discovery fails.

    """
    return RepositoryContext.get(working_directory=working_directory)


def _get_client(working_directory: str | None = None) -> AdoClient:  # pyright: ignore[reportUnusedFunction]  # called by sibling tool modules
    """
    Build an authenticated AdoClient from repository context.

    Resolves the organisation URL from cache (or *working_directory*),
    then constructs a :class:`~ado_workflows.client.AdoClient` using
    :class:`~ado_workflows.auth.ConnectionFactory`.
    """
    ctx = _get_context(working_directory)
    org_url = ctx.get("org_url") or f"https://dev.azure.com/{ctx['organization']}"
    connection = ConnectionFactory().get_connection(org_url)
    return AdoClient(connection)
