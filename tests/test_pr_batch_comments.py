"""
BDD tests for tools/pr_comments.py — batch comment posting with positioning.

Covers:
- TestPostPRComments: batch-post comments with file/line positioning

Public API surface (from src/ado_workflows_mcp/tools/pr_comments.py):
    post_pr_comments(pr_url_or_id, comments, *, dry_run, working_directory)
        -> PostingResult | ActionableError

Library API surface:
    ado_workflows.comments.post_comments(client, repository, pr_id, comments,
        project, *, dry_run) -> PostingResult
    ado_workflows.iterations.get_latest_iteration_context(client, repository,
        pr_id, project) -> IterationContext
    ado_workflows.pr.establish_pr_context(url_or_id, working_directory)
        -> AzureDevOpsPRContext

I/O boundaries:
    ado_workflows.discovery.Repo (GitPython)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_pull_request_iterations, client.git.get_pull_request_iteration_changes,
    client.git.create_thread (SDK REST calls)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.context import RepositoryContext
from ado_workflows.models import (
    PostingResult,
)

from ado_workflows_mcp.tools.pr_comments import post_pr_comments

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_PR_URL = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo/pullrequest/42"
_REPO_PATCH = "ado_workflows.discovery.Repo"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"

_ESTABLISH_PR_PATCH = "ado_workflows_mcp.tools.pr_comments._lib_establish_pr"


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


def _setup_context(tmp_path: Any) -> None:
    """Set up repository context with git.Repo mocked at the I/O edge."""
    (tmp_path / ".git").mkdir()
    with patch(_REPO_PATCH, return_value=_mock_git_repo()):
        RepositoryContext.set(working_directory=str(tmp_path))


def _mock_connection_factory() -> MagicMock:
    """Return a mock ConnectionFactory that produces a mock Connection."""
    factory = MagicMock()
    factory.return_value.get_connection.return_value = MagicMock()
    return factory


def _error_with_guidance() -> ActionableError:
    """Return an ActionableError that already has ai_guidance set."""
    return ActionableError.connection(
        service="AzureDevOps",
        url="https://dev.azure.com",
        raw_error="test error",
        suggestion="test suggestion",
        ai_guidance=AIGuidance(action_required="pre-set guidance"),
    )


# ---------------------------------------------------------------------------
# TestPostPRComments
# ---------------------------------------------------------------------------


class TestPostPRComments:
    """
    REQUIREMENT: An MCP consumer can batch-post positioned comments to a
    PR using either a URL or numeric ID.

    WHO: AI agents and MCP clients performing code review.
    WHAT: (1) a PR URL and comments with file/line produce a PostingResult
              with successes
          (2) a numeric PR ID with working_directory resolves context and
              posts comments
          (3) dry_run=True returns a validation result without posting
          (4) a comment with line_number but no file_path produces a failure
              in the result
          (5) an invalid PR URL returns ActionableError
          (6) an unexpected non-ActionableError exception returns
              ActionableError.internal with ai_guidance
    WHY: Enables code review workflows without requiring the consumer to
         understand iteration tracking, changeTrackingId, or SDK threading.

    MOCK BOUNDARY:
        Mock:  git.Repo (GitPython — context), ConnectionFactory (auth),
               client.git.get_pull_request_iterations,
               client.git.get_pull_request_iteration_changes,
               client.git.create_thread (SDK REST calls)
        Real:  tool function, establish_pr_context, post_comments,
               get_latest_iteration_context, dict-to-CommentPayload conversion,
               iteration context resolution, PostingResult construction
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_url_with_positioned_comments_returns_posting_result(self, tmp_path: Any) -> None:
        """
        Given a PR URL and 2 comments with file/line positioning
        When post_pr_comments is called
        Then returns PostingResult with 2 successes
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns iterations and changes, then thread creation succeeds
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            # Iterations
            iter_mock = MagicMock()
            iter_mock.id = 2
            iter_mock.created_date = "2026-03-18T00:00:00Z"
            iter_mock.source_ref_commit = MagicMock(commit_id="abc123")
            iter_mock.target_ref_commit = MagicMock(commit_id="def456")
            mock_client.git.get_pull_request_iterations.return_value = [iter_mock]
            # Iteration changes
            change1 = MagicMock()
            change1.additional_properties = {
                "item": {"path": "/src/main.py"},
                "changeType": "edit",
            }
            change1.change_tracking_id = 1
            change2 = MagicMock()
            change2.additional_properties = {
                "item": {"path": "/src/utils.py"},
                "changeType": "add",
            }
            change2.change_tracking_id = 2
            changes_response = MagicMock()
            changes_response.change_entries = [change1, change2]
            mock_client.git.get_pull_request_iteration_changes.return_value = changes_response
            # Thread creation
            thread1 = MagicMock()
            thread1.id = 101
            thread2 = MagicMock()
            thread2.id = 102
            mock_client.git.create_thread.side_effect = [thread1, thread2]
            mock_ado_client_cls.return_value = mock_client

            # When: batch post
            result = post_pr_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    {
                        "content": "Fix null check",
                        "file_path": "src/main.py",
                        "line_number": 42,
                    },
                    {
                        "content": "Add docstring",
                        "file_path": "src/utils.py",
                        "line_number": 10,
                    },
                ],
            )

        # Then: returns PostingResult with 2 successes
        assert isinstance(result, PostingResult), (
            f"Expected PostingResult, got {type(result).__name__}: {result}"
        )
        assert len(result.posted) == 2, f"Expected 2 posted, got {len(result.posted)}"
        assert len(result.failures) == 0, f"Expected 0 failures, got {len(result.failures)}"

    def test_numeric_id_with_working_directory_resolves_context(self, tmp_path: Any) -> None:
        """
        Given a numeric PR ID and working_directory
        When post_pr_comments is called
        Then context resolved from working_directory, comments posted
        """
        # Given: context set via working_directory
        (tmp_path / ".git").mkdir()
        mock_factory = _mock_connection_factory()
        with (
            patch(_REPO_PATCH, return_value=_mock_git_repo()),
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            # Set context
            RepositoryContext.set(working_directory=str(tmp_path))

            mock_client = Mock()
            # Iterations
            iter_mock = MagicMock()
            iter_mock.id = 1
            iter_mock.created_date = "2026-03-18T00:00:00Z"
            iter_mock.source_ref_commit = MagicMock(commit_id="abc")
            iter_mock.target_ref_commit = MagicMock(commit_id="def")
            mock_client.git.get_pull_request_iterations.return_value = [iter_mock]
            # No file-positioned comments — just a general comment
            changes_response = MagicMock()
            changes_response.change_entries = []
            mock_client.git.get_pull_request_iteration_changes.return_value = changes_response
            # Thread creation
            thread = MagicMock()
            thread.id = 200
            mock_client.git.create_thread.return_value = thread
            mock_ado_client_cls.return_value = mock_client

            # When: called with numeric ID
            result = post_pr_comments(
                pr_url_or_id="42",
                comments=[{"content": "General comment"}],
                working_directory=str(tmp_path),
            )

        # Then: returns PostingResult
        assert isinstance(result, PostingResult), (
            f"Expected PostingResult, got {type(result).__name__}: {result}"
        )
        assert len(result.posted) == 1, f"Expected 1 posted, got {len(result.posted)}"

    def test_dry_run_validates_without_posting(self, tmp_path: Any) -> None:
        """
        Given dry_run=True
        When post_pr_comments is called
        Then returns validation result without making API calls
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            # Iterations
            iter_mock = MagicMock()
            iter_mock.id = 1
            iter_mock.created_date = "2026-03-18T00:00:00Z"
            iter_mock.source_ref_commit = MagicMock(commit_id="abc")
            iter_mock.target_ref_commit = MagicMock(commit_id="def")
            mock_client.git.get_pull_request_iterations.return_value = [iter_mock]
            changes_response = MagicMock()
            changes_response.change_entries = []
            mock_client.git.get_pull_request_iteration_changes.return_value = changes_response
            mock_ado_client_cls.return_value = mock_client

            # When: dry_run=True
            result = post_pr_comments(
                pr_url_or_id=_PR_URL,
                comments=[{"content": "Test comment"}],
                dry_run=True,
            )

        # Then: returns PostingResult and create_thread was never called
        assert isinstance(result, PostingResult), (
            f"Expected PostingResult, got {type(result).__name__}: {result}"
        )
        mock_client.git.create_thread.assert_not_called()

    def test_line_without_file_path_produces_failure(self, tmp_path: Any) -> None:
        """
        Given a comment with line_number but no file_path
        When post_pr_comments is called
        Then the comment appears in failures (validation error)
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            iter_mock = MagicMock()
            iter_mock.id = 1
            iter_mock.created_date = "2026-03-18T00:00:00Z"
            iter_mock.source_ref_commit = MagicMock(commit_id="abc")
            iter_mock.target_ref_commit = MagicMock(commit_id="def")
            mock_client.git.get_pull_request_iterations.return_value = [iter_mock]
            changes_response = MagicMock()
            changes_response.change_entries = []
            mock_client.git.get_pull_request_iteration_changes.return_value = changes_response
            mock_ado_client_cls.return_value = mock_client

            # When: comment has line_number but no file_path
            result = post_pr_comments(
                pr_url_or_id=_PR_URL,
                comments=[{"content": "Bad comment", "line_number": 42}],
            )

        # Then: failure in result with recovery guidance
        assert isinstance(result, PostingResult), (
            f"Expected PostingResult, got {type(result).__name__}: {result}"
        )
        assert len(result.failures) >= 1, (
            f"Expected at least 1 failure for line_number without file_path, "
            f"got {len(result.failures)}"
        )
        failure = result.failures[0]
        assert isinstance(failure, ActionableError), (
            f"Expected ActionableError in failures, got {type(failure).__name__}"
        )
        assert failure.ai_guidance is not None, (
            f"Expected ai_guidance on validation failure, got None. Error: {failure.error}"
        )

    def test_invalid_pr_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When post_pr_comments is called
        Then returns ActionableError
        """
        # When: called with unparseable URL
        result = post_pr_comments(
            pr_url_or_id="https://github.com/not-ado/repo",
            comments=[{"content": "Test"}],
        )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError for invalid URL, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )

    def test_unexpected_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given an unexpected exception at the I/O boundary
        When post_pr_comments is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set, but ConnectionFactory raises
        _setup_context(tmp_path)

        mock_factory = MagicMock()
        mock_factory.return_value.get_connection.side_effect = RuntimeError(
            "unexpected crash",
        )
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            # When: called with valid PR URL (URL parsing succeeds, get_client fails)
            result = post_pr_comments(
                pr_url_or_id=_PR_URL,
                comments=[{"content": "Test"}],
            )

        # Then: returns ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )
        assert "unexpected crash" in result.error, (
            f"Expected raw error in message, got: {result.error}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When post_pr_comments is called
        Then returns the error with original ai_guidance preserved
        """
        result = post_pr_comments(
            pr_url_or_id="https://dev.azure.com/O/P/_git/R/pullrequest/1",
            comments=[{"content": "x"}],
        )
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )
