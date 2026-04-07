"""
BDD tests for tools/repository_context.py — context management tools.

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
    ado_workflows.discovery.Repo (GitPython — used by set_repository_context)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError, AIGuidance
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
_REPO_PATCH = "ado_workflows.discovery.Repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_git_repo(remote_url: str = _ADO_REMOTE) -> MagicMock:
    """Return a mock GitPython Repo with an origin remote."""
    repo = MagicMock()
    repo.remotes.origin.url = remote_url

    def _bool(_self: object) -> bool:
        return True

    def _len(_self: object) -> int:
        return 1

    repo.remotes.__bool__ = _bool
    repo.remotes.__len__ = _len
    return repo


def _error_with_guidance() -> ActionableError:
    """Return an ActionableError that already has ai_guidance set."""
    return ActionableError.connection(
        service="AzureDevOps",
        url="https://dev.azure.com",
        raw_error="test error",
        suggestion="test suggestion",
        ai_guidance=AIGuidance(action_required="pre-set guidance"),
    )


class TestSetRepositoryContext:
    """
    REQUIREMENT: Cache repository context for the session.

    WHO: Agents that call multiple tools against the same repo.
    WHAT: Sets the working directory and caches discovery results for reuse.
    WHY: Eliminates redundant discovery subprocess calls across tool invocations.

    MOCK BOUNDARY:
        Mock:  `git.Repo` (GitPython — I/O boundary for discovery)
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
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
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
        # Given: a directory with no .git (real discovery returns nothing)
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

    def test_actionable_error_without_guidance_gets_enriched(self) -> None:
        """
        Given the library raises ActionableError without ai_guidance
        When set_repository_context is called
        Then returns the error with ai_guidance enriched
        """
        # Given: library raises ActionableError with no ai_guidance
        bare_error = ActionableError(
            error="Discovery failed",
            error_type="VALIDATION",
            service="ado-workflows",
        )
        with patch(
            "ado_workflows_mcp.tools.repository_context._lib_set",
            side_effect=bare_error,
        ):
            # When: called
            result = set_repository_context(working_directory="/fake/path")

        # Then: returns ActionableError with ai_guidance enriched
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance to be enriched, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "context" in guidance or "git" in guidance or "working directory" in guidance, (
            f"ai_guidance should mention context/git/working directory, got: {guidance}"
        )

    @patch(
        "ado_workflows_mcp.tools.repository_context._lib_set", side_effect=_error_with_guidance()
    )
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When set_repository_context is called
        Then returns the error with original ai_guidance preserved
        """
        result = set_repository_context(working_directory="/fake")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    def test_unexpected_exception_returns_internal_error(self) -> None:
        """
        Given the library raises an unexpected Exception
        When set_repository_context is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: library raises generic exception
        with patch(
            "ado_workflows_mcp.tools.repository_context._lib_set",
            side_effect=RuntimeError("segfault"),
        ):
            # When: called
            result = set_repository_context(working_directory="/fake/path")

        # Then: returns ActionableError with internal error details
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.checks is not None, (
            f"Expected checks in ai_guidance for internal error. Got: {result.ai_guidance}"
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
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
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

    def test_actionable_error_without_guidance_gets_enriched(self) -> None:
        """
        Given the library raises ActionableError without ai_guidance
        When get_repository_context_status is called
        Then returns the error with ai_guidance enriched
        """
        # Given: library raises ActionableError with no ai_guidance
        bare_error = ActionableError(
            error="Cache read failed",
            error_type="INTERNAL",
            service="ado-workflows",
        )
        with patch(
            "ado_workflows_mcp.tools.repository_context._lib_status",
            side_effect=bare_error,
        ):
            # When: called
            result = get_repository_context_status()

        # Then: returns ActionableError with ai_guidance enriched
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance to be enriched, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "context" in guidance or "status" in guidance or "retry" in guidance, (
            f"ai_guidance should mention context/status/retry, got: {guidance}"
        )

    @patch(
        "ado_workflows_mcp.tools.repository_context._lib_status",
        side_effect=_error_with_guidance(),
    )
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When get_repository_context_status is called
        Then returns the error with original ai_guidance preserved
        """
        result = get_repository_context_status()
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    def test_unexpected_exception_returns_internal_error(self) -> None:
        """
        Given the library raises an unexpected Exception
        When get_repository_context_status is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: library raises generic exception
        with patch(
            "ado_workflows_mcp.tools.repository_context._lib_status",
            side_effect=RuntimeError("cache corrupted"),
        ):
            # When: called
            result = get_repository_context_status()

        # Then: returns ActionableError with internal error details
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.steps is not None, (
            f"Expected recovery steps in ai_guidance. Got: {result.ai_guidance}"
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
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
            set_repository_context(working_directory=str(tmp_path))

        # When: clear is called
        result = clear_repository_context()

        # Then: returns confirmation dict
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )

        # And: subsequent status shows no context
        status = get_repository_context_status()
        assert isinstance(status, dict), (
            f"Expected dict status, got {type(status).__name__}: {status}"
        )
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

    @patch(
        "ado_workflows_mcp.tools.repository_context._lib_clear", side_effect=_error_with_guidance()
    )
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When clear_repository_context is called
        Then returns the error with original ai_guidance preserved
        """
        result = clear_repository_context()
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    def test_unexpected_exception_returns_internal_error(self) -> None:
        """
        Given the library raises an unexpected Exception
        When clear_repository_context is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: library raises generic exception
        with patch(
            "ado_workflows_mcp.tools.repository_context._lib_clear",
            side_effect=RuntimeError("unexpected failure"),
        ):
            # When: called
            result = clear_repository_context()

        # Then: returns ActionableError with internal error details
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "clear" in guidance or "retry" in guidance, (
            f"ai_guidance should mention clear/retry, got: {guidance}"
        )
