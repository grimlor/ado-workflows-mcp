"""MCP tool modules — explicit re-exports.

Importing this package triggers ``@mcp.tool()`` registration for every
tool function listed below.  Each sub-module decorates its functions
with ``@mcp.tool()`` at import time.
"""

from __future__ import annotations

import ado_workflows_mcp.tools._fixup_forward_refs as _fixup_forward_refs  # noqa: F401
from ado_workflows_mcp.tools.pr_comments import (
    analyze_pr_comments as analyze_pr_comments,
    post_pr_comment as post_pr_comment,
    reply_to_pr_comment as reply_to_pr_comment,
    resolve_pr_comments as resolve_pr_comments,
)
from ado_workflows_mcp.tools.pr_review import (
    analyze_pending_reviews as analyze_pending_reviews,
    get_pr_review_status as get_pr_review_status,
)
from ado_workflows_mcp.tools.pull_requests import (
    create_pull_request as create_pull_request,
    establish_pr_context as establish_pr_context,
)
from ado_workflows_mcp.tools.repositories import repository_discovery as repository_discovery
from ado_workflows_mcp.tools.repository_context import (
    clear_repository_context as clear_repository_context,
    get_repository_context_status as get_repository_context_status,
    set_repository_context as set_repository_context,
)

__all__ = [
    "analyze_pending_reviews",
    "analyze_pr_comments",
    "clear_repository_context",
    "create_pull_request",
    "establish_pr_context",
    "get_pr_review_status",
    "get_repository_context_status",
    "post_pr_comment",
    "reply_to_pr_comment",
    "repository_discovery",
    "resolve_pr_comments",
    "set_repository_context",
]
