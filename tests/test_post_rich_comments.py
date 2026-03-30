"""
BDD tests for tools/pr_comments.py — rich comment posting with formatting and praise.

Covers:
- TestPostRichComments: batch-post structured review comments with enum coercion

Public API surface (from src/ado_workflows_mcp/tools/pr_comments.py):
    post_rich_comments(pr_url_or_id, comments, *, dry_run, batch_size,
        filter_self_praise, working_directory)
        -> RichPostingResult | ActionableError

Library API surface:
    ado_workflows.comments.post_rich_comments(client, repository, pr_id,
        comments, project, *, dry_run, batch_size, filter_self_praise, formatter)
        -> RichPostingResult

I/O boundaries:
    ado_workflows.discovery.subprocess.run (git CLI)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.create_thread, client.git.create_comment,
    client.git.get_pull_request_iterations,
    client.git.get_pull_request_iteration_changes (SDK REST calls)
    ado_workflows.auth.get_current_user, ado_workflows.pr.get_pr_author (identity)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext
from ado_workflows.models import RichPostingResult

from ado_workflows_mcp.tools.pr_comments import post_rich_comments

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_PR_URL = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo/pullrequest/42"
_SUBPROCESS_PATCH = "ado_workflows.discovery.subprocess.run"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"
_GET_PR_AUTHOR_PATCH = "ado_workflows.pr.get_pr_author"
_GET_CURRENT_USER_PATCH = "ado_workflows.auth.get_current_user"


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


def _make_comment_dict(
    *,
    comment_id: str = "c1",
    title: str = "Fix null check",
    content: str = "Handle None return value",
    severity: str = "warning",
    comment_type: str = "line",
    file_path: str | None = None,
    line_number: int | None = None,
    parent_thread_id: int | None = None,
) -> dict[str, object]:
    """Build a comment dict matching the MCP tool input schema."""
    d: dict[str, object] = {
        "comment_id": comment_id,
        "title": title,
        "content": content,
        "severity": severity,
        "comment_type": comment_type,
    }
    if file_path is not None:
        d["file_path"] = file_path
    if line_number is not None:
        d["line_number"] = line_number
    if parent_thread_id is not None:
        d["parent_thread_id"] = parent_thread_id
    return d


def _mock_client_for_posting() -> Mock:
    """Return a mock AdoClient wired for comment posting."""
    client = Mock()
    # Iterations (for positioned comments)
    iter_mock = MagicMock()
    iter_mock.id = 1
    iter_mock.created_date = "2026-03-18T00:00:00Z"
    iter_mock.source_ref_commit = MagicMock(commit_id="abc123")
    iter_mock.target_ref_commit = MagicMock(commit_id="def456")
    client.git.get_pull_request_iterations.return_value = [iter_mock]
    # Iteration changes
    changes_response = MagicMock()
    changes_response.change_entries = []
    client.git.get_pull_request_iteration_changes.return_value = changes_response
    # Thread creation
    thread = MagicMock()
    thread.id = 101
    client.git.create_thread.return_value = thread
    return client


# ---------------------------------------------------------------------------
# TestPostRichComments
# ---------------------------------------------------------------------------


class TestPostRichComments:
    """
    REQUIREMENT: An MCP consumer can batch-post structured review comments
    with severity, type, and formatting metadata.

    WHO: AI agents performing code review via MCP.
    WHAT: (1) valid comments with string severity/type are coerced to enums
              and posted successfully
          (2) dry_run=True validates without posting and returns skipped indices
          (3) an invalid severity string returns ActionableError with guidance
          (4) an invalid comment_type string returns ActionableError with guidance
          (5) filter_self_praise=False disables praise filtering
          (6) an SDK exception during posting returns ActionableError.internal
          (7) an ActionableError from the library is enriched with ai_guidance
          (8) an unexpected non-ActionableError returns ActionableError.internal
          (9) optional metadata fields are coerced into the RichComment
          (10) omitting severity/comment_type uses defaults (info/general)
          (11) custom batch_size is forwarded to the library
    WHY: MCP tools receive JSON dicts — string-to-enum coercion at this layer
         prevents invalid data from reaching the library and produces
         structured, actionable errors for AI consumers.

    MOCK BOUNDARY:
        Mock:  subprocess.run (git CLI — context), ConnectionFactory (auth),
               AdoClient (SDK REST calls),
               get_pr_author / get_current_user (identity lookups)
        Real:  tool function, establish_pr_context, dict→RichComment coercion,
               enum validation, post_rich_comments library orchestration,
               RichPostingResult construction
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_valid_comments_coerced_and_posted(self, tmp_path: Any) -> None:
        """
        Given a PR URL and comments with string severity/type values
        When post_rich_comments is called
        Then string values are coerced to enums and comments are posted
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
            patch(_GET_PR_AUTHOR_PATCH, return_value="other@example.com"),
            patch(_GET_CURRENT_USER_PATCH, return_value="me@example.com"),
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()

            # When: post_rich_comments with string enum values
            result = post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    _make_comment_dict(
                        comment_id="c1",
                        title="Fix null check",
                        content="Handle None return",
                        severity="warning",
                        comment_type="general",
                    ),
                    _make_comment_dict(
                        comment_id="c2",
                        title="Add logging",
                        content="Log the response",
                        severity="info",
                        comment_type="suggestion",
                    ),
                ],
            )

        # Then: returns RichPostingResult with successes
        assert isinstance(result, RichPostingResult), (
            f"Expected RichPostingResult, got {type(result).__name__}: {result}"
        )
        assert len(result.posted) == 2, f"Expected 2 posted, got {len(result.posted)}"
        assert len(result.failures) == 0, f"Expected 0 failures, got {len(result.failures)}"

    def test_dry_run_validates_without_posting(self, tmp_path: Any) -> None:
        """
        Given dry_run=True
        When post_rich_comments is called
        Then returns skipped indices without making API calls
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
            patch(_GET_PR_AUTHOR_PATCH, return_value="other@example.com"),
            patch(_GET_CURRENT_USER_PATCH, return_value="me@example.com"),
        ):
            mock_client = _mock_client_for_posting()
            mock_ado_client_cls.return_value = mock_client

            # When: dry_run=True
            result = post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    _make_comment_dict(comment_id="c1"),
                ],
                dry_run=True,
            )

        # Then: no actual posting, skipped indices present
        assert isinstance(result, RichPostingResult), (
            f"Expected RichPostingResult, got {type(result).__name__}: {result}"
        )
        assert result.dry_run is True, "Expected dry_run=True in result"
        assert len(result.posted) == 0, "Expected 0 posted in dry run"
        assert len(result.skipped) == 1, f"Expected 1 skipped, got {len(result.skipped)}"
        # Verify no create_thread calls were made
        mock_client.git.create_thread.assert_not_called()

    def test_invalid_severity_returns_error(self, tmp_path: Any) -> None:
        """
        Given a comment with an invalid severity string
        When post_rich_comments is called
        Then returns ActionableError with guidance listing valid values
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()

            # When: post_rich_comments with invalid severity
            result = post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    _make_comment_dict(severity="catastrophic"),
                ],
            )

        # Then: ActionableError for invalid enum value
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError for invalid severity, got {type(result).__name__}"
        )
        assert "severity" in str(result).lower(), (
            f"Expected 'severity' mentioned in error, got: {result}"
        )

    def test_invalid_comment_type_returns_error(self, tmp_path: Any) -> None:
        """
        Given a comment with an invalid comment_type string
        When post_rich_comments is called
        Then returns ActionableError with guidance listing valid values
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()

            # When: post_rich_comments with invalid comment_type
            result = post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    _make_comment_dict(comment_type="unknown_type"),
                ],
            )

        # Then: ActionableError for invalid enum value
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError for invalid comment_type, got {type(result).__name__}"
        )
        assert "comment_type" in str(result).lower(), (
            f"Expected 'comment_type' mentioned in error, got: {result}"
        )

    def test_filter_self_praise_disabled(self, tmp_path: Any) -> None:
        """
        Given filter_self_praise=False
        When post_rich_comments is called
        Then praise comments are not filtered out
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()

            # When: filter_self_praise=False with a praise-like comment
            result = post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    _make_comment_dict(
                        comment_id="praise1",
                        title="Great work!",
                        content="Excellent implementation",
                        severity="info",
                    ),
                ],
                filter_self_praise=False,
            )

        # Then: comment is posted (not filtered)
        assert isinstance(result, RichPostingResult), (
            f"Expected RichPostingResult, got {type(result).__name__}: {result}"
        )
        assert len(result.posted) == 1, f"Expected 1 posted, got {len(result.posted)}"
        assert len(result.local_praise) == 0, (
            f"Expected 0 local_praise when filtering disabled, got {len(result.local_praise)}"
        )

    def test_optional_metadata_coerced_into_rich_comment(self, tmp_path: Any) -> None:
        """
        Given a comment dict with optional metadata fields populated
        When post_rich_comments is called
        Then suggested_code, reasoning, business_impact, tags, and
             parent_thread_id are coerced into the RichComment
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
            patch(_GET_PR_AUTHOR_PATCH, return_value="other@example.com"),
            patch(_GET_CURRENT_USER_PATCH, return_value="me@example.com"),
            patch(
                "ado_workflows_mcp.tools.pr_comments._lib_post_rich",
            ) as mock_lib,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()
            mock_lib.return_value = RichPostingResult(
                posted=[],
                failures=[],
                skipped=[],
                dry_run=False,
                local_praise=[],
            )

            # When: comment includes all optional metadata
            post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    {
                        "comment_id": "m1",
                        "title": "Refactor",
                        "content": "Extract method",
                        "severity": "suggestion",
                        "comment_type": "suggestion",
                        "file_path": "/src/app.py",
                        "line_number": 42,
                        "suggested_code": "def helper(): ...",
                        "reasoning": "Reduces duplication",
                        "business_impact": "Easier maintenance",
                        "tags": ["refactor", "dry"],
                        "status": "closed",
                        "parent_thread_id": 7,
                    },
                ],
            )

        # Then: library received a RichComment with all metadata
        mock_lib.assert_called_once()
        rich = mock_lib.call_args.kwargs["comments"][0]
        assert rich.suggested_code == "def helper(): ..."
        assert rich.reasoning == "Reduces duplication"
        assert rich.business_impact == "Easier maintenance"
        assert rich.tags == ["refactor", "dry"]
        assert rich.parent_thread_id == 7
        assert rich.file_path == "/src/app.py"
        assert rich.line_number == 42
        assert rich.status == "closed"

    def test_omitted_severity_and_type_use_defaults(self, tmp_path: Any) -> None:
        """
        Given a comment dict without severity or comment_type keys
        When post_rich_comments is called
        Then defaults to severity=info and comment_type=general
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
            patch(_GET_PR_AUTHOR_PATCH, return_value="other@example.com"),
            patch(_GET_CURRENT_USER_PATCH, return_value="me@example.com"),
            patch(
                "ado_workflows_mcp.tools.pr_comments._lib_post_rich",
            ) as mock_lib,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()
            mock_lib.return_value = RichPostingResult(
                posted=[],
                failures=[],
                skipped=[],
                dry_run=False,
                local_praise=[],
            )

            # When: comment dict omits severity and comment_type
            post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    {"comment_id": "d1", "title": "Note", "content": "FYI"},
                ],
            )

        # Then: defaults applied
        from ado_workflows.models import CommentSeverity, CommentType

        rich = mock_lib.call_args.kwargs["comments"][0]
        assert rich.severity is CommentSeverity.INFO, f"Expected INFO default, got {rich.severity}"
        assert rich.comment_type is CommentType.GENERAL, (
            f"Expected GENERAL default, got {rich.comment_type}"
        )

    def test_custom_batch_size_forwarded(self, tmp_path: Any) -> None:
        """
        Given a custom batch_size value
        When post_rich_comments is called
        Then batch_size is forwarded to the library
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
            patch(_GET_PR_AUTHOR_PATCH, return_value="other@example.com"),
            patch(_GET_CURRENT_USER_PATCH, return_value="me@example.com"),
            patch(
                "ado_workflows_mcp.tools.pr_comments._lib_post_rich",
            ) as mock_lib,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()
            mock_lib.return_value = RichPostingResult(
                posted=[],
                failures=[],
                skipped=[],
                dry_run=False,
                local_praise=[],
            )

            # When: batch_size=10
            post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[_make_comment_dict()],
                batch_size=10,
            )

        # Then: library received batch_size=10
        assert mock_lib.call_args.kwargs["batch_size"] == 10, (
            f"Expected batch_size=10, got {mock_lib.call_args.kwargs.get('batch_size')}"
        )

    def test_sdk_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given an SDK exception during posting
        When post_rich_comments is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_ado_client_cls.side_effect = RuntimeError("Connection refused")

            # When: post_rich_comments with failing SDK
            result = post_rich_comments(
                pr_url_or_id=_PR_URL,
                comments=[
                    _make_comment_dict(comment_id="c1"),
                ],
            )

        # Then: ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on error"

    def test_actionable_error_enriched_with_guidance(self, tmp_path: Any) -> None:
        """
        Given the library raises ActionableError without ai_guidance
        When post_rich_comments is called
        Then ai_guidance is added before returning
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            # Simulate ActionableError from establish_pr_context
            mock_ado_client_cls.return_value = _mock_client_for_posting()
            bare_error = ActionableError.not_found(
                service="AzureDevOps",
                resource_type="PullRequest",
                resource_id="999",
                raw_error="Not found",
            )
            with patch(
                "ado_workflows_mcp.tools.pr_comments._lib_establish_pr",
                side_effect=bare_error,
            ):
                # When: post_rich_comments raises bare ActionableError
                result = post_rich_comments(
                    pr_url_or_id="999",
                    comments=[_make_comment_dict()],
                )

        # Then: ai_guidance is enriched
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            "Expected ai_guidance to be enriched on bare ActionableError"
        )

    def test_unexpected_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given an unexpected non-ActionableError exception
        When post_rich_comments is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_ado_client_cls.return_value = _mock_client_for_posting()
            with patch(
                "ado_workflows_mcp.tools.pr_comments._lib_establish_pr",
                side_effect=TypeError("Unexpected type error"),
            ):
                # When: post_rich_comments hits unexpected error
                result = post_rich_comments(
                    pr_url_or_id=_PR_URL,
                    comments=[_make_comment_dict()],
                )

        # Then: ActionableError.internal with guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on internal error"
        assert "post_rich_comments" in str(result), (
            f"Expected operation name in error, got: {result}"
        )
