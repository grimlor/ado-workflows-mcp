"""BDD tests for tools/repository_context.py — context management tools.

Covers:
- TestSetRepositoryContext: caching repository context for the session
- TestGetRepositoryContextStatus: inspecting cached context state
- TestClearRepositoryContext: resetting cached context

Public API surface (from src/ado_workflows_mcp/tools/repository_context.py):
    set_repository_context(working_directory: str) -> dict[str, Any] | ActionableError
    get_repository_context_status() -> dict[str, Any] | ActionableError
    clear_repository_context() -> dict[str, Any] | ActionableError

Library API surface (from ado_workflows.context):
    set_repository_context(working_directory: str) -> dict[str, Any]
    get_context_status() -> dict[str, Any]
    clear_repository_context() -> dict[str, Any]
    RepositoryContext (class with set/get/clear/status class methods)

I/O boundary:
    ado_workflows.discovery.subprocess.run (git CLI — used by set_repository_context)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from ado_workflows.context import RepositoryContext

from ado_workflows_mcp.tools.repository_context import (
    clear_repository_context,
    get_repository_context_status,
    set_repository_context,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_SUBPROCESS_PATCH = "ado_workflows.discovery.subprocess.run"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_success(remote: str = _ADO_REMOTE) -> MagicMock:
    """Return a mock subprocess result for a successful git remote -v."""
    return MagicMock(returncode=0, stdout=remote)


def _git_failure() -> MagicMock:
    """Return a mock subprocess result for a non-git directory."""
    return MagicMock(returncode=1, stderr="fatal: not a git repository")


class TestSetRepositoryContext:
    """
    REQUIREMENT: Cache repository context for the session.

    WHO: Agents that call multiple tools against the same repo.
    WHAT: Sets the working directory and caches discovery results for reuse.
    WHY: Eliminates redundant discovery subprocess calls across tool invocations.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — I/O boundary for discovery)
        Real:  tool function, `set_repository_context`, `RepositoryContext` caching,
               response formatting, `tmp_path` filesystem
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_directory_caches_and_returns_context(self, tmp_path: Any) -> None:
        """
        Given a valid working directory
        When set_repository_context is called
        Then caches context and returns context dict
        """
        # Given: a tmp_path with .git directory
        (tmp_path / ".git").mkdir()
        with patch(_SUBPROCESS_PATCH, return_value=_git_success()):
            # When: set_repository_context is called
            result = set_repository_context(working_directory=str(tmp_path))

        # Then: returns a dict with success info
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )
        assert result.get("success") is True, (
            f"Expected success=True in context result. Got: {result}"
        )

    def test_invalid_directory_returns_error_dict(self, tmp_path: Any) -> None:
        """
        Given an invalid directory
        When set_repository_context is called
        Then returns error dict with success=False and suggestion
        """
        # Given: a directory with no .git (subprocess returns failure)
        with patch(_SUBPROCESS_PATCH, return_value=_git_failure()):
            # When: called on a non-repo directory
            result = set_repository_context(working_directory=str(tmp_path))

        # Then: returns an error dict
        assert isinstance(result, dict), (
            f"Expected dict error result, got {type(result).__name__}: {result}"
        )
        assert result.get("success") is False, (
            f"Expected success=False for invalid dir. Got: {result}"
        )
        assert result.get("suggestion") is not None, (
            f"Expected suggestion on error dict. Got: {result}"
        )


class TestGetRepositoryContextStatus:
    """
    REQUIREMENT: Inspect current cached context state.

    WHO: Agents debugging context issues or verifying setup.
    WHAT: Returns cache state, timestamps, working directory.
    WHY: Observability for agent self-diagnosis.

    MOCK BOUNDARY:
        Mock:  nothing — reads cached in-process state only
        Real:  tool function, `get_context_status`, response formatting
        Never: FastMCP framework, library functions in our codebase
    """

    def test_context_set_returns_details(self, tmp_path: Any) -> None:
        """
        Given context is set
        When get_repository_context_status is called
        Then returns context details with context_set=True
        """
        # Given: context has been set via set_repository_context
        (tmp_path / ".git").mkdir()
        with patch(_SUBPROCESS_PATCH, return_value=_git_success()):
            set_repository_context(working_directory=str(tmp_path))

        # When: status is queried
        result = get_repository_context_status()

        # Then: reports context_set=True
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )
        assert result.get("context_set") is True, (
            f"Expected context_set=True after setting context. Got: {result}"
        )

    def test_no_context_returns_not_set(self) -> None:
        """
        Given no context has been set
        When get_repository_context_status is called
        Then returns context_set=False
        """
        # Given: clear any existing context
        RepositoryContext.clear()

        # When: status is queried
        result = get_repository_context_status()

        # Then: reports context_set=False
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )
        assert result.get("context_set") is False, (
            f"Expected context_set=False when no context set. Got: {result}"
        )


class TestClearRepositoryContext:
    """
    REQUIREMENT: Reset cached context.

    WHO: Agents switching between repositories.
    WHAT: Clears cached discovery results.
    WHY: Forces fresh discovery on next tool call.

    MOCK BOUNDARY:
        Mock:  nothing — mutates cached in-process state only
        Real:  tool function, `clear_repository_context`, response formatting
        Never: FastMCP framework, library functions in our codebase
    """

    def test_context_set_clears_and_returns_confirmation(self, tmp_path: Any) -> None:
        """
        Given context is set
        When clear_repository_context is called
        Then clears and returns confirmation dict
        """
        # Given: context has been set
        (tmp_path / ".git").mkdir()
        with patch(_SUBPROCESS_PATCH, return_value=_git_success()):
            set_repository_context(working_directory=str(tmp_path))

        # When: clear is called
        result = clear_repository_context()

        # Then: returns confirmation dict
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )

        # And: subsequent status shows no context
        status = get_repository_context_status()
        assert status.get("context_set") is False, (
            f"Expected context_set=False after clear. Got: {status}"
        )

    def test_no_context_returns_confirmation_idempotent(self) -> None:
        """
        Given no context has been set
        When clear_repository_context is called
        Then returns confirmation dict (idempotent)
        """
        # Given: ensure no context
        RepositoryContext.clear()

        # When: clear is called with nothing set
        result = clear_repository_context()

        # Then: still returns confirmation dict (idempotent)
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )
