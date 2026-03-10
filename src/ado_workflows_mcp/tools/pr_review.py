"""MCP tools for PR review status and pending review analysis."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.models import (  # noqa: TC002 — runtime for @mcp.tool() outputSchema
    PendingReviewResult,
    ReviewStatus,
)
from ado_workflows.review import (
    analyze_pending_reviews as _lib_analyze,
    get_review_status as _lib_review,
)

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import (
    _get_client,  # pyright: ignore[reportPrivateUsage]  # package-internal helpers
    _get_context,  # pyright: ignore[reportPrivateUsage]  # package-internal helpers
)


@mcp.tool()
def get_pr_review_status(
    pr_id: int,
    working_directory: str | None = None,
) -> ReviewStatus | ActionableError:
    """Get comprehensive review status with vote invalidation detection.

    Fetches PR details, reviewer votes, commit history, and detects
    stale approvals that the raw API buries.

    Args:
        pr_id: Pull request ID.
        working_directory: Optional path for context resolution.
    """
    try:
        ctx = _get_context(working_directory)
        client = _get_client(working_directory)
        return _lib_review(
            client,
            pr_id=pr_id,
            project=ctx["project"],
            repository=ctx["name"],
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=("Review status fetch failed. Verify the PR ID and credentials."),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_pr_review_status",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Review status fetch failed. Verify the PR ID"
                    " exists and credentials are valid."
                ),
                checks=[
                    "Confirm the PR ID is valid for this repository",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )


@mcp.tool()
def analyze_pending_reviews(
    max_days_old: int = 30,
    creator_filter: str | None = None,
    working_directory: str | None = None,
) -> PendingReviewResult | ActionableError:
    """Discover PRs needing review attention across a repository.

    Lists active PRs, filters by age and creator, and enriches each
    with staleness detection data.

    Args:
        max_days_old: Exclude PRs older than this many days. Default 30.
        creator_filter: Optional substring match on PR creator.
        working_directory: Optional path for context resolution.
    """
    try:
        ctx = _get_context(working_directory)
        client = _get_client(working_directory)
        return _lib_analyze(
            client,
            project=ctx["project"],
            repository=ctx["name"],
            max_days_old=max_days_old,
            creator_filter=creator_filter,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Pending review analysis encountered an error."
                    " Verify repository context and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="analyze_pending_reviews",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Pending review analysis failed. Verify repository context and credentials."
                ),
                steps=[
                    "Call set_repository_context to ensure context is set",
                    "Verify Azure DevOps authentication",
                    "Retry the operation",
                ],
            ),
        )
