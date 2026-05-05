"""MCP tools for Azure DevOps repository discovery."""

from __future__ import annotations

import os
from typing import Any

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.context import (
    discover_all_repositories as _lib_discover_all_repositories,
)
from ado_workflows.discovery import discover_repositories, infer_target_repository

from ado_workflows_mcp.mcp_instance import mcp


@mcp.tool()
def repository_discovery(
    working_directory: str | None = None,
) -> dict[str, Any] | ActionableError:
    """
    Discover Azure DevOps repositories from local git remotes.

    Scans the working directory (or cwd) for git repos, extracts ADO remote
    metadata, and selects the best match.

    Args:
        working_directory: Path to scan. Defaults to the current working
            directory when omitted.

    """
    try:
        search_root = working_directory or os.getcwd()
        repos = discover_repositories(search_root)
        if not repos:
            return ActionableError.not_found(
                service="ado-workflows-mcp",
                resource_type="Azure DevOps repository",
                resource_id=search_root,
                raw_error="No ADO remotes found",
                suggestion=(
                    "Ensure the directory contains a git repo with an "
                    "Azure DevOps remote (dev.azure.com or visualstudio.com)."
                ),
                ai_guidance=AIGuidance(
                    action_required=(
                        "Verify the working directory contains a git repo"
                        " with an Azure DevOps remote."
                    ),
                    checks=[
                        "Confirm the path exists and contains a .git directory",
                        "Run 'git remote -v' to verify an ADO remote is configured",
                    ],
                ),
            )
        target = infer_target_repository(repos)
        if target is None:
            return ActionableError.not_found(
                service="ado-workflows-mcp",
                resource_type="Azure DevOps repository",
                resource_id=search_root,
                raw_error="Multiple repos found but none matched working directory",
                suggestion=(
                    "Pass a working_directory that is inside one of the discovered repositories."
                ),
                ai_guidance=AIGuidance(
                    action_required=(
                        "Narrow the search by passing a working_directory inside the target repo."
                    ),
                    discovery_tool="repository_discovery",
                ),
            )
        return target
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="repository_discovery",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Unexpected error during repository discovery."
                    " Check the working directory and retry."
                ),
            ),
        )


@mcp.tool()
def discover_all_repositories(
    working_directory: str | None = None,
) -> list[dict[str, Any]] | ActionableError:
    """
    List every Azure DevOps repository discovered under the working directory.

    Walks the working directory (or cwd) for git repositories with
    Azure DevOps remotes. Use this tool when another tool surfaces a
    multi-repo ambiguity error to enumerate the candidate repos so an
    end user can disambiguate.

    Args:
        working_directory: Path to scan. Defaults to the current working
            directory when omitted.

    """
    try:
        return _lib_discover_all_repositories(working_directory=working_directory)
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="discover_all_repositories",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Unexpected error while discovering repositories."
                    " Check the working directory and retry."
                ),
            ),
        )
