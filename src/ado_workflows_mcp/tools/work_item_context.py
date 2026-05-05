"""MCP tools for work-item context resolution."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.work_items import (
    AzureDevOpsWorkItemContext,  # runtime for @mcp.tool() outputSchema
    establish_work_item_context as _lib_establish_work_item,
)

from ado_workflows_mcp.mcp_instance import mcp


@mcp.tool()
def establish_work_item_context(
    work_item_url_or_id: str,
    working_directory: str | None = None,
) -> AzureDevOpsWorkItemContext | ActionableError:
    """
    Resolve a work-item URL or numeric ID into a structured context.

    Parses a full Azure DevOps work-item URL or resolves a bare numeric
    work-item ID using the cached repository context. The returned
    ``AzureDevOpsWorkItemContext`` carries the organisation, project,
    work-item ID, and computed ``org_url`` for downstream tools.

    Caveat — work board ≠ code repo: when resolving a bare numeric ID
    against a workspace whose work board lives in a different
    organisation than any of the discovered code repos, the resolved
    ``org_url`` will land on the code-repo organisation, not the work
    board's. Prefer passing a full work-item URL whenever one is
    available.

    Args:
        work_item_url_or_id: A full Azure DevOps work-item URL or a
            numeric work-item ID.
        working_directory: Optional path for repository-context
            resolution when using a numeric ID.

    """
    try:
        return _lib_establish_work_item(work_item_url_or_id, working_directory=working_directory)
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Work-item context resolution failed. Provide a full"
                    " work-item URL or set repository context first."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="establish_work_item_context",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Work-item context resolution failed. Provide a full"
                    " work-item URL or set repository context first."
                ),
                steps=[
                    "Use a full Azure DevOps work-item URL instead of a numeric ID",
                    "Or call set_repository_context before using a numeric ID",
                ],
            ),
        )
