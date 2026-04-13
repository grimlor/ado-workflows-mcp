"""
BDD tests for tools/pr_lifecycle.py — PR lifecycle MCP tools.

Covers:
- TestGetPullRequest: retrieve full PR metadata
- TestUpdatePullRequest: edit title and/or description
- TestRetargetPullRequest: change target branch
- TestSetPRDraftStatus: toggle draft/published state
- TestAbandonPullRequest: close without merging
- TestCompletePullRequest: merge with configurable strategy
- TestAddPRReviewer: add reviewer to PR
- TestRemovePRReviewer: remove reviewer from PR
- TestListPRReviewers: list reviewers with votes
- TestAddPRLabel: add label to PR
- TestRemovePRLabel: remove label from PR
- TestListPRLabels: list all labels
- TestGetPRWorkItems: list linked work items

Public API surface (from src/ado_workflows_mcp/tools/pr_lifecycle.py):
    get_pull_request(pr_url_or_id, working_directory?) -> PullRequestDetail | ActionableError
    update_pull_request(pr_url_or_id, title?, description?, working_directory?)
        -> PullRequestDetail | ActionableError
    retarget_pull_request(pr_url_or_id, target_branch, working_directory?)
        -> PullRequestDetail | ActionableError
    set_pr_draft_status(pr_url_or_id, is_draft, working_directory?)
        -> PullRequestDetail | ActionableError
    abandon_pull_request(pr_url_or_id, working_directory?)
        -> PullRequestDetail | ActionableError
    complete_pull_request(pr_url_or_id, merge_strategy?, ..., working_directory?)
        -> PullRequestDetail | ActionableError
    add_pr_reviewer(pr_url_or_id, reviewer_id, is_required?, working_directory?)
        -> ReviewerDetail | ActionableError
    remove_pr_reviewer(pr_url_or_id, reviewer_id, working_directory?)
        -> str | ActionableError
    list_pr_reviewers(pr_url_or_id, working_directory?)
        -> list[ReviewerDetail] | ActionableError
    add_pr_label(pr_url_or_id, name, working_directory?)
        -> LabelDetail | ActionableError
    remove_pr_label(pr_url_or_id, label_name, working_directory?)
        -> str | ActionableError
    list_pr_labels(pr_url_or_id, working_directory?)
        -> list[LabelDetail] | ActionableError
    get_pr_work_items(pr_url_or_id, working_directory?)
        -> list[WorkItemRef] | ActionableError

I/O boundaries:
    ado_workflows.discovery.Repo (GitPython)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_pull_request_by_id, client.git.update_pull_request,
    client.git.create_pull_request_reviewer, client.git.delete_pull_request_reviewer,
    client.git.get_pull_request_reviewers, client.git.create_pull_request_label,
    client.git.delete_pull_request_labels, client.git.get_pull_request_labels,
    client.git.get_pull_request_work_item_refs (SDK REST calls)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.models import (
    LabelDetail,
    PullRequestDetail,
    ReviewerDetail,
)

from ado_workflows_mcp.tools.pr_lifecycle import (
    abandon_pull_request,
    add_pr_label,
    add_pr_reviewer,
    complete_pull_request,
    get_pr_work_items,
    get_pull_request,
    list_pr_labels,
    list_pr_reviewers,
    remove_pr_label,
    remove_pr_reviewer,
    retarget_pull_request,
    set_pr_draft_status,
    update_pull_request,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PR_URL = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo/pullrequest/42"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"
_ESTABLISH_PR_PATCH = "ado_workflows_mcp.tools.pr_lifecycle._lib_establish_pr"


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
# TestGetPullRequest
# ---------------------------------------------------------------------------


class TestGetPullRequest:
    """
    REQUIREMENT: Retrieve full PR metadata via MCP tool.

    WHO: Agents needing PR details
    WHAT: (1) a valid PR URL returns PullRequestDetail
          (2) an SDK failure returns ActionableError with ai_guidance
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing get_pull_request to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.get_pull_request_by_id
        Real:  MCP tool function, PR context resolution from URL
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_pr_url_returns_detail(self, mock_cf: MagicMock, mock_ac: MagicMock) -> None:
        """
        Given a valid PR URL
        When get_pull_request is called
        Then returns PullRequestDetail
        """
        # Given: SDK returns a PR
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Test PR"
        sdk_pr.description = "desc"
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "active"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.get_pull_request_by_id.return_value = sdk_pr

        # When
        result = get_pull_request(pr_url_or_id=_PR_URL)

        # Then
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When get_pull_request is called
        Then returns ActionableError with ai_guidance
        """
        # When
        result = get_pull_request(pr_url_or_id="not-a-url")

        # Then
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When get_pull_request is called
        Then returns the error with original ai_guidance preserved
        """
        result = get_pull_request(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance preserved, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception at the SDK boundary
        When get_pull_request is called
        Then returns ActionableError.internal with ai_guidance
        """
        # When
        result = get_pull_request(pr_url_or_id=_PR_URL)

        # Then
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on internal error, got None"


# ---------------------------------------------------------------------------
# TestUpdatePullRequest
# ---------------------------------------------------------------------------


class TestUpdatePullRequest:
    """
    REQUIREMENT: Update PR title/description via MCP tool.

    WHO: Agents managing PR metadata
    WHAT: (1) a valid PR URL with title returns PullRequestDetail
          (2) an SDK failure returns ActionableError with ai_guidance
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing update_pull_request to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.update_pull_request
        Real:  MCP tool function, PR context resolution from URL
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_update_returns_detail(self, mock_cf: MagicMock, mock_ac: MagicMock) -> None:
        """
        Given a valid PR URL and new title
        When update_pull_request is called
        Then returns PullRequestDetail
        """
        # Given: SDK returns updated PR
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "New Title"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "active"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr

        # When
        result = update_pull_request(pr_url_or_id=_PR_URL, title="New Title")

        # Then
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When update_pull_request is called
        Then returns ActionableError with ai_guidance
        """
        # When
        result = update_pull_request(pr_url_or_id="bad", title="X")

        # Then
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on error"

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When update_pull_request is called
        Then returns the error with original ai_guidance preserved
        """
        result = update_pull_request(pr_url_or_id=_PR_URL, title="X")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When update_pull_request is called
        Then returns ActionableError.internal
        """
        result = update_pull_request(pr_url_or_id=_PR_URL, title="X")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestRetargetPullRequest
# ---------------------------------------------------------------------------


class TestRetargetPullRequest:
    """
    REQUIREMENT: Retarget a PR via MCP tool.

    WHO: Agents managing branch targets
    WHAT: (1) a valid PR URL returns PullRequestDetail with new target
          (2) an SDK failure returns ActionableError with ai_guidance
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing retarget_pull_request to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.update_pull_request
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_retarget_returns_detail(self, mock_cf: MagicMock, mock_ac: MagicMock) -> None:
        """
        Given a valid PR URL and target branch
        When retarget_pull_request is called
        Then returns PullRequestDetail
        """
        # Given
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Test"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/develop"
        sdk_pr.status = "active"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr

        # When
        result = retarget_pull_request(pr_url_or_id=_PR_URL, target_branch="develop")

        # Then
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When retarget_pull_request is called
        Then returns ActionableError
        """
        result = retarget_pull_request(pr_url_or_id="bad", target_branch="develop")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When retarget_pull_request is called
        Then returns the error with original ai_guidance preserved
        """
        result = retarget_pull_request(pr_url_or_id=_PR_URL, target_branch="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When retarget_pull_request is called
        Then returns ActionableError.internal
        """
        result = retarget_pull_request(pr_url_or_id=_PR_URL, target_branch="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestSetPRDraftStatus
# ---------------------------------------------------------------------------


class TestSetPRDraftStatus:
    """
    REQUIREMENT: Toggle PR draft status via MCP tool.

    WHO: Agents managing PR lifecycle
    WHAT: (1) a valid PR URL returns PullRequestDetail
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing set_draft_status to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.update_pull_request
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_draft_toggle_returns_detail(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL
        When set_pr_draft_status is called
        Then returns PullRequestDetail
        """
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Test"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "active"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr

        result = set_pr_draft_status(pr_url_or_id=_PR_URL, is_draft=False)
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When set_pr_draft_status is called
        Then returns ActionableError
        """
        result = set_pr_draft_status(pr_url_or_id="bad", is_draft=False)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When set_pr_draft_status is called
        Then returns the error with original ai_guidance preserved
        """
        result = set_pr_draft_status(pr_url_or_id=_PR_URL, is_draft=False)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When set_pr_draft_status is called
        Then returns ActionableError.internal
        """
        result = set_pr_draft_status(pr_url_or_id=_PR_URL, is_draft=False)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestAbandonPullRequest
# ---------------------------------------------------------------------------


class TestAbandonPullRequest:
    """
    REQUIREMENT: Abandon a PR via MCP tool.

    WHO: Agents cleaning up PRs
    WHAT: (1) a valid PR URL returns PullRequestDetail with status abandoned
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing abandon_pull_request to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.update_pull_request
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_abandon_returns_detail(self, mock_cf: MagicMock, mock_ac: MagicMock) -> None:
        """
        Given a valid PR URL
        When abandon_pull_request is called
        Then returns PullRequestDetail
        """
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Test"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "abandoned"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr

        result = abandon_pull_request(pr_url_or_id=_PR_URL)
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When abandon_pull_request is called
        Then returns ActionableError
        """
        result = abandon_pull_request(pr_url_or_id="bad")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When abandon_pull_request is called
        Then returns the error with original ai_guidance preserved
        """
        result = abandon_pull_request(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When abandon_pull_request is called
        Then returns ActionableError.internal
        """
        result = abandon_pull_request(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestCompletePullRequest
# ---------------------------------------------------------------------------


class TestCompletePullRequest:
    """
    REQUIREMENT: Complete (merge) a PR via MCP tool.

    WHO: Agents automating merge workflows
    WHAT: (1) a valid PR URL with squash strategy returns PullRequestDetail
          (2) an invalid merge_strategy string returns ActionableError
          (3) an SDK failure returns ActionableError
          (4) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper with string-to-enum coercion

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.update_pull_request
        Real:  MCP tool function, MergeStrategy coercion, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_complete_returns_detail(self, mock_cf: MagicMock, mock_ac: MagicMock) -> None:
        """
        Given a valid PR URL and squash strategy
        When complete_pull_request is called
        Then returns PullRequestDetail
        """
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Test"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "completed"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr

        result = complete_pull_request(pr_url_or_id=_PR_URL, merge_strategy="squash")
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_merge_strategy_returns_actionable_error(self) -> None:
        """
        Given an invalid merge_strategy string
        When complete_pull_request is called
        Then returns ActionableError listing valid strategies
        """
        result = complete_pull_request(pr_url_or_id=_PR_URL, merge_strategy="invalid")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When complete_pull_request is called
        Then returns ActionableError
        """
        result = complete_pull_request(pr_url_or_id="bad")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When complete_pull_request is called
        Then returns the error with original ai_guidance preserved
        """
        result = complete_pull_request(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When complete_pull_request is called
        Then returns ActionableError.internal
        """
        result = complete_pull_request(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestAddPRReviewer
# ---------------------------------------------------------------------------


class TestAddPRReviewer:
    """
    REQUIREMENT: Add reviewer to PR via MCP tool.

    WHO: Agents managing review assignments
    WHAT: (1) a valid PR URL returns ReviewerDetail
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing add_reviewer to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.create_pull_request_reviewer
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_add_returns_reviewer_detail(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL and reviewer ID
        When add_pr_reviewer is called
        Then returns ReviewerDetail
        """
        sdk_reviewer = MagicMock()
        sdk_reviewer.id = "guid-1"
        sdk_reviewer.display_name = "Bob"
        sdk_reviewer.unique_name = "bob@example.com"
        sdk_reviewer.vote = 0
        sdk_reviewer.is_required = False
        sdk_reviewer.is_container = False
        mock_ac.return_value.git.create_pull_request_reviewer.return_value = sdk_reviewer

        result = add_pr_reviewer(pr_url_or_id=_PR_URL, reviewer_id="guid-1")
        assert isinstance(result, ReviewerDetail), (
            f"Expected ReviewerDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When add_pr_reviewer is called
        Then returns ActionableError
        """
        result = add_pr_reviewer(pr_url_or_id="bad", reviewer_id="guid-1")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When add_pr_reviewer is called
        Then returns the error with original ai_guidance preserved
        """
        result = add_pr_reviewer(pr_url_or_id=_PR_URL, reviewer_id="guid-1")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When add_pr_reviewer is called
        Then returns ActionableError.internal
        """
        result = add_pr_reviewer(pr_url_or_id=_PR_URL, reviewer_id="guid-1")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestRemovePRReviewer
# ---------------------------------------------------------------------------


class TestRemovePRReviewer:
    """
    REQUIREMENT: Remove reviewer from PR via MCP tool.

    WHO: Agents managing review assignments
    WHAT: (1) a valid PR URL returns success message
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing remove_reviewer to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.delete_pull_request_reviewer
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_remove_returns_confirmation(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL and reviewer ID
        When remove_pr_reviewer is called
        Then returns success string
        """
        mock_ac.return_value.git.delete_pull_request_reviewer.return_value = None

        result = remove_pr_reviewer(pr_url_or_id=_PR_URL, reviewer_id="guid-1")
        assert isinstance(result, str), f"Expected str, got {type(result).__name__}: {result}"
        assert "guid-1" in result, f"Expected reviewer ID in message, got: {result}"

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When remove_pr_reviewer is called
        Then returns ActionableError
        """
        result = remove_pr_reviewer(pr_url_or_id="bad", reviewer_id="guid-1")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When remove_pr_reviewer is called
        Then returns the error with original ai_guidance preserved
        """
        result = remove_pr_reviewer(pr_url_or_id=_PR_URL, reviewer_id="guid-1")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When remove_pr_reviewer is called
        Then returns ActionableError.internal
        """
        result = remove_pr_reviewer(pr_url_or_id=_PR_URL, reviewer_id="guid-1")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestListPRReviewers
# ---------------------------------------------------------------------------


class TestListPRReviewers:
    """
    REQUIREMENT: List PR reviewers via MCP tool.

    WHO: Agents needing reviewer information
    WHAT: (1) a valid PR URL returns list of ReviewerDetail
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing list_reviewers to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.get_pull_request_reviewers
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_list_returns_reviewer_details(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL
        When list_pr_reviewers is called
        Then returns list of ReviewerDetail
        """
        r1 = MagicMock()
        r1.id = "g1"
        r1.display_name = "Alice"
        r1.unique_name = "alice@example.com"
        r1.vote = 10
        r1.is_required = False
        r1.is_container = False
        mock_ac.return_value.git.get_pull_request_reviewers.return_value = [r1]

        result = list_pr_reviewers(pr_url_or_id=_PR_URL)
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 reviewer, got {len(result)}"

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When list_pr_reviewers is called
        Then returns ActionableError
        """
        result = list_pr_reviewers(pr_url_or_id="bad")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When list_pr_reviewers is called
        Then returns the error with original ai_guidance preserved
        """
        result = list_pr_reviewers(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When list_pr_reviewers is called
        Then returns ActionableError.internal
        """
        result = list_pr_reviewers(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestAddPRLabel
# ---------------------------------------------------------------------------


class TestAddPRLabel:
    """
    REQUIREMENT: Add label to PR via MCP tool.

    WHO: Agents categorizing PRs
    WHAT: (1) a valid PR URL returns LabelDetail
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing add_label to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.create_pull_request_label
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_add_returns_label_detail(self, mock_cf: MagicMock, mock_ac: MagicMock) -> None:
        """
        Given a valid PR URL and label name
        When add_pr_label is called
        Then returns LabelDetail
        """
        sdk_label = MagicMock()
        sdk_label.id = "label-1"
        sdk_label.name = "priority"
        mock_ac.return_value.git.create_pull_request_label.return_value = sdk_label

        result = add_pr_label(pr_url_or_id=_PR_URL, name="priority")
        assert isinstance(result, LabelDetail), (
            f"Expected LabelDetail, got {type(result).__name__}: {result}"
        )

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When add_pr_label is called
        Then returns ActionableError
        """
        result = add_pr_label(pr_url_or_id="bad", name="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When add_pr_label is called
        Then returns the error with original ai_guidance preserved
        """
        result = add_pr_label(pr_url_or_id=_PR_URL, name="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When add_pr_label is called
        Then returns ActionableError.internal
        """
        result = add_pr_label(pr_url_or_id=_PR_URL, name="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestRemovePRLabel
# ---------------------------------------------------------------------------


class TestRemovePRLabel:
    """
    REQUIREMENT: Remove label from PR via MCP tool.

    WHO: Agents managing PR categorization
    WHAT: (1) a valid PR URL returns success message
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing remove_label to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.delete_pull_request_labels
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_remove_returns_confirmation(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL and label name
        When remove_pr_label is called
        Then returns success string
        """
        mock_ac.return_value.git.delete_pull_request_labels.return_value = None

        result = remove_pr_label(pr_url_or_id=_PR_URL, label_name="old-tag")
        assert isinstance(result, str), f"Expected str, got {type(result).__name__}: {result}"
        assert "old-tag" in result, f"Expected label name in message, got: {result}"

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When remove_pr_label is called
        Then returns ActionableError
        """
        result = remove_pr_label(pr_url_or_id="bad", label_name="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When remove_pr_label is called
        Then returns the error with original ai_guidance preserved
        """
        result = remove_pr_label(pr_url_or_id=_PR_URL, label_name="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When remove_pr_label is called
        Then returns ActionableError.internal
        """
        result = remove_pr_label(pr_url_or_id=_PR_URL, label_name="x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestListPRLabels
# ---------------------------------------------------------------------------


class TestListPRLabels:
    """
    REQUIREMENT: List PR labels via MCP tool.

    WHO: Agents needing label information
    WHAT: (1) a valid PR URL returns list of LabelDetail
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing list_labels to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.get_pull_request_labels
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_list_returns_label_details(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL
        When list_pr_labels is called
        Then returns list of LabelDetail
        """
        lbl = MagicMock()
        lbl.id = "id-1"
        lbl.name = "bug"
        mock_ac.return_value.git.get_pull_request_labels.return_value = [lbl]

        result = list_pr_labels(pr_url_or_id=_PR_URL)
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 label, got {len(result)}"

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When list_pr_labels is called
        Then returns ActionableError
        """
        result = list_pr_labels(pr_url_or_id="bad")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When list_pr_labels is called
        Then returns the error with original ai_guidance preserved
        """
        result = list_pr_labels(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When list_pr_labels is called
        Then returns ActionableError.internal
        """
        result = list_pr_labels(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestGetPRWorkItems
# ---------------------------------------------------------------------------


class TestGetPRWorkItems:
    """
    REQUIREMENT: List PR work items via MCP tool.

    WHO: Agents cross-referencing PRs and work items
    WHAT: (1) a valid PR URL returns list of WorkItemRef
          (2) an SDK failure returns ActionableError
          (3) an unexpected exception returns ActionableError.internal
    WHY: Thin MCP wrapper exposing get_pr_work_item_refs to agents

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient,
               client.git.get_pull_request_work_item_refs
        Real:  MCP tool function, PR context resolution
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_valid_list_returns_work_item_refs(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given a valid PR URL
        When get_pr_work_items is called
        Then returns list of WorkItemRef
        """
        wi = MagicMock()
        wi.id = "100"
        wi.url = "https://dev.azure.com/Org/_apis/wit/workItems/100"
        mock_ac.return_value.git.get_pull_request_work_item_refs.return_value = [wi]

        result = get_pr_work_items(pr_url_or_id=_PR_URL)
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 work item, got {len(result)}"

    def test_invalid_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When get_pr_work_items is called
        Then returns ActionableError
        """
        result = get_pr_work_items(pr_url_or_id="bad")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When get_pr_work_items is called
        Then returns the error with original ai_guidance preserved
        """
        result = get_pr_work_items(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    @patch(_ESTABLISH_PR_PATCH, side_effect=RuntimeError("boom"))
    def test_unexpected_exception_returns_internal_error(self, mock_establish: MagicMock) -> None:
        """
        Given an unexpected exception
        When get_pr_work_items is called
        Then returns ActionableError.internal
        """
        result = get_pr_work_items(pr_url_or_id=_PR_URL)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )


# ---------------------------------------------------------------------------
# TestUpdatePRWithWorkItems
# ---------------------------------------------------------------------------


class TestUpdatePRWithWorkItems:
    """
    REQUIREMENT: update_pull_request passes work_item_ids to the library layer.

    WHO: Agents and automation updating PRs with work item links.
    WHAT: (1) When work_item_ids is provided, they are forwarded to the library
          (2) When work_item_ids is None, behavior is unchanged

    MOCK BOUNDARY:
        Mock:  ConnectionFactory, AdoClient, client.git.update_pull_request,
               client.work_items.update_work_item
        Real:  MCP tool function, PR context resolution from URL
        Never: FastMCP framework
    """

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_work_item_ids_forwarded_to_library(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given work_item_ids=[456]
        When update_pull_request is called
        Then the library receives work_item_ids and links the work item
        """
        # Given: SDK returns updated PR with repository metadata
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Updated"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "active"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        sdk_pr.repository = MagicMock()
        sdk_pr.repository.id = "repo-guid"
        sdk_pr.repository.project = MagicMock()
        sdk_pr.repository.project.id = "proj-guid"
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr
        mock_ac.return_value.work_items.update_work_item.return_value = MagicMock()

        # When: update_pull_request is called with work_item_ids
        result = update_pull_request(
            pr_url_or_id=_PR_URL,
            title="Updated",
            work_item_ids=[456],
        )

        # Then: returns PullRequestDetail
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"
        # Then: work item was linked
        mock_ac.return_value.work_items.update_work_item.assert_called_once()

    @patch(_ADO_CLIENT_PATCH)
    @patch(_CONN_FACTORY_PATCH)
    def test_no_work_item_ids_means_no_wit_calls(
        self, mock_cf: MagicMock, mock_ac: MagicMock
    ) -> None:
        """
        Given work_item_ids is not provided
        When update_pull_request is called
        Then no WIT calls are made
        """
        # Given: SDK returns updated PR
        sdk_pr = MagicMock()
        sdk_pr.pull_request_id = 42
        sdk_pr.title = "Updated"
        sdk_pr.description = None
        sdk_pr.url = _PR_URL
        sdk_pr.source_ref_name = "refs/heads/feature/x"
        sdk_pr.target_ref_name = "refs/heads/main"
        sdk_pr.status = "active"
        sdk_pr.is_draft = False
        sdk_pr.merge_status = "succeeded"
        sdk_pr.creation_date = "2026-03-15T10:00:00Z"
        sdk_pr.created_by = MagicMock(display_name="Alice")
        sdk_pr.reviewers = []
        sdk_pr.labels = []
        sdk_pr.work_item_refs = []
        mock_ac.return_value.git.update_pull_request.return_value = sdk_pr

        # When: called without work_item_ids
        result = update_pull_request(
            pr_url_or_id=_PR_URL,
            title="Updated",
        )

        # Then: returns PullRequestDetail
        assert isinstance(result, PullRequestDetail), (
            f"Expected PullRequestDetail, got {type(result).__name__}: {result}"
        )
        # Then: no WIT calls were made
        mock_ac.return_value.work_items.update_work_item.assert_not_called()
