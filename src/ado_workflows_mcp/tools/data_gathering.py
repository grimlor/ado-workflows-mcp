"""MCP tools for data gathering — PRs, work items, and commit history."""

from __future__ import annotations

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.listing import (
    list_commits as _lib_list_commits,
    list_pull_requests as _lib_list_pull_requests,
    query_work_items as _lib_query_work_items,
)
from ado_workflows.models import (
    CommitSummary,
    PullRequestSummary,
    WorkItemSummary,
)

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import get_client


@mcp.tool()
def list_pull_requests(
    project: str,
    *,
    creator_id: str | None = None,
    reviewer_id: str | None = None,
    status: str = "all",
    repository_id: str | None = None,
    top: int = 50,
    working_directory: str | None = None,
) -> list[PullRequestSummary] | ActionableError:
    """
    List pull requests matching search criteria.

    Returns PR summaries with id, title, status, web_url, and more.

    Args:
        project: Azure DevOps project name.
        creator_id: Optional GUID to filter by PR creator.
        reviewer_id: Optional GUID to filter by reviewer.
        status: PR status filter (default "all").
        repository_id: Optional repository ID for repo-scoped queries.
        top: Maximum number of results (default 50).
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_list_pull_requests(
            client,
            project,
            creator_id=creator_id,
            reviewer_id=reviewer_id,
            status=status,
            repository_id=repository_id,
            top=top,
        )
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="list_pull_requests",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="PR listing failed. Verify project name and credentials.",
                checks=[
                    "Confirm the project name is correct",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm repository context is set or working_directory is valid",
                ],
            ),
        )


@mcp.tool()
def query_work_items(
    project: str,
    wiql: str,
    *,
    top: int | None = None,
    working_directory: str | None = None,
) -> list[WorkItemSummary] | ActionableError:
    """
    Query work items via WIQL and return enriched data.

    Executes a WIQL query and returns work item summaries with id,
    title, state, type, and effort tracking fields.

    Args:
        project: Azure DevOps project name.
        wiql: WIQL query string.
        top: Optional maximum number of results.
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_query_work_items(
            client,
            project,
            wiql,
            top=top,
        )
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="query_work_items",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Work item query failed. Verify WIQL syntax and credentials.",
                checks=[
                    "Confirm the WIQL query syntax is valid",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )


@mcp.tool()
def list_commits(
    repo_path: str,
    *,
    authors: list[str] | None = None,
    since: str | None = None,
    max_count: int = 100,
) -> list[CommitSummary] | ActionableError:
    """
    List git commits from a local repository.

    Returns commit summaries with sha, message, author, date, and
    repo name. No ADO connection is needed.

    Args:
        repo_path: Absolute path to the local git repository.
        authors: Optional list of author names/emails to filter by.
        since: Optional date string to filter commits after (e.g. "2026-01-01").
        max_count: Maximum number of commits to return (default 100).

    """
    try:
        return _lib_list_commits(
            repo_path,
            authors=authors,
            since=since,
            max_count=max_count,
        )
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="list_commits",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Commit listing failed. Verify the repository path.",
                checks=[
                    "Confirm the repo_path points to a valid git repository",
                    "Verify the path exists and is accessible",
                ],
            ),
        )
