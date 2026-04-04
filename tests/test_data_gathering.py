"""
BDD tests for tools/data_gathering.py — data gathering MCP tools.

Covers:
    TestListPullRequestsTool — list PRs matching search criteria via MCP
    TestQueryWorkItemsTool — query work items via WIQL and return enriched data
    TestListCommitsTool — list git commits from a local repository via MCP

Public API surface (from src/ado_workflows_mcp/tools/data_gathering.py):
    list_pull_requests(project, *, creator_id, reviewer_id, status,
        repository_id, top, working_directory) -> list[PullRequestSummary] | ActionableError
    query_work_items(project, wiql, *, top, working_directory)
        -> list[WorkItemSummary] | ActionableError
    list_commits(repo_path, *, authors, since, max_count)
        -> list[CommitSummary] | ActionableError

Library API surface (from ado_workflows.listing):
    list_pull_requests(client, project, *, creator_id, reviewer_id, status,
        repository_id, top) -> list[PullRequestSummary]
    query_work_items(client, project, wiql, *, top) -> list[WorkItemSummary]
    list_commits(repo_path, *, authors, since, max_count) -> list[CommitSummary]

I/O boundaries:
    ado_workflows.discovery.Repo (GitPython — context resolution)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_pull_requests / get_pull_requests_by_project (SDK REST)
    client.work_items.query_by_wiql / get_work_items (SDK REST)
    git.Repo (GitPython — commit listing in list_commits)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext
from ado_workflows.models import CommitSummary, PullRequestSummary, WorkItemSummary

from ado_workflows_mcp.tools.data_gathering import (
    list_commits,
    list_pull_requests,
    query_work_items,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_REPO_PATCH = "ado_workflows.discovery.Repo"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"
_LISTING_REPO_PATCH = "ado_workflows.listing.Repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_git_repo(remote_url: str = _ADO_REMOTE) -> MagicMock:
    """Return a mock GitPython Repo with an origin remote for context setup."""
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
    (tmp_path / ".git").mkdir(exist_ok=True)
    with patch(_REPO_PATCH, return_value=_mock_git_repo()):
        RepositoryContext.set(working_directory=str(tmp_path))


def _mock_connection_factory() -> MagicMock:
    """Return a mock ConnectionFactory that produces a mock Connection."""
    factory = MagicMock()
    factory.return_value.get_connection.return_value = MagicMock()
    return factory


def _make_raw_pr(
    pr_id: int = 1,
    title: str = "Fix bug",
    status: str = "active",
) -> MagicMock:
    """Build a mock GitPullRequest matching the SDK shape."""
    pr = MagicMock()
    pr.pull_request_id = pr_id
    pr.title = title
    pr.status = status
    pr.created_by.display_name = "Alice"
    pr.creation_date = "2026-04-01T00:00:00Z"
    pr.source_ref_name = "refs/heads/feature"
    pr.target_ref_name = "refs/heads/main"
    pr.repository.name = "TestRepo"
    pr.repository.web_url = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
    pr.is_draft = False
    pr.merge_status = "succeeded"
    return pr


def _make_raw_work_item(
    wi_id: int = 101,
    title: str = "Task A",
    state: str = "Active",
    work_item_type: str = "Task",
) -> MagicMock:
    """Build a mock WorkItem matching the SDK shape."""
    wi = MagicMock()
    wi.id = wi_id
    wi.fields = {
        "System.Title": title,
        "System.State": state,
        "System.WorkItemType": work_item_type,
        "System.AssignedTo": "Bob",
        "System.IterationPath": r"Proj\Sprint1",
        "Microsoft.VSTS.Scheduling.CompletedWork": 4.0,
        "Microsoft.VSTS.Scheduling.RemainingWork": 2.0,
    }
    wi.url = f"https://dev.azure.com/TestOrg/TestProject/_apis/wit/workItems/{wi_id}"
    return wi


# ---------------------------------------------------------------------------
# TestListPullRequestsTool
# ---------------------------------------------------------------------------


class TestListPullRequestsTool:
    """
    REQUIREMENT: List pull requests matching search criteria via MCP.

    WHO: AI agents querying PR data for reporting or dashboards.
    WHAT: (1) Given a project with active PRs matching the criteria, the tool
              returns a list of PullRequestSummary with pr_id, title, status,
              web_url, and other fields populated
          (2) Given a working_directory pointing at a valid ADO repo, the tool
              resolves the ADO connection without requiring an explicit org_url
          (3) Given an ADO service error (auth failure, network), the tool
              returns an ActionableError instead of raising
          (4) Given an unexpected internal error, the tool returns an
              ActionableError with ai_guidance for the agent
          (5) Given no matching PRs, the tool returns an empty list (not an error)
    WHY: Enables MCP clients to search PRs by creator, reviewer, or
         status without managing ADO authentication or SDK details.

    MOCK BOUNDARY:
        Mock:  git.Repo (GitPython — context), ConnectionFactory (auth),
               SDK REST methods (get_pull_requests, get_pull_requests_by_project)
        Real:  tool function, get_client(), library list_pull_requests(),
               model mapping, tmp_path filesystem
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_matching_prs_returns_summary_list(self, tmp_path: Any) -> None:
        """
        Given a project with active PRs
        When list_pull_requests is called
        Then returns a list of PullRequestSummary with fields populated
        """
        # Given: context set, SDK returns PRs
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.git.get_pull_requests_by_project.return_value = [
                _make_raw_pr(pr_id=10, title="PR Alpha"),
                _make_raw_pr(pr_id=20, title="PR Beta"),
            ]
            mock_client_cls.return_value = mock_client

            # When: tool is called
            result = list_pull_requests(project="TestProject")

        # Then: returns list of PullRequestSummary
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 2, f"Expected 2 PRs, got {len(result)}"
        assert all(isinstance(pr, PullRequestSummary) for pr in result), (
            f"Expected all PullRequestSummary, got types: {[type(r).__name__ for r in result]}"
        )
        assert result[0].pr_id == 10, f"Expected pr_id=10, got {result[0].pr_id}"
        assert result[0].title == "PR Alpha", f"Expected title 'PR Alpha', got '{result[0].title}'"
        assert "pullrequest/10" in result[0].web_url, (
            f"Expected web_url to contain pullrequest/10, got '{result[0].web_url}'"
        )

    def test_working_directory_resolves_connection(self, tmp_path: Any) -> None:
        """
        Given a working_directory pointing at a valid ADO repo
        When list_pull_requests is called with working_directory
        Then resolves the ADO connection and returns results
        """
        # Given: context NOT pre-set, working_directory provided
        (tmp_path / ".git").mkdir(exist_ok=True)

        mock_factory = _mock_connection_factory()
        with (
            patch(_REPO_PATCH, return_value=_mock_git_repo()),
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.git.get_pull_requests_by_project.return_value = [
                _make_raw_pr(),
            ]
            mock_client_cls.return_value = mock_client

            # When: called with working_directory
            result = list_pull_requests(
                project="TestProject",
                working_directory=str(tmp_path),
            )

        # Then: resolves connection and returns results
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 PR, got {len(result)}"

    def test_ado_service_error_returns_actionable_error(self, tmp_path: Any) -> None:
        """
        Given an ADO service error during SDK call
        When list_pull_requests is called
        Then returns ActionableError instead of raising
        """
        # Given: context set, SDK raises
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.git.get_pull_requests_by_project.side_effect = Exception(
                "Service unavailable",
            )
            mock_client_cls.return_value = mock_client

            # When: tool is called
            result = list_pull_requests(project="TestProject")

        # Then: returns ActionableError (not raised)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert "Service unavailable" in result.error, (
            f"Expected error message to contain cause, got: {result.error}"
        )

    def test_unexpected_internal_error_returns_actionable_error_with_guidance(
        self,
        tmp_path: Any,
    ) -> None:
        """
        Given an unexpected internal error (not an ActionableError)
        When list_pull_requests is called
        Then returns ActionableError with ai_guidance
        """
        # Given: context set, ConnectionFactory itself crashes
        _setup_context(tmp_path)

        mock_factory = MagicMock()
        mock_factory.return_value.get_connection.side_effect = RuntimeError(
            "credential store corrupt",
        )
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            # When: tool is called
            result = list_pull_requests(project="TestProject")

        # Then: returns ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )

    def test_no_matching_prs_returns_empty_list(self, tmp_path: Any) -> None:
        """
        Given no PRs match the criteria
        When list_pull_requests is called
        Then returns an empty list (not an error)
        """
        # Given: context set, SDK returns empty
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.git.get_pull_requests_by_project.return_value = []
            mock_client_cls.return_value = mock_client

            # When: tool is called
            result = list_pull_requests(project="TestProject")

        # Then: returns empty list
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 0, f"Expected empty list, got {len(result)} items"


# ---------------------------------------------------------------------------
# TestQueryWorkItemsTool
# ---------------------------------------------------------------------------


class TestQueryWorkItemsTool:
    """
    REQUIREMENT: Query work items via WIQL and return enriched data via MCP.

    WHO: AI agents building sprint dashboards or querying task status.
    WHAT: (1) Given a valid WIQL query and project, the tool returns a list of
              WorkItemSummary with id, title, state, work_item_type, and effort
              tracking fields
          (2) Given a working_directory pointing at a valid ADO repo, the tool
              resolves the ADO connection without requiring an explicit org_url
          (3) Given an ADO service error, the tool returns an ActionableError
              instead of raising
          (4) Given an unexpected internal error, the tool returns an
              ActionableError with ai_guidance
          (5) Given a WIQL query with zero results, the tool returns an empty list
    WHY: Enables MCP clients to run WIQL queries with enriched field
         data without managing ADO auth, SDK calls, or batch-fetch logic.

    MOCK BOUNDARY:
        Mock:  git.Repo (GitPython — context), ConnectionFactory (auth),
               SDK REST methods (query_by_wiql, get_work_items)
        Real:  tool function, get_client(), library query_work_items(),
               model mapping, tmp_path filesystem
        Never: FastMCP framework
    """

    _WIQL = "SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'Active'"

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_matching_work_items_returns_summary_list(self, tmp_path: Any) -> None:
        """
        Given a valid WIQL query returning work items
        When query_work_items is called
        Then returns a list of WorkItemSummary with fields populated
        """
        # Given: context set, SDK returns WIQL results + work items
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()

            # WIQL result with work item references
            wi_ref_1 = MagicMock()
            wi_ref_1.id = 101
            wi_ref_2 = MagicMock()
            wi_ref_2.id = 102
            query_result = MagicMock()
            query_result.work_items = [wi_ref_1, wi_ref_2]
            mock_client.work_items.query_by_wiql.return_value = query_result

            # Batch fetch returns full work items
            mock_client.work_items.get_work_items.return_value = [
                _make_raw_work_item(wi_id=101, title="Task A"),
                _make_raw_work_item(wi_id=102, title="Task B"),
            ]
            mock_client_cls.return_value = mock_client

            # When: tool is called
            result = query_work_items(project="TestProject", wiql=self._WIQL)

        # Then: returns list of WorkItemSummary
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 2, f"Expected 2 work items, got {len(result)}"
        assert all(isinstance(wi, WorkItemSummary) for wi in result), (
            f"Expected all WorkItemSummary, got types: {[type(r).__name__ for r in result]}"
        )
        assert result[0].id == 101, f"Expected id=101, got {result[0].id}"
        assert result[0].title == "Task A", f"Expected title 'Task A', got '{result[0].title}'"
        assert result[0].state == "Active", f"Expected state 'Active', got '{result[0].state}'"
        assert result[0].completed_work == 4.0, (
            f"Expected completed_work=4.0, got {result[0].completed_work}"
        )

    def test_working_directory_resolves_connection(self, tmp_path: Any) -> None:
        """
        Given a working_directory pointing at a valid ADO repo
        When query_work_items is called with working_directory
        Then resolves the ADO connection and returns results
        """
        # Given: context NOT pre-set, working_directory provided
        (tmp_path / ".git").mkdir(exist_ok=True)

        mock_factory = _mock_connection_factory()
        with (
            patch(_REPO_PATCH, return_value=_mock_git_repo()),
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            query_result = MagicMock()
            query_result.work_items = []
            mock_client.work_items.query_by_wiql.return_value = query_result
            mock_client_cls.return_value = mock_client

            # When: called with working_directory
            result = query_work_items(
                project="TestProject",
                wiql=self._WIQL,
                working_directory=str(tmp_path),
            )

        # Then: resolves connection and returns results
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"

    def test_ado_service_error_returns_actionable_error(self, tmp_path: Any) -> None:
        """
        Given an ADO service error during SDK call
        When query_work_items is called
        Then returns ActionableError instead of raising
        """
        # Given: context set, SDK raises
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.work_items.query_by_wiql.side_effect = Exception(
                "WIQL syntax error",
            )
            mock_client_cls.return_value = mock_client

            # When: tool is called
            result = query_work_items(project="TestProject", wiql="invalid wiql")

        # Then: returns ActionableError (not raised)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert "WIQL syntax error" in result.error, (
            f"Expected error message to contain cause, got: {result.error}"
        )

    def test_unexpected_internal_error_returns_actionable_error_with_guidance(
        self,
        tmp_path: Any,
    ) -> None:
        """
        Given an unexpected internal error (not an ActionableError)
        When query_work_items is called
        Then returns ActionableError with ai_guidance
        """
        # Given: context set, ConnectionFactory crashes
        _setup_context(tmp_path)

        mock_factory = MagicMock()
        mock_factory.return_value.get_connection.side_effect = RuntimeError(
            "auth backend timeout",
        )
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            # When: tool is called
            result = query_work_items(project="TestProject", wiql=self._WIQL)

        # Then: returns ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )

    def test_zero_results_returns_empty_list(self, tmp_path: Any) -> None:
        """
        Given a WIQL query with zero results
        When query_work_items is called
        Then returns an empty list (not an error)
        """
        # Given: context set, WIQL returns no IDs
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client = MagicMock()
            query_result = MagicMock()
            query_result.work_items = []
            mock_client.work_items.query_by_wiql.return_value = query_result
            mock_client_cls.return_value = mock_client

            # When: tool is called
            result = query_work_items(project="TestProject", wiql=self._WIQL)

        # Then: returns empty list
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 0, f"Expected empty list for WIQL, got {len(result)} items"


# ---------------------------------------------------------------------------
# TestListCommitsTool
# ---------------------------------------------------------------------------


class TestListCommitsTool:
    """
    REQUIREMENT: List git commits from a local repository via MCP.

    WHO: AI agents querying commit history for activity reports.
    WHAT: (1) Given a valid local repo path with commits, the tool returns a
              list of CommitSummary with sha, message, author, date, repo_name
          (2) The tool operates on a local path directly — no ADO connection
              or working_directory context is needed
          (3) Given an invalid repo path, the tool returns an ActionableError
              instead of raising
          (4) Given an unexpected internal error, the tool returns an
              ActionableError with ai_guidance
          (5) Given no matching commits (empty filter result), the tool returns
              an empty list
    WHY: Enables MCP clients to query local git history without
         managing GitPython directly.

    MOCK BOUNDARY:
        Mock:  git.Repo (GitPython — filesystem/git I/O)
        Real:  tool function, library list_commits(), model mapping
        Never: ADO client or connection (not used by this tool)
    """

    def _make_mock_commit(
        self,
        sha: str = "abc123",
        message: str = "fix: patch",
        author: str = "Alice",
        date: int = 1712188800,
    ) -> MagicMock:
        """Build a mock GitPython Commit."""
        commit = MagicMock()
        commit.hexsha = sha
        commit.message = message
        commit.author.name = author
        commit.committed_date = date
        return commit

    def test_valid_repo_returns_commit_summaries(self) -> None:
        """
        Given a valid local repo path with commits
        When list_commits is called
        Then returns a list of CommitSummary with fields populated
        """
        # Given: mock Repo with commits
        mock_repo = MagicMock()
        mock_repo.iter_commits.return_value = [
            self._make_mock_commit(sha="aaa111", message="feat: add feature", date=1712188800),
            self._make_mock_commit(sha="bbb222", message="fix: bug fix", date=1712102400),
        ]

        with patch(_LISTING_REPO_PATCH, return_value=mock_repo):
            # When: tool is called
            result = list_commits(repo_path="/workspace/my-repo")

        # Then: returns list of CommitSummary
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 2, f"Expected 2 commits, got {len(result)}"
        assert all(isinstance(c, CommitSummary) for c in result), (
            f"Expected all CommitSummary, got: {[type(c).__name__ for c in result]}"
        )
        assert result[0].sha == "aaa111", f"Expected sha='aaa111', got '{result[0].sha}'"
        assert result[0].message == "feat: add feature", (
            f"Expected message 'feat: add feature', got '{result[0].message}'"
        )
        assert result[0].repo_name == "my-repo", (
            f"Expected repo_name='my-repo', got '{result[0].repo_name}'"
        )

    def test_no_ado_connection_needed(self) -> None:
        """
        Given a valid repo path
        When list_commits is called
        Then operates without any ADO connection or working_directory context
        """
        # Given: no context set, mock Repo returns empty
        RepositoryContext.clear()
        mock_repo = MagicMock()
        mock_repo.iter_commits.return_value = []

        with patch(_LISTING_REPO_PATCH, return_value=mock_repo):
            # When: called without context — no connection needed
            result = list_commits(repo_path="/workspace/standalone-repo")

        # Then: returns result without error
        assert isinstance(result, list), (
            f"Expected list (no ADO needed), got {type(result).__name__}: {result}"
        )

    def test_invalid_repo_path_returns_actionable_error(self) -> None:
        """
        Given an invalid repo path
        When list_commits is called
        Then returns ActionableError instead of raising
        """
        # Given: Repo() raises for bad path
        with patch(_LISTING_REPO_PATCH, side_effect=Exception("not a git repo")):
            # When: tool is called
            result = list_commits(repo_path="/nonexistent/path")

        # Then: returns ActionableError (not raised)
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert "not a git repo" in result.error, (
            f"Expected error message to contain cause, got: {result.error}"
        )

    def test_unexpected_internal_error_returns_actionable_error_with_guidance(
        self,
    ) -> None:
        """
        Given an unexpected internal error (not an ActionableError)
        When list_commits is called
        Then returns ActionableError with ai_guidance
        """
        # Given: Repo is valid but iter_commits raises unexpectedly
        mock_repo = MagicMock()
        mock_repo.iter_commits.side_effect = RuntimeError("corrupt index")

        with patch(_LISTING_REPO_PATCH, return_value=mock_repo):
            # When: tool is called
            result = list_commits(repo_path="/workspace/broken-repo")

        # Then: returns ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )

    def test_no_matching_commits_returns_empty_list(self) -> None:
        """
        Given no commits match the filter criteria
        When list_commits is called
        Then returns an empty list
        """
        # Given: Repo returns no commits
        mock_repo = MagicMock()
        mock_repo.iter_commits.return_value = []

        with patch(_LISTING_REPO_PATCH, return_value=mock_repo):
            # When: tool is called with filter
            result = list_commits(
                repo_path="/workspace/my-repo",
                authors=["nobody@example.com"],
                since="2099-01-01",
            )

        # Then: returns empty list
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 0, f"Expected empty list for commits, got {len(result)} items"
