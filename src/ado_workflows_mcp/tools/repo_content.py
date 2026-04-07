"""MCP tools for remote repository content inspection."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.content import (
    get_file_content as _lib_get_content,
    list_repo_items as _lib_list_items,
)

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import get_client, get_context


@mcp.tool()
def list_repo_items(
    *,
    path: str = "/",
    ref: str | None = None,
    recursion: str = "oneLevel",
    repository: str | None = None,
    project: str | None = None,
    working_directory: str | None = None,
) -> list[dict[str, Any]] | ActionableError:
    """
    List files and folders at a path on any branch, commit, or tag.

    Returns a list of dicts, each with keys: path, is_folder,
    git_object_type, object_id, commit_id, url.

    Context (repository, project, org) is resolved from the cached
    RepositoryContext unless explicit params are provided.

    Args:
        path: Directory path to list. Defaults to "/".
        ref: Branch name, commit SHA, or tag. None = default branch.
        recursion: "none", "oneLevel" (default), or "full".
        repository: Repository name (overrides context).
        project: Project name (overrides context).
        working_directory: Optional path for context resolution.

    """
    try:
        ctx = get_context(working_directory)
        repo = repository or ctx["repository"]
        proj = project or ctx["project"]
        client = get_client(working_directory)

        items = _lib_list_items(
            client,
            repo,
            proj,
            path=path,
            ref=ref,
            recursion=recursion,
        )

        return [asdict(item) for item in items]

    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Failed to list repository items. "
                    "Verify the path, branch reference, and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="list_repo_items",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Repository item listing failed unexpectedly. "
                    "Check the error details and retry."
                ),
                checks=[
                    "Confirm the repository and project names are correct",
                    "Verify Azure DevOps authentication",
                    "Check that the path and branch reference exist",
                ],
            ),
        )


@mcp.tool()
def get_repo_file_content(
    path: str,
    *,
    ref: str | None = None,
    repository: str | None = None,
    project: str | None = None,
    working_directory: str | None = None,
) -> dict[str, Any] | ActionableError:
    """
    Fetch a single file's content from any branch, commit, or tag.

    Returns a dict with keys: path, content, encoding, size_bytes.

    Context (repository, project, org) is resolved from the cached
    RepositoryContext unless explicit params are provided.

    Args:
        path: File path within the repository.
        ref: Branch name, commit SHA, or tag. None = default branch.
        repository: Repository name (overrides context).
        project: Project name (overrides context).
        working_directory: Optional path for context resolution.

    """
    try:
        ctx = get_context(working_directory)
        repo = repository or ctx["repository"]
        proj = project or ctx["project"]
        client = get_client(working_directory)

        fc = _lib_get_content(
            client,
            repo,
            path,
            proj,
            version=ref,
            version_type="branch",
        )

        return asdict(fc)

    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Failed to fetch file content. "
                    "Verify the file path, branch reference, and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_repo_file_content",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "File content fetch failed unexpectedly. Check the error details and retry."
                ),
                checks=[
                    "Confirm the file path exists in the repository",
                    "Verify the branch or commit reference is valid",
                    "Check Azure DevOps authentication",
                ],
            ),
        )
