"""BDD tests for tools/pr_comments.py — PR comment analysis and management.

Covers:
- TestAnalyzePRComments: analyzing comment threads on a PR
- TestPostPRComment: posting a new comment thread
- TestReplyToPRComment: replying to an existing thread
- TestResolvePRComments: batch-resolving comment threads

Public API surface (from src/ado_workflows_mcp/tools/pr_comments.py):
    analyze_pr_comments(pr_url_or_id, working_directory) -> CommentAnalysis | ActionableError
    post_pr_comment(pr_url_or_id, comment_text, status, working_directory) -> int | ActionableError
    reply_to_pr_comment(pr_url_or_id, thread_id, comment_text, working_directory)
        -> int | ActionableError
    resolve_pr_comments(pr_url_or_id, thread_ids, status, working_directory)
        -> ResolveResult | ActionableError

Library API surface:
    ado_workflows.comments.analyze_pr_comments(client, pr_id, project, repository)
        -> CommentAnalysis
    ado_workflows.comments.post_comment(client, repository, pr_id, content, project, *, status)
        -> int
    ado_workflows.comments.reply_to_comment(client, repository, pr_id, thread_id, content, project)
        -> int
    ado_workflows.comments.resolve_comments(client, repository, pr_id, thread_ids, project, *,
        status) -> ResolveResult

I/O boundaries:
    ado_workflows.discovery.subprocess.run (git CLI)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_threads, client.git.create_thread, client.git.create_comment,
    client.git.update_thread (SDK REST calls)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext
from ado_workflows.models import CommentAnalysis, ResolveResult

from ado_workflows_mcp.tools.pr_comments import (
    analyze_pr_comments,
    post_pr_comment,
    reply_to_pr_comment,
    resolve_pr_comments,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_PR_URL = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo/pullrequest/42"
_SUBPROCESS_PATCH = "ado_workflows.discovery.subprocess.run"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_success(remote: str = _ADO_REMOTE) -> MagicMock:
    """Return a mock subprocess result for a successful git remote -v."""
    return MagicMock(returncode=0, stdout=remote)


def _setup_context(tmp_path: Any) -> None:
    """Set up repository context with subprocess mocked."""
    (tmp_path / ".git").mkdir()
    with patch(_SUBPROCESS_PATCH, return_value=_git_success()):
        RepositoryContext.set(working_directory=str(tmp_path))


def _mock_connection_factory() -> MagicMock:
    """Return a mock ConnectionFactory that produces a mock Connection."""
    factory = MagicMock()
    factory.return_value.get_connection.return_value = MagicMock()
    return factory


def _mock_thread(
    thread_id: int = 1, status: str = "active", content: str = "Fix this"
) -> MagicMock:
    """Return a mock comment thread object."""
    thread = MagicMock()
    thread.id = thread_id
    thread.status = status
    thread.properties = {}
    comment = MagicMock()
    comment.content = content
    comment.author.display_name = "Reviewer"
    comment.author.unique_name = "reviewer@example.com"
    comment.comment_type = "text"
    comment.is_deleted = False
    comment.published_date = "2025-01-01T00:00:00Z"
    thread.comments = [comment]
    thread.thread_context = None
    return thread


class TestAnalyzePRComments:
    """
    REQUIREMENT: Analyze all comment threads on a PR.

    WHO: Agents preparing to review or resolve PR comments.
    WHAT: Fetches threads, categorizes by status, extracts author statistics.
    WHY: Gives agent a structured overview before taking action on comments.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — context), `ConnectionFactory` (auth),
               `client.git.get_threads` (SDK REST call)
        Real:  tool function, `establish_pr_context`, `analyze_pr_comments`,
               thread categorization, author stats, dataclass construction
        Never: FastMCP framework, library functions in our codebase
    """

    def test_pr_with_comments_returns_analysis(self, tmp_path: Any) -> None:
        """
        Given a PR with comments
        When analyze_pr_comments is called
        Then returns CommentAnalysis dataclass
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns threads
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.return_value = [
                _mock_thread(thread_id=1, status="active"),
                _mock_thread(thread_id=2, status="fixed"),
            ]
            mock_ado_client_cls.return_value = mock_client

            # When: analyze_pr_comments called
            result = analyze_pr_comments(pr_url_or_id=_PR_URL)

        # Then: returns CommentAnalysis
        assert isinstance(result, CommentAnalysis), (
            f"Expected CommentAnalysis, got {type(result).__name__}: {result}"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"

    def test_pr_with_no_comments_returns_empty_summary(self, tmp_path: Any) -> None:
        """
        Given a PR with no comments
        When analyze_pr_comments is called
        Then returns CommentAnalysis with empty summary
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns no threads
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.return_value = []
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = analyze_pr_comments(pr_url_or_id=_PR_URL)

        # Then: returns CommentAnalysis with zeros
        assert isinstance(result, CommentAnalysis), (
            f"Expected CommentAnalysis, got {type(result).__name__}: {result}"
        )
        assert result.comment_summary.total_threads == 0, (
            f"Expected 0 total threads, got {result.comment_summary.total_threads}"
        )

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure
        When analyze_pr_comments is called
        Then returns ActionableError
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK raises
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.side_effect = Exception("timeout")
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = analyze_pr_comments(pr_url_or_id=_PR_URL)

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.action_required, (
            "Expected non-empty action_required in ai_guidance"
        )


class TestPostPRComment:
    """
    REQUIREMENT: Post a new comment thread to a PR.

    WHO: Agents leaving feedback or status updates on PRs.
    WHAT: Creates a new comment thread with specified content and status.
    WHY: Replaces `az rest POST` subprocess.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — context), `ConnectionFactory` (auth),
               `client.git.create_thread` (SDK REST call)
        Real:  tool function, `establish_pr_context`, `post_comment`,
               response formatting
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_content_posts_comment(self, tmp_path: Any) -> None:
        """
        Given valid PR and content
        When post_pr_comment is called
        Then returns thread_id (int)
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns thread with id
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_response = MagicMock()
            mock_response.id = 101
            mock_client.git.create_thread.return_value = mock_response
            mock_ado_client_cls.return_value = mock_client

            # When: post comment
            result = post_pr_comment(
                pr_url_or_id=_PR_URL,
                comment_text="LGTM!",
            )

        # Then: returns thread_id
        assert isinstance(result, int), (
            f"Expected int thread_id, got {type(result).__name__}: {result}"
        )
        assert result == 101, f"Expected thread_id=101, got {result}"

    def test_empty_content_returns_error(self) -> None:
        """
        Given empty content
        When post_pr_comment is called
        Then returns ActionableError (validation)
        """
        # When: called with empty content (no SDK needed — validation first)
        result = post_pr_comment(
            pr_url_or_id=_PR_URL,
            comment_text="",
        )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError for empty content, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure
        When post_pr_comment is called
        Then returns ActionableError
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK raises
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.create_thread.side_effect = Exception("forbidden")
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = post_pr_comment(
                pr_url_or_id=_PR_URL,
                comment_text="LGTM!",
            )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.action_required, (
            "Expected non-empty action_required in ai_guidance"
        )


class TestReplyToPRComment:
    """
    REQUIREMENT: Reply to an existing comment thread.

    WHO: Agents responding to review feedback.
    WHAT: Adds a reply to a specific thread.
    WHY: Replaces `az rest POST .../comments` subprocess.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — context), `ConnectionFactory` (auth),
               `client.git.create_comment` (SDK REST call)
        Real:  tool function, `establish_pr_context`, `reply_to_comment`,
               response formatting
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_reply_returns_comment_id(self, tmp_path: Any) -> None:
        """
        Given valid thread ID and content
        When reply_to_pr_comment is called
        Then returns comment_id (int)
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns comment with id
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_response = MagicMock()
            mock_response.id = 55
            mock_client.git.create_comment.return_value = mock_response
            mock_ado_client_cls.return_value = mock_client

            # When: reply
            result = reply_to_pr_comment(
                pr_url_or_id=_PR_URL,
                thread_id=10,
                comment_text="Done, fixed in latest commit.",
            )

        # Then: returns comment_id
        assert isinstance(result, int), (
            f"Expected int comment_id, got {type(result).__name__}: {result}"
        )
        assert result == 55, f"Expected comment_id=55, got {result}"

    def test_invalid_thread_returns_error(self, tmp_path: Any) -> None:
        """
        Given invalid thread ID
        When reply_to_pr_comment is called
        Then returns ActionableError
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK raises for invalid thread
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.create_comment.side_effect = Exception("Thread 9999 not found")
            mock_ado_client_cls.return_value = mock_client

            # When: called with nonexistent thread
            result = reply_to_pr_comment(
                pr_url_or_id=_PR_URL,
                thread_id=9999,
                comment_text="reply",
            )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.action_required, (
            "Expected non-empty action_required in ai_guidance"
        )

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure
        When reply_to_pr_comment is called
        Then returns ActionableError
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK raises
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.create_comment.side_effect = Exception("timeout")
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = reply_to_pr_comment(
                pr_url_or_id=_PR_URL,
                thread_id=10,
                comment_text="reply",
            )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.action_required, (
            "Expected non-empty action_required in ai_guidance"
        )


class TestResolvePRComments:
    """
    REQUIREMENT: Batch-resolve PR comment threads.

    WHO: Agents that have addressed review feedback.
    WHAT: Sets thread status to "fixed" for a list of thread IDs.
    WHY: Partial-success semantics — doesn't fail the batch on individual errors.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — context), `ConnectionFactory` (auth),
               `client.git.get_threads`, `client.git.update_thread` (SDK REST calls)
        Real:  tool function, `establish_pr_context`, `resolve_comments`,
               partial-success logic, dataclass construction
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_threads_returns_resolve_result(self, tmp_path: Any) -> None:
        """
        Given valid thread IDs
        When resolve_pr_comments is called
        Then returns ResolveResult dataclass
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns threads and update succeeds
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.return_value = [
                _mock_thread(thread_id=1, status="active"),
                _mock_thread(thread_id=2, status="active"),
            ]
            mock_client.git.update_thread.return_value = MagicMock()
            mock_ado_client_cls.return_value = mock_client

            # When: resolve
            result = resolve_pr_comments(
                pr_url_or_id=_PR_URL,
                thread_ids=[1, 2],
            )

        # Then: returns ResolveResult
        assert isinstance(result, ResolveResult), (
            f"Expected ResolveResult, got {type(result).__name__}: {result}"
        )
        assert len(result.resolved) == 2, (
            f"Expected 2 resolved, got {len(result.resolved)}: {result.resolved}"
        )

    def test_already_resolved_threads_are_skipped(self, tmp_path: Any) -> None:
        """
        Given mix of valid and already-resolved threads
        When resolve_pr_comments is called
        Then skipped list is populated
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: thread 1 is active, thread 2 is already fixed
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.return_value = [
                _mock_thread(thread_id=1, status="active"),
                _mock_thread(thread_id=2, status="fixed"),
            ]
            mock_client.git.update_thread.return_value = MagicMock()
            mock_ado_client_cls.return_value = mock_client

            # When: resolve both
            result = resolve_pr_comments(
                pr_url_or_id=_PR_URL,
                thread_ids=[1, 2],
            )

        # Then: thread 2 is skipped
        assert isinstance(result, ResolveResult), (
            f"Expected ResolveResult, got {type(result).__name__}: {result}"
        )
        assert 2 in result.skipped, f"Expected thread 2 in skipped list. Got: {result.skipped}"
        assert 1 in result.resolved, f"Expected thread 1 in resolved list. Got: {result.resolved}"

    def test_all_threads_fail_returns_resolve_result_with_errors(self, tmp_path: Any) -> None:
        """
        Given all threads fail
        When resolve_pr_comments is called
        Then returns ResolveResult with all in failed list
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: update_thread fails for all
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.return_value = [
                _mock_thread(thread_id=1, status="active"),
                _mock_thread(thread_id=2, status="active"),
            ]
            mock_client.git.update_thread.side_effect = Exception("permission denied")
            mock_ado_client_cls.return_value = mock_client

            # When: resolve
            result = resolve_pr_comments(
                pr_url_or_id=_PR_URL,
                thread_ids=[1, 2],
            )

        # Then: all in errors
        assert isinstance(result, ResolveResult), (
            f"Expected ResolveResult, got {type(result).__name__}: {result}"
        )
        assert len(result.errors) == 2, (
            f"Expected 2 errors, got {len(result.errors)}: {result.errors}"
        )
        assert len(result.resolved) == 0, f"Expected 0 resolved, got {len(result.resolved)}"

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure on thread listing
        When resolve_pr_comments is called
        Then returns ActionableError
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: get_threads raises (before any resolution attempts)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_threads.side_effect = Exception("500 error")
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = resolve_pr_comments(
                pr_url_or_id=_PR_URL,
                thread_ids=[1],
            )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.action_required, (
            "Expected non-empty action_required in ai_guidance"
        )
