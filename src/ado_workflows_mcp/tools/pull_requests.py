"""MCP tools for PR context resolution and creation."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.lifecycle import create_pull_request as _lib_create_pr
from ado_workflows.models import CreatedPR  # runtime for @mcp.tool() outputSchema
from ado_workflows.pr import AzureDevOpsPRContext, establish_pr_context as _lib_establish

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import (
    _get_client,  # pyright: ignore[reportPrivateUsage]  # package-internal helpers
    _get_context,  # pyright: ignore[reportPrivateUsage]  # package-internal helpers
)


@mcp.tool()
def establish_pr_context(
    pr_url_or_id: str,
    working_directory: str | None = None,
) -> AzureDevOpsPRContext | ActionableError:
    """Create reusable PR context from a URL or numeric ID.

    Parses a full PR URL or resolves a numeric PR ID using
    cached repository context.

    Args:
        pr_url_or_id: A full Azure DevOps PR URL or a numeric PR ID.
        working_directory: Optional path for context resolution when
            using a numeric ID.
    """
    try:
        return _lib_establish(pr_url_or_id, working_directory=working_directory)
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "PR context resolution failed. Provide"
                    " a full PR URL or set repository context."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="establish_pr_context",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "PR context resolution failed. Provide a full"
                    " PR URL or set repository context first."
                ),
                steps=[
                    "Use a full Azure DevOps PR URL instead of a numeric ID",
                    "Or call set_repository_context before using a numeric ID",
                ],
            ),
        )


@mcp.tool()
def create_pull_request(
    source_branch: str,
    target_branch: str = "main",
    title: str | None = None,
    description: str | None = None,
    is_draft: bool = False,
    working_directory: str | None = None,
) -> CreatedPR | ActionableError:
    """Create a new pull request via the Azure DevOps SDK.

    Constructs a PR from branch names with optional title, description,
    and draft mode.

    Args:
        source_branch: Source branch name (with or without refs/heads/).
        target_branch: Target branch name. Defaults to "main".
        title: Optional PR title.
        description: Optional PR description.
        is_draft: Whether to create as a draft PR.
        working_directory: Optional path for context resolution.
    """
    try:
        ctx = _get_context(working_directory)
        client = _get_client(working_directory)
        return _lib_create_pr(
            client,
            repository=ctx["name"],
            source_branch=source_branch,
            target_branch=target_branch,
            project=ctx["project"],
            title=title,
            description=description,
            is_draft=is_draft,
        )
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "PR creation encountered an error. Check branches and credentials."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="create_pull_request",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "PR creation failed. Verify branches exist and Azure credentials are valid."
                ),
                checks=[
                    "Confirm source and target branches exist in the remote",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                ],
                command="az login",
            ),
        )
