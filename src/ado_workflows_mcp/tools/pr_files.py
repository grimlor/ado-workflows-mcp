"""MCP tools for PR file changes and content fetching."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.content import get_changed_file_contents as _lib_contents
from ado_workflows.iterations import (
    get_latest_iteration_context as _lib_iteration_ctx,
)
from ado_workflows.models import ContentResult  # runtime for @mcp.tool() outputSchema
from ado_workflows.pr import establish_pr_context as _lib_establish_pr

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import (
    _get_client,  # pyright: ignore[reportPrivateUsage]  # package-internal helper
)


@mcp.tool()
def get_pr_file_changes(
    pr_url_or_id: str,
    *,
    working_directory: str | None = None,
) -> list[dict[str, Any]] | ActionableError:
    """List files changed in a PR with iteration metadata.

    Returns a list of dicts, each with keys: path, change_type,
    change_tracking_id, iteration_id.

    Uses the latest iteration.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        ctx = _lib_iteration_ctx(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
        )
        return [
            {
                "path": fc.path,
                "change_type": fc.change_type,
                "change_tracking_id": fc.change_tracking_id,
                "iteration_id": ctx.iteration_id,
            }
            for fc in ctx.file_changes.values()
        ]
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "File change listing failed. Verify the PR URL/ID and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_pr_file_changes",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "File change listing failed. Verify the PR URL/ID and credentials."
                ),
                checks=[
                    "Confirm the PR URL or ID is valid",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )


@mcp.tool()
def get_pr_file_contents(
    pr_url_or_id: str,
    *,
    file_paths: list[str] | None = None,
    working_directory: str | None = None,
) -> list[dict[str, Any]] | ActionableError:
    """Fetch file contents for files changed in a PR.

    Returns a list of dicts, each with keys: path, content, encoding,
    size_bytes. Files that fail to fetch are omitted from successes and
    included as error entries with ai_guidance.

    If file_paths is None, fetches all changed files.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        file_paths: Optional list of specific file paths to fetch.
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        result: ContentResult = _lib_contents(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            file_paths=file_paths,
        )

        # Serialize successes
        entries: list[dict[str, Any]] = [asdict(fc) for fc in result.files]

        # Serialize failures with ai_guidance
        for failure in result.failures:
            entry: dict[str, Any] = {
                "error": failure.error,
                "path": failure.context.get("path", "") if failure.context else "",
            }
            entry["ai_guidance"] = (
                failure.ai_guidance.action_required
                if failure.ai_guidance
                else "File content fetch failed. Verify the file path exists."
            )
            entries.append(entry)

        return entries

    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "File content fetch failed. Verify the PR URL/ID and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_pr_file_contents",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "File content fetch failed. Verify the PR URL/ID and credentials."
                ),
                checks=[
                    "Confirm the PR URL or ID is valid",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )
