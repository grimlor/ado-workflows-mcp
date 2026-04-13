"""MCP tools for PR lifecycle operations — get, update, complete, reviewers, labels."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.lifecycle import (
    abandon_pull_request as _lib_abandon,
    add_label as _lib_add_label,
    add_reviewer as _lib_add_reviewer,
    complete_pull_request as _lib_complete,
    get_pr_work_item_refs as _lib_work_items,
    get_pull_request as _lib_get_pr,
    list_labels as _lib_list_labels,
    list_reviewers as _lib_list_reviewers,
    remove_label as _lib_remove_label,
    remove_reviewer as _lib_remove_reviewer,
    retarget_pull_request as _lib_retarget,
    set_draft_status as _lib_set_draft,
    update_pull_request as _lib_update,
)
from ado_workflows.models import (
    LabelDetail,
    MergeStrategy,
    PullRequestDetail,
    ReviewerDetail,
    WorkItemRef,
)
from ado_workflows.pr import establish_pr_context as _lib_establish_pr

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import get_client

# Lookup table for string → enum coercion at the MCP boundary.
_MERGE_STRATEGY_LOOKUP: dict[str, MergeStrategy] = {m.value: m for m in MergeStrategy}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@mcp.tool()
def get_pull_request(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> PullRequestDetail | ActionableError:
    """
    Retrieve full PR metadata including reviewers, labels, and work items.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_get_pr(client, pr_id=pr_ctx.pr_id, project=pr_ctx.project)
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to retrieve PR. Verify the PR URL/ID and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_pull_request",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to retrieve PR details.",
                checks=["Confirm the PR URL or ID is valid", "Verify Azure DevOps authentication"],
            ),
        )


# ---------------------------------------------------------------------------
# Update metadata
# ---------------------------------------------------------------------------


@mcp.tool()
def update_pull_request(
    pr_url_or_id: str,
    title: str | None = None,
    description: str | None = None,
    working_directory: str | None = None,
    work_item_ids: list[int] | None = None,
) -> PullRequestDetail | ActionableError:
    """
    Update title and/or description of an existing PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        title: New title (optional).
        description: New description (optional).
        working_directory: Optional path for context resolution.
        work_item_ids: Optional list of work item IDs to link to the PR.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_update(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            title=title,
            description=description,
            work_item_ids=work_item_ids,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="PR update failed. Verify the PR URL/ID and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="update_pull_request",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="PR update failed.",
                checks=["Confirm the PR URL or ID is valid", "Verify Azure DevOps authentication"],
            ),
        )


@mcp.tool()
def retarget_pull_request(
    pr_url_or_id: str,
    target_branch: str,
    working_directory: str | None = None,
) -> PullRequestDetail | ActionableError:
    """
    Change the target branch of an existing PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        target_branch: New target branch name.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_retarget(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            target_branch=target_branch,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="PR retarget failed. Verify the branch name and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="retarget_pull_request",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="PR retarget failed.",
                checks=["Confirm the target branch exists", "Verify Azure DevOps authentication"],
            ),
        )


@mcp.tool()
def set_pr_draft_status(
    pr_url_or_id: str,
    is_draft: bool,
    working_directory: str | None = None,
) -> PullRequestDetail | ActionableError:
    """
    Toggle a PR between draft and published state.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        is_draft: True to mark as draft, False to publish.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_set_draft(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            is_draft=is_draft,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Draft status change failed. Verify the PR URL/ID and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="set_pr_draft_status",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Draft status change failed.",
                checks=["Confirm the PR URL or ID is valid", "Verify Azure DevOps authentication"],
            ),
        )


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


@mcp.tool()
def abandon_pull_request(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> PullRequestDetail | ActionableError:
    """
    Abandon (close without merging) an existing PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_abandon(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="PR abandon failed. Verify the PR URL/ID and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="abandon_pull_request",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="PR abandon failed.",
                checks=["Confirm the PR URL or ID is valid", "Verify Azure DevOps authentication"],
            ),
        )


@mcp.tool()
def complete_pull_request(
    pr_url_or_id: str,
    merge_strategy: str = "squash",
    delete_source_branch: bool = True,
    transition_work_items: bool = True,
    merge_commit_message: str | None = None,
    bypass_policy: bool = False,
    bypass_reason: str | None = None,
    working_directory: str | None = None,
) -> PullRequestDetail | ActionableError:
    """
    Complete (merge) a PR with configurable merge strategy.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        merge_strategy: One of: squash, noFastForward, rebase, rebaseMerge.
        delete_source_branch: Whether to delete the source branch after merge.
        transition_work_items: Whether to transition linked work items.
        merge_commit_message: Optional merge commit message.
        bypass_policy: Whether to bypass branch policies.
        bypass_reason: Required when bypass_policy is True.
        working_directory: Optional path for context resolution.

    """
    try:
        strategy = _MERGE_STRATEGY_LOOKUP.get(merge_strategy)
        if strategy is None:
            valid = ", ".join(_MERGE_STRATEGY_LOOKUP)
            return ActionableError.validation(
                service="ado-workflows-mcp",
                field_name="merge_strategy",
                reason=f"Invalid merge_strategy '{merge_strategy}'. Valid: {valid}",
                suggestion=f"Use one of: {valid}",
            )

        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_complete(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            merge_strategy=strategy,
            delete_source_branch=delete_source_branch,
            transition_work_items=transition_work_items,
            merge_commit_message=merge_commit_message,
            bypass_policy=bypass_policy,
            bypass_reason=bypass_reason,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="PR completion failed. Check merge conflicts and credentials.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="complete_pull_request",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="PR completion failed.",
                checks=[
                    "Confirm the PR is approved and has no merge conflicts",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )


# ---------------------------------------------------------------------------
# Reviewers
# ---------------------------------------------------------------------------


@mcp.tool()
def add_pr_reviewer(
    pr_url_or_id: str,
    reviewer_id: str,
    is_required: bool = False,
    working_directory: str | None = None,
) -> ReviewerDetail | ActionableError:
    """
    Add a reviewer to a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        reviewer_id: Azure DevOps identity GUID of the reviewer.
        is_required: Whether the reviewer is required.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_add_reviewer(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            reviewer_id=reviewer_id,
            is_required=is_required,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to add reviewer. Verify the identity GUID.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="add_pr_reviewer",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to add reviewer.",
                checks=[
                    "Confirm the reviewer GUID is valid",
                    "Verify Azure DevOps authentication",
                ],
            ),
        )


@mcp.tool()
def remove_pr_reviewer(
    pr_url_or_id: str,
    reviewer_id: str,
    working_directory: str | None = None,
) -> str | ActionableError:
    """
    Remove a reviewer from a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        reviewer_id: Azure DevOps identity GUID of the reviewer.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        _lib_remove_reviewer(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            reviewer_id=reviewer_id,
        )
        return f"Reviewer {reviewer_id} removed from PR {pr_ctx.pr_id}."
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to remove reviewer.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="remove_pr_reviewer",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to remove reviewer.",
                checks=["Confirm the reviewer exists on the PR"],
            ),
        )


@mcp.tool()
def list_pr_reviewers(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> list[ReviewerDetail] | ActionableError:
    """
    List all reviewers on a PR with vote details.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_list_reviewers(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to list reviewers.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="list_pr_reviewers",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to list reviewers.",
                checks=["Confirm the PR URL or ID is valid"],
            ),
        )


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@mcp.tool()
def add_pr_label(
    pr_url_or_id: str,
    name: str,
    working_directory: str | None = None,
) -> LabelDetail | ActionableError:
    """
    Add a label/tag to a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        name: Label name.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_add_label(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            name=name,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to add label.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="add_pr_label",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to add label.",
                checks=["Confirm the PR URL or ID is valid"],
            ),
        )


@mcp.tool()
def remove_pr_label(
    pr_url_or_id: str,
    label_name: str,
    working_directory: str | None = None,
) -> str | ActionableError:
    """
    Remove a label from a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        label_name: Label name to remove.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        _lib_remove_label(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
            label_name=label_name,
        )
        return f"Label '{label_name}' removed from PR {pr_ctx.pr_id}."
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to remove label.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="remove_pr_label",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to remove label.",
                checks=["Confirm the label exists on the PR"],
            ),
        )


@mcp.tool()
def list_pr_labels(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> list[LabelDetail] | ActionableError:
    """
    List all labels on a PR.

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_list_labels(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to list labels.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="list_pr_labels",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to list labels.",
                checks=["Confirm the PR URL or ID is valid"],
            ),
        )


# ---------------------------------------------------------------------------
# Work items
# ---------------------------------------------------------------------------


@mcp.tool()
def get_pr_work_items(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> list[WorkItemRef] | ActionableError:
    """
    List work items linked to a PR (read-only).

    Args:
        pr_url_or_id: A full PR URL or numeric PR ID.
        working_directory: Optional path for context resolution.

    """
    try:
        pr_ctx = _lib_establish_pr(pr_url_or_id, working_directory=working_directory)
        client = get_client(working_directory, org_url=pr_ctx.org_url)
        return _lib_work_items(
            client,
            pr_ctx.repository,
            pr_id=pr_ctx.pr_id,
            project=pr_ctx.project,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required="Failed to list work items.",
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_pr_work_items",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Failed to list work items.",
                checks=["Confirm the PR URL or ID is valid"],
            ),
        )
