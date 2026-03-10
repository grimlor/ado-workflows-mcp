"""MCP tools for repository context management."""

from __future__ import annotations

from typing import Any

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.context import (
    clear_repository_context as _lib_clear,
    get_context_status as _lib_status,
    set_repository_context as _lib_set,
)

from ado_workflows_mcp.mcp_instance import mcp


@mcp.tool()
def set_repository_context(
    working_directory: str,
) -> dict[str, Any] | ActionableError:
    """Cache repository context for the session.

    Sets the working directory and caches discovery results so
    subsequent tool calls skip redundant git CLI lookups.

    Args:
        working_directory: Path to the git repository root.
    """
    try:
        return _lib_set(working_directory)
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=(
                    "Context setup failed. Verify the working directory is a valid git repo."
                ),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="set_repository_context",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Verify the working directory path exists and"
                    " contains a .git folder, then retry."
                ),
                checks=[
                    "Confirm the path is an absolute path to a git repository",
                    "Ensure git remotes include an Azure DevOps URL",
                ],
            ),
        )


@mcp.tool()
def get_repository_context_status() -> dict[str, Any] | ActionableError:
    """Inspect current cached context state.

    Returns cache state, timestamps, and working directory details.
    Useful for agents debugging context issues or verifying setup.
    """
    try:
        return _lib_status()
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=("Context status check failed. Review error details and retry."),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_repository_context_status",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Context status check failed unexpectedly."
                    " Try clearing and re-setting context."
                ),
                steps=[
                    "Call clear_repository_context",
                    "Call set_repository_context with a valid path",
                ],
            ),
        )


@mcp.tool()
def clear_repository_context() -> dict[str, Any] | ActionableError:
    """Reset cached context.

    Clears cached discovery results, forcing fresh discovery on
    the next tool call. Idempotent — safe to call even when no
    context is set.
    """
    try:
        return _lib_clear()
    except ActionableError as exc:
        if exc.ai_guidance is None:
            exc.ai_guidance = AIGuidance(
                action_required=("Context clear failed. Review error details and retry."),
            )
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="clear_repository_context",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required=(
                    "Context clear failed unexpectedly."
                    " This is unusual \u2014 retry the operation."
                ),
            ),
        )
