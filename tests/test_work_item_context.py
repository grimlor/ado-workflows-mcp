"""
BDD tests for tools/work_item_context.py — work item context resolution tool.

Covers:
    TestEstablishWorkItemContextTool — wrap library establish_work_item_context

Public API surface (from src/ado_workflows_mcp/tools/work_item_context.py):
    establish_work_item_context(work_item_url_or_id: str, working_directory: str | None)
        -> AzureDevOpsWorkItemContext | ActionableError

Library API surface:
    ado_workflows.work_items.establish_work_item_context(url_or_id, working_directory)
        -> AzureDevOpsWorkItemContext

I/O boundaries:
    ado_workflows.discovery.Repo (GitPython) — only mocked for the bare-ID path
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.context import RepositoryContext
from ado_workflows.work_items import AzureDevOpsWorkItemContext

from ado_workflows_mcp.tools.work_item_context import establish_work_item_context

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_WORK_ITEM_URL = "https://msazure.visualstudio.com/One/_workitems/edit/37453680"
_REPO_PATCH = "ado_workflows.discovery.Repo"
_LIB_ESTABLISH_PATCH = "ado_workflows_mcp.tools.work_item_context._lib_establish_work_item"


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


class TestEstablishWorkItemContextTool:
    """
    REQUIREMENT: The MCP tool wraps the library
    establish_work_item_context, returning the AzureDevOpsWorkItemContext
    on success and ActionableError on failure with operation-specific
    ai_guidance attached when the library did not provide guidance.

    WHO: Agents resolving a pasted work-item URL or bare ID into a
        structured context that can be threaded into subsequent
        work-item tool calls without re-parsing.
    WHAT: (1) URL input → returns an AzureDevOpsWorkItemContext whose
              org / project / id come from URL parsing, with
              source="url".
          (2) Numeric input + valid repository context → returns a
              context whose org / project come from the cached / fresh
              repository context and id is the parsed integer, with
              source="repository_context".
          (3) Library raises ActionableError → tool returns the error
              unchanged (preserves library ai_guidance).
          (4) Library raises ActionableError with no ai_guidance →
              tool attaches a generic "resolution failed; provide a
              full URL or set repository context" guidance before
              returning.
          (5) Unexpected exception → tool returns
              ActionableError.internal with operation-specific guidance.

    MOCK BOUNDARY:
        Mock:  ado_workflows.discovery.Repo (GitPython filesystem edge —
               the only mock needed for the bare-ID path, since URL
               parsing is pure and never touches the filesystem).
        Real:  the MCP tool function, the library
               establish_work_item_context, parse_ado_work_item_url,
               RepositoryContext, AzureDevOpsWorkItemContext
               construction, ActionableError construction, AIGuidance
               attachment.
        Never: the MCP tool function (SUT), establish_work_item_context
               (in-codebase function — mocking it would hide the
               URL→org integration this tool exists to verify).
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_url_input_returns_work_item_context_with_source_url(self) -> None:
        """
        Given a valid work item URL
        When establish_work_item_context is called
        Then returns AzureDevOpsWorkItemContext with source="url" and
            org/project/id parsed from the URL
        """
        # When: called with a full work item URL
        result = establish_work_item_context(work_item_url_or_id=_WORK_ITEM_URL)

        # Then: returns resolved context with URL-derived fields
        assert isinstance(result, AzureDevOpsWorkItemContext), (
            f"Expected AzureDevOpsWorkItemContext, got {type(result).__name__}: {result}"
        )
        assert result.source == "url", f"Expected source='url', got {result.source!r}"
        assert result.organization == "msazure", (
            f"Expected organization='msazure', got {result.organization!r}"
        )
        assert result.project == "One", f"Expected project='One', got {result.project!r}"
        assert result.work_item_id == 37453680, (
            f"Expected work_item_id=37453680, got {result.work_item_id}"
        )

    def test_numeric_input_returns_work_item_context_with_source_repository_context(
        self, tmp_path: Any
    ) -> None:
        """
        Given a numeric work item ID and cached repository context
        When establish_work_item_context is called
        Then returns AzureDevOpsWorkItemContext with
            source="repository_context" and org/project from cache
        """
        # Given: cached repository context
        (tmp_path / ".git").mkdir()
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
            RepositoryContext.set(working_directory=str(tmp_path))

        # When: called with a numeric ID
        result = establish_work_item_context(work_item_url_or_id="37453680")

        # Then: returns context with repository_context-derived fields
        assert isinstance(result, AzureDevOpsWorkItemContext), (
            f"Expected AzureDevOpsWorkItemContext, got {type(result).__name__}: {result}"
        )
        assert result.source == "repository_context", (
            f"Expected source='repository_context', got {result.source!r}"
        )
        assert result.organization == "TestOrg", (
            f"Expected organization='TestOrg' from cached context, got {result.organization!r}"
        )
        assert result.project == "TestProject", (
            f"Expected project='TestProject' from cached context, got {result.project!r}"
        )
        assert result.work_item_id == 37453680, (
            f"Expected work_item_id=37453680, got {result.work_item_id}"
        )

    def test_library_actionable_error_propagates_unchanged(self) -> None:
        """
        Given the library raises ActionableError with ai_guidance set
        When establish_work_item_context is called
        Then the tool returns the same ActionableError unchanged
            (preserving the library's ai_guidance)
        """
        # Given: library raises an error that already has guidance
        library_error = ActionableError.validation(
            service="ado-workflows",
            field_name="url_or_id",
            reason="library reason",
            suggestion="library suggestion",
            ai_guidance=AIGuidance(action_required="library guidance"),
        )

        # When: the library entry point raises
        with patch(_LIB_ESTABLISH_PATCH, side_effect=library_error):
            result = establish_work_item_context(work_item_url_or_id="bogus")

        # Then: same error returned, library guidance preserved
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result is library_error, (
            "Expected the same ActionableError instance to be returned unchanged"
        )
        assert result.ai_guidance is not None, (
            "Expected library ai_guidance to be preserved, got None"
        )
        assert result.ai_guidance.action_required == "library guidance", (
            f"Expected library ai_guidance preserved, got {result.ai_guidance.action_required!r}"
        )

    def test_library_error_without_guidance_gets_default_guidance(self) -> None:
        """
        Given the library raises ActionableError with no ai_guidance
        When establish_work_item_context is called
        Then the tool attaches a default ai_guidance mentioning the
            URL alternative or repository context before returning
        """
        # Given: library error with no guidance
        library_error = ActionableError.validation(
            service="ado-workflows",
            field_name="url_or_id",
            reason="ambiguous",
            suggestion="provide more info",
        )
        assert library_error.ai_guidance is None, (
            "Test setup invariant: library_error must start with no guidance"
        )

        # When: the library entry point raises
        with patch(_LIB_ESTABLISH_PATCH, side_effect=library_error):
            result = establish_work_item_context(work_item_url_or_id="bogus")

        # Then: tool attached default guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            "Expected default ai_guidance to be attached, got None"
        )
        action = result.ai_guidance.action_required.lower()
        assert "url" in action or "context" in action, (
            f"Expected default guidance to mention URL or context, "
            f"got: {result.ai_guidance.action_required!r}"
        )

    def test_unexpected_exception_returns_internal_actionable_error(self) -> None:
        """
        Given the library raises an unexpected (non-ActionableError) exception
        When establish_work_item_context is called
        Then the tool returns ActionableError.internal with operation-specific
            ai_guidance
        """
        # Given: library raises a bare exception
        with patch(_LIB_ESTABLISH_PATCH, side_effect=RuntimeError("kaboom")):
            # When: tool is called
            result = establish_work_item_context(work_item_url_or_id=_WORK_ITEM_URL)

        # Then: returns ActionableError.internal with guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "internal", (
            f"Expected error_type='internal', got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on internal error, got None"
        action = result.ai_guidance.action_required.lower()
        assert "url" in action or "context" in action or "work item" in action, (
            f"Expected guidance to mention URL/context/work item, "
            f"got: {result.ai_guidance.action_required!r}"
        )
