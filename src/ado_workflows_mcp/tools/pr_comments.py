"""MCP tools for PR comment analysis and management."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.comments import (
    analyze_pr_comments as _lib_analyze,
    post_comment as _lib_post,
    reply_to_comment as _lib_reply,
    resolve_comments as _lib_resolve,
)
from ado_workflows.models import (  # runtime for @mcp.tool() outputSchema
    CommentAnalysis,
    ResolveResult,
)
from ado_workflows.pr import establish_pr_context as _lib_establish_pr

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import (
    _get_client,  # pyright: ignore[reportPrivateUsage]  # package-internal helper
)


@mcp.tool()
def analyze_pr_comments(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> CommentAnalysis | ActionableError:
    """Analyze all comment threads on a PR.

    Fetches threads, categorizes by status, and extracts author
    statistics for a structured overview.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        return _lib_analyze(
            client,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            repository=pr_ctx.repository,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=("Comment analysis failed. Verify the PR URL/ID and credentials."),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="analyze_pr_comments",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=("Comment analysis failed. Verify the PR URL/ID and credentials."),
                checks=[
                    "Confirm the PR URL or ID is valid",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )


@mcp.tool()
def post_pr_comment(
    pr_url_or_id: str,
    comment_text: str,
    status: str = "active",
    working_directory: str | None = None,
) -> int | ActionableError:
    """Post a new comment thread to a PR.

    Creates a new comment thread with the specified content and status.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        comment_text: Comment body text.
        status: Thread status (default "active").
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        return _lib_post(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            content=comment_text,
            project=pr_ctx.project,
            status=status,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Comment posting failed. Verify credentials and PR write access."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="post_pr_comment",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Comment posting failed. Verify credentials and PR write access."
                ),
                checks=[
                    "Verify Azure DevOps authentication",
                    "Confirm you have Contribute to pull requests permission",
                ],
            ),
        )


@mcp.tool()
def reply_to_pr_comment(
    pr_url_or_id: str,
    thread_id: int,
    comment_text: str,
    working_directory: str | None = None,
) -> int | ActionableError:
    """Reply to an existing comment thread.

    Adds a reply to a specific thread on a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        thread_id: Existing thread ID to reply to.
        comment_text: Reply body text.
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        return _lib_reply(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            thread_id=thread_id,
            content=comment_text,
            project=pr_ctx.project,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=("Reply failed. Verify the thread ID and credentials."),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="reply_to_pr_comment",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Reply failed. Verify the thread ID exists and credentials are valid."
                ),
                checks=[
                    "Confirm the thread_id exists on this PR"
                    " (use analyze_pr_comments to list threads)",
                    "Verify Azure DevOps authentication",
                ],
                discovery_tool="analyze_pr_comments",
            ),
        )


@mcp.tool()
def resolve_pr_comments(
    pr_url_or_id: str,
    thread_ids: list[int],
    status: str = "fixed",
    working_directory: str | None = None,
) -> ResolveResult | ActionableError:
    """Batch-resolve PR comment threads.

    Sets thread status to the target status for a list of thread IDs.
    Uses partial-success semantics — individual thread errors don't
    fail the entire batch.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        thread_ids: Thread IDs to resolve.
        status: Target thread status (default "fixed").
        working_directory: Optional path for context resolution.
    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = _get_client(working_directory)
        return _lib_resolve(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            thread_ids=thread_ids,
            project=pr_ctx.project,
            status=status,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=("Comment resolution failed. Verify thread IDs and credentials."),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="resolve_pr_comments",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=("Comment resolution failed. Verify thread IDs and credentials."),
                checks=[
                    "Confirm thread_ids exist on this PR"
                    " (use analyze_pr_comments to list threads)",
                    "Verify Azure DevOps authentication and write permissions",
                ],
                discovery_tool="analyze_pr_comments",
            ),
        )
