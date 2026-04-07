"""
MCP tool modules — explicit re-exports.

Importing this package triggers ``@mcp.tool()`` registration for every
tool function listed below.  Each sub-module decorates its functions
with ``@mcp.tool()`` at import time.
"""

from __future__ import annotations

import ado_workflows_mcp.tools._fixup_forward_refs as _fixup_forward_refs  # noqa: F401  # pyright: ignore[reportUnusedImport]  # side-effect: patches forward refs
from ado_workflows_mcp.tools.data_gathering import (
    list_commits as list_commits,
    list_pull_requests as list_pull_requests,
    query_work_items as query_work_items,
)
from ado_workflows_mcp.tools.pr_comments import (
    analyze_pr_comments as analyze_pr_comments,
    post_pr_comment as post_pr_comment,
    post_pr_comments as post_pr_comments,
    post_rich_comments as post_rich_comments,
    reply_to_pr_comment as reply_to_pr_comment,
    resolve_pr_comments as resolve_pr_comments,
)
from ado_workflows_mcp.tools.pr_context import (
    create_pull_request as create_pull_request,
    establish_pr_context as establish_pr_context,
)
from ado_workflows_mcp.tools.pr_files import (
    get_pr_file_changes as get_pr_file_changes,
    get_pr_file_contents as get_pr_file_contents,
)
from ado_workflows_mcp.tools.pr_identity import (
    get_current_user as get_current_user,
    get_pr_author as get_pr_author,
)
from ado_workflows_mcp.tools.pr_lifecycle import (
    abandon_pull_request as abandon_pull_request,
    add_pr_label as add_pr_label,
    add_pr_reviewer as add_pr_reviewer,
    complete_pull_request as complete_pull_request,
    get_pr_work_items as get_pr_work_items,
    get_pull_request as get_pull_request,
    list_pr_labels as list_pr_labels,
    list_pr_reviewers as list_pr_reviewers,
    remove_pr_label as remove_pr_label,
    remove_pr_reviewer as remove_pr_reviewer,
    retarget_pull_request as retarget_pull_request,
    set_pr_draft_status as set_pr_draft_status,
    update_pull_request as update_pull_request,
)
from ado_workflows_mcp.tools.pr_review import (
    analyze_pending_reviews as analyze_pending_reviews,
    get_pr_review_status as get_pr_review_status,
)
from ado_workflows_mcp.tools.repo_content import (
    get_repo_file_content as get_repo_file_content,
    list_repo_items as list_repo_items,
)
from ado_workflows_mcp.tools.repositories import repository_discovery as repository_discovery
from ado_workflows_mcp.tools.repository_context import (
    clear_repository_context as clear_repository_context,
    get_repository_context_status as get_repository_context_status,
    set_repository_context as set_repository_context,
)

__all__ = [
    "abandon_pull_request",
    "add_pr_label",
    "add_pr_reviewer",
    "analyze_pending_reviews",
    "analyze_pr_comments",
    "clear_repository_context",
    "complete_pull_request",
    "create_pull_request",
    "establish_pr_context",
    "get_current_user",
    "get_pr_author",
    "get_pr_file_changes",
    "get_pr_file_contents",
    "get_pr_review_status",
    "get_pr_work_items",
    "get_pull_request",
    "get_repo_file_content",
    "get_repository_context_status",
    "list_commits",
    "list_pr_labels",
    "list_pr_reviewers",
    "list_pull_requests",
    "list_repo_items",
    "post_pr_comment",
    "post_pr_comments",
    "post_rich_comments",
    "query_work_items",
    "remove_pr_label",
    "remove_pr_reviewer",
    "reply_to_pr_comment",
    "repository_discovery",
    "resolve_pr_comments",
    "retarget_pull_request",
    "set_pr_draft_status",
    "set_repository_context",
    "update_pull_request",
]
