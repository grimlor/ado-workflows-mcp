"""MCP tools for PR author and authenticated user identity."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.auth import get_current_user as _lib_current_user
from ado_workflows.models import UserIdentity  # runtime for @mcp.tool() outputSchema
from ado_workflows.pr import (
    establish_pr_context as _lib_establish_pr,
    get_pr_author as _lib_pr_author,
)

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import (
    _get_client,  # pyright: ignore[reportPrivateUsage]  # package-internal helper
)


@mcp.tool()
def get_pr_author(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> UserIdentity | ActionableError:
    """Get the identity of a PR's creator.

    Returns the display name, GUID, and email of the user who created
    the pull request.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        return _lib_pr_author(
            client,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="PR author lookup failed. Verify the PR URL/ID and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_pr_author",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="PR author lookup failed. Verify the PR URL/ID and credentials.",
                checks=[
                    "Confirm the PR URL or ID is valid",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )


@mcp.tool()
def get_current_user(
    working_directory: str | None = None,
) -> UserIdentity | ActionableError:
    """Get the identity of the authenticated user.

    Returns the display name and GUID of the user whose credentials
    are active for Azure DevOps operations. Useful for self-praise
    filtering, commit attribution, and permission checks.

    Args:
        working_directory: Optional path for context resolution.
    """
    try:
        client = _get_client(working_directory)
        return _lib_current_user(client)
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Current user lookup failed. Verify Azure DevOps authentication."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_current_user",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Current user lookup failed. Verify Azure DevOps authentication."
                ),
                checks=[
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm repository context is set",
                ],
                command="az login",
            ),
        )
