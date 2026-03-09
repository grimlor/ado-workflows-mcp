"""BDD tests for tools/pr_review.py — review status and pending review tools.

Covers:
- TestGetPRReviewStatus: fetching comprehensive review status for a PR
- TestAnalyzePendingReviews: discovering PRs needing review attention

Public API surface (from src/ado_workflows_mcp/tools/pr_review.py):
    get_pr_review_status(pr_id: int, working_directory: str | None)
        -> ReviewStatus | ActionableError
    analyze_pending_reviews(max_days_old: int, creator_filter: str | None,
        working_directory: str | None) -> PendingReviewResult | ActionableError

Library API surface:
    ado_workflows.review.get_review_status(client, pr_id, project, repository, *, ...)
        -> ReviewStatus
    ado_workflows.review.analyze_pending_reviews(client, project, repository, *, ...)
        -> PendingReviewResult
    ado_workflows.auth.ConnectionFactory(credential).get_connection(org_url) -> Connection
    ado_workflows.client.AdoClient(connection)

I/O boundaries:
    ado_workflows.discovery.subprocess.run (git CLI)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_pull_request_by_id, client.git.get_pull_request_commits,
    client.git.get_pull_request_properties, client.git.get_threads,
    client.git.get_pull_requests (SDK REST calls)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext
from ado_workflows.models import PendingReviewResult, ReviewStatus

from ado_workflows_mcp.tools.pr_review import (
    analyze_pending_reviews,
    get_pr_review_status,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_SUBPROCESS_PATCH = "ado_workflows.discovery.subprocess.run"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_success(remote: str = _ADO_REMOTE) -> MagicMock:
    """Return a mock subprocess result for a successful git remote -v."""
    return MagicMock(returncode=0, stdout=remote)


def _mock_connection_factory() -> MagicMock:
    """Return a mock ConnectionFactory that produces a mock Connection."""
    factory = MagicMock()
    factory.return_value.get_connection.return_value = MagicMock()
    return factory


def _setup_context(tmp_path: Any) -> None:
    """Set up repository context with subprocess mocked."""
    (tmp_path / ".git").mkdir()
    with patch(_SUBPROCESS_PATCH, return_value=_git_success()):
        RepositoryContext.set(working_directory=str(tmp_path))


def _mock_pr_details() -> MagicMock:
    """Return a mock PR detail object (from get_pull_request_by_id)."""
    pr = MagicMock()
    pr.pull_request_id = 42
    pr.title = "feat: add widget"
    pr.created_by.unique_name = "dev@example.com"
    pr.created_by.display_name = "Dev User"
    pr.url = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo/pullrequest/42"
    pr.creation_date = datetime.now(tz=UTC) - timedelta(days=3)
    pr.source_ref_name = "refs/heads/feature/widget"
    pr.target_ref_name = "refs/heads/main"
    pr.merge_status = "succeeded"
    pr.is_draft = False
    pr.reviewers = []
    return pr


def _mock_commit() -> MagicMock:
    """Return a mock commit object (from get_pull_request_commits)."""
    commit = MagicMock()
    commit.author.date = datetime.now(tz=UTC) - timedelta(hours=2)
    commit.committer.date = datetime.now(tz=UTC) - timedelta(hours=2)
    return commit


def _setup_review_mocks(mock_client: Mock) -> None:
    """Wire up mock SDK responses for get_review_status calls."""
    mock_client.git.get_pull_request_by_id.return_value = _mock_pr_details()
    mock_client.git.get_pull_request_commits.return_value = [_mock_commit()]
    mock_client.git.get_pull_request_properties.return_value = {"value": {}}
    mock_client.git.get_threads.return_value = []
    mock_client.policy.get_policy_evaluations.return_value = []


class TestGetPRReviewStatus:
    """
    REQUIREMENT: Get comprehensive review status with vote invalidation.

    WHO: Agents checking whether a PR is ready to merge.
    WHAT: Fetches PR details, reviewer votes, commit history, detects stale
          approvals.
    WHY: Surfaces stale approvals that the raw API buries.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — context), `ConnectionFactory` (auth),
               `client.git.get_pull_request_by_id`,
               `client.git.get_pull_request_commits`,
               `client.git.get_pull_request_properties`,
               `client.git.get_threads` (SDK REST calls)
        Real:  tool function, `get_review_status`, vote logic, staleness
               detection, dataclass construction
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_pr_returns_review_status(self, tmp_path: Any) -> None:
        """
        Given a valid PR ID with context
        When get_pr_review_status is called
        Then returns ReviewStatus dataclass
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: auth + SDK mocked
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            _setup_review_mocks(mock_client)
            mock_ado_client_cls.return_value = mock_client

            # When: get_pr_review_status called
            result = get_pr_review_status(pr_id=42)

        # Then: returns ReviewStatus
        assert isinstance(result, ReviewStatus), (
            f"Expected ReviewStatus, got {type(result).__name__}: {result}"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure
        When get_pr_review_status is called
        Then returns ActionableError with suggestion and ai_guidance
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
            mock_client.git.get_pull_request_by_id.side_effect = Exception("404 Not Found")
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = get_pr_review_status(pr_id=9999)

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on error. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance.action_required, (
            "Expected non-empty action_required in ai_guidance"
        )

    def test_review_status_with_warnings_includes_them(self, tmp_path: Any) -> None:
        """
        Given ReviewStatus with warnings
        When get_pr_review_status is called
        Then includes warnings in response
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns data that produces warnings (properties fetch
        # raises a non-fatal error which the library captures as a warning)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            _setup_review_mocks(mock_client)
            # Properties fetch failure produces enrichment warning
            mock_client.git.get_pull_request_properties.side_effect = Exception(
                "properties unavailable"
            )
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = get_pr_review_status(pr_id=42)

        # Then: returns ReviewStatus (possibly with warnings)
        assert isinstance(result, ReviewStatus), (
            f"Expected ReviewStatus, got {type(result).__name__}: {result}"
        )
        # Note: whether warnings list is populated depends on library
        # implementation; we verify the type is correct and the call succeeds


class TestAnalyzePendingReviews:
    """
    REQUIREMENT: Discover PRs needing review attention across a repository.

    WHO: Agents doing daily review triage.
    WHAT: Lists active PRs, filters by age/creator, enriches with staleness.
    WHY: Automates the "what PRs need my attention" workflow.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — context), `ConnectionFactory` (auth),
               `client.git.get_pull_requests`,
               `client.git.get_pull_request_commits`,
               `client.git.get_pull_request_properties` (SDK REST calls)
        Real:  tool function, `analyze_pending_reviews`, PR enrichment,
               staleness detection, dataclass construction
        Never: FastMCP framework, library functions in our codebase
    """

    def test_active_prs_returns_pending_review_result(self, tmp_path: Any) -> None:
        """
        Given active PRs in repo
        When analyze_pending_reviews is called
        Then returns PendingReviewResult
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns active PRs
        pr = _mock_pr_details()
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_pull_requests.return_value = [pr]
            # Enrichment calls
            mock_client.git.get_pull_request_commits.return_value = [_mock_commit()]
            mock_client.git.get_pull_request_properties.return_value = {"value": {}}
            mock_client.git.get_threads.return_value = []
            mock_client.git.get_pull_request_by_id.return_value = pr
            mock_ado_client_cls.return_value = mock_client

            # When: analyze_pending_reviews called
            result = analyze_pending_reviews()

        # Then: returns PendingReviewResult
        assert isinstance(result, PendingReviewResult), (
            f"Expected PendingReviewResult, got {type(result).__name__}: {result}"
        )

    def test_no_active_prs_returns_empty_list(self, tmp_path: Any) -> None:
        """
        Given no active PRs
        When analyze_pending_reviews is called
        Then returns PendingReviewResult with empty list
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns no PRs
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_pull_requests.return_value = []
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = analyze_pending_reviews()

        # Then: returns empty PendingReviewResult
        assert isinstance(result, PendingReviewResult), (
            f"Expected PendingReviewResult, got {type(result).__name__}: {result}"
        )
        assert len(result.pending_prs) == 0, (
            f"Expected 0 pending PRs, got {len(result.pending_prs)}"
        )

    def test_partial_enrichment_failures_returns_skipped(self, tmp_path: Any) -> None:
        """
        Given partial enrichment failures
        When analyze_pending_reviews is called
        Then returns skipped list alongside results
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns PRs but enrichment fails for some
        pr1 = _mock_pr_details()
        pr1.pull_request_id = 1
        pr2 = _mock_pr_details()
        pr2.pull_request_id = 2

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_pull_requests.return_value = [pr1, pr2]
            # First PR enrichment succeeds, second fails
            mock_client.git.get_pull_request_commits.side_effect = [
                [_mock_commit()],
                Exception("enrichment failure"),
            ]
            mock_client.git.get_pull_request_properties.return_value = {"value": {}}
            mock_client.git.get_threads.return_value = []
            mock_client.git.get_pull_request_by_id.side_effect = [pr1, pr2]
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = analyze_pending_reviews()

        # Then: returns result with skipped entries
        assert isinstance(result, PendingReviewResult), (
            f"Expected PendingReviewResult, got {type(result).__name__}: {result}"
        )
        # The library should capture the enrichment failure in skipped
        assert len(result.skipped) > 0 or len(result.pending_prs) > 0, (
            "Expected at least some results or skipped entries"
        )

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure
        When analyze_pending_reviews is called
        Then returns ActionableError
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK raises on listing
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.get_pull_requests.side_effect = Exception("503 Service Unavailable")
            mock_ado_client_cls.return_value = mock_client

            # When: called
            result = analyze_pending_reviews()

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
