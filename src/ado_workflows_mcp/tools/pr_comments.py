"""MCP tools for PR comment analysis and management."""

from __future__ import annotations

from typing import cast

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.comments import (
    analyze_pr_comments as _lib_analyze,
    post_comment as _lib_post,
    post_comments as _lib_post_batch,
    post_rich_comments as _lib_post_rich,
    reply_to_comment as _lib_reply,
    resolve_comments as _lib_resolve,
)
from ado_workflows.models import (  # runtime for @mcp.tool() outputSchema
    CommentAnalysis,
    CommentPayload,
    CommentSeverity,
    CommentType,
    PostingResult,
    ResolveResult,
    RichComment,
    RichPostingResult,
)
from ado_workflows.pr import establish_pr_context as _lib_establish_pr

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import (
    get_client,
)

# Lookup tables for string → enum coercion at the MCP boundary.
_SEVERITY_LOOKUP: dict[str, CommentSeverity] = {m.value: m for m in CommentSeverity}
_COMMENT_TYPE_LOOKUP: dict[str, CommentType] = {m.value: m for m in CommentType}


@mcp.tool()
def analyze_pr_comments(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> CommentAnalysis | ActionableError:
    """
    Analyze all comment threads on a PR.

    Fetches threads, categorizes by status, and extracts author
    statistics for a structured overview.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
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
    """
    Post a new comment thread to a PR.

    Creates a new comment thread with the specified content and status.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        comment_text: Comment body text.
        status: Thread status (default "active").
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
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
    """
    Reply to an existing comment thread.

    Adds a reply to a specific thread on a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        thread_id: Existing thread ID to reply to.
        comment_text: Reply body text.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
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
    """
    Batch-resolve PR comment threads.

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
        client = get_client(working_directory, org_url=pr_ctx.org_url)
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


@mcp.tool()
def post_pr_comments(
    pr_url_or_id: str,
    comments: list[dict[str, object]],
    *,
    dry_run: bool = False,
    working_directory: str | None = None,
) -> PostingResult | ActionableError:
    """
    Batch-post comments to a PR with optional file/line positioning.

    Each comment dict has keys:
        content: str           (required)
        file_path: str | None  (optional — anchors to file)
        line_number: int | None (optional — anchors to line, requires file_path)
        status: str            (optional — default "active")

    Iteration context is auto-resolved. Comments are positioned on the
    latest iteration.

    dry_run=True validates and returns what would be posted.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        comments: List of comment dicts to post.
        dry_run: If True, validate without posting.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)

        # Convert dicts to CommentPayload, collecting validation failures
        payloads: list[CommentPayload] = []
        validation_failures: list[ActionableError] = []
        for comment in comments:
            content = str(comment.get("content", ""))
            file_path = comment.get("file_path")
            line_number = comment.get("line_number")
            status = str(comment.get("status", "active"))

            if line_number is not None and file_path is None:
                validation_failures.append(
                    ActionableError.validation(
                        service="ado-workflows-mcp",
                        field_name="file_path",
                        reason=(
                            "line_number requires file_path. "
                            f"Got line_number={line_number} with no file_path."
                        ),
                        ai_guidance=AIGuidance(
                            action_required=(
                                "Provide file_path when specifying line_number, "
                                "or remove line_number for a general comment."
                            ),
                        ),
                    )
                )
                continue

            payloads.append(
                CommentPayload(
                    content=content,
                    file_path=str(file_path) if file_path is not None else None,
                    line_number=int(str(line_number)) if line_number is not None else None,
                    status=status,
                )
            )

        # Delegate to library batch post (iteration context resolved internally)
        result = _lib_post_batch(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            comments=payloads,
            project=pr_ctx.project,
            dry_run=dry_run,
        )

        # Merge validation failures into the result
        if validation_failures:
            result = PostingResult(
                posted=result.posted,
                failures=[*result.failures, *validation_failures],
                skipped=result.skipped,
                dry_run=result.dry_run,
            )

        return result

    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Batch comment posting failed. Verify the PR URL/ID and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="post_pr_comments",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Batch comment posting failed. Verify credentials and PR write access."
                ),
                checks=[
                    "Confirm the PR URL or ID is valid",
                    "Verify Azure DevOps authentication",
                    "Confirm you have Contribute to pull requests permission",
                ],
            ),
        )


@mcp.tool()
def post_rich_comments(
    pr_url_or_id: str,
    comments: list[dict[str, object]],
    *,
    dry_run: bool = False,
    batch_size: int = 5,
    filter_self_praise: bool = True,
    working_directory: str | None = None,
) -> RichPostingResult | ActionableError:
    """
    Batch-post structured review comments with severity, type, and formatting.

    Each comment dict has keys:
        comment_id: str        (required — unique identifier)
        title: str             (required — short heading)
        content: str           (required — comment body)
        severity: str          (optional — "info","suggestion","warning","error","critical")
        comment_type: str      (optional — "general","line","file","suggestion","security","performance")
        file_path: str | None  (optional — anchors to file)
        line_number: int | None (optional — anchors to line, requires file_path)
        suggested_code: str | None (optional)
        reasoning: str | None  (optional)
        business_impact: str | None (optional)
        tags: list[str]        (optional)
        status: str            (optional — default "active")
        parent_thread_id: int | None (optional — reply to existing thread)

    String severity/comment_type values are coerced to enums at this layer.
    Invalid values return an ActionableError listing valid options.

    dry_run=True validates and shows what would be posted without calling the API.
    filter_self_praise=True (default) removes praise comments authored by the caller.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        comments: List of comment dicts to post.
        dry_run: If True, validate without posting.
        batch_size: Number of comments per API batch (default 5).
        filter_self_praise: If True, filter out self-praise comments.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)

        # Coerce dicts to RichComment with string→enum conversion
        rich_comments: list[RichComment] = []
        for comment in comments:
            # --- severity ---
            raw_severity = str(comment.get("severity", "info"))
            severity = _SEVERITY_LOOKUP.get(raw_severity)
            if severity is None:
                return ActionableError.validation(
                    service="ado-workflows-mcp",
                    field_name="severity",
                    reason=(
                        f"Invalid severity {raw_severity!r}. "
                        f"Valid values: {', '.join(sorted(_SEVERITY_LOOKUP))}."
                    ),
                    ai_guidance=AIGuidance(
                        action_required=(
                            f"Use one of the valid severity values: "
                            f"{', '.join(sorted(_SEVERITY_LOOKUP))}."
                        ),
                    ),
                )

            # --- comment_type ---
            raw_type = str(comment.get("comment_type", "general"))
            comment_type = _COMMENT_TYPE_LOOKUP.get(raw_type)
            if comment_type is None:
                return ActionableError.validation(
                    service="ado-workflows-mcp",
                    field_name="comment_type",
                    reason=(
                        f"Invalid comment_type {raw_type!r}. "
                        f"Valid values: {', '.join(sorted(_COMMENT_TYPE_LOOKUP))}."
                    ),
                    ai_guidance=AIGuidance(
                        action_required=(
                            f"Use one of the valid comment_type values: "
                            f"{', '.join(sorted(_COMMENT_TYPE_LOOKUP))}."
                        ),
                    ),
                )

            file_path = comment.get("file_path")
            line_number = comment.get("line_number")
            tags_raw = comment.get("tags")
            tags: list[str] = (
                [str(t) for t in cast("list[object]", tags_raw)]
                if isinstance(tags_raw, list)
                else []
            )

            rich_comments.append(
                RichComment(
                    comment_id=str(comment.get("comment_id", "")),
                    title=str(comment.get("title", "")),
                    content=str(comment.get("content", "")),
                    severity=severity,
                    comment_type=comment_type,
                    file_path=str(file_path) if file_path is not None else None,
                    line_number=int(str(line_number)) if line_number is not None else None,
                    suggested_code=(
                        str(comment["suggested_code"])
                        if comment.get("suggested_code") is not None
                        else None
                    ),
                    reasoning=(
                        str(comment["reasoning"]) if comment.get("reasoning") is not None else None
                    ),
                    business_impact=(
                        str(comment["business_impact"])
                        if comment.get("business_impact") is not None
                        else None
                    ),
                    tags=tags,
                    status=str(comment.get("status", "active")),
                    parent_thread_id=(
                        int(str(comment["parent_thread_id"]))
                        if comment.get("parent_thread_id") is not None
                        else None
                    ),
                )
            )

        return _lib_post_rich(
            client,
            repository=pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            comments=rich_comments,
            project=pr_ctx.project,
            dry_run=dry_run,
            batch_size=batch_size,
            filter_self_praise=filter_self_praise,
        )

    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Rich comment posting failed. Verify the PR URL/ID and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="post_rich_comments",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Rich comment posting failed. Verify credentials and PR write access."
                ),
                checks=[
                    "Confirm the PR URL or ID is valid",
                    "Verify Azure DevOps authentication",
                    "Confirm you have Contribute to pull requests permission",
                ],
            ),
        )
