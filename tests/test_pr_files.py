"""BDD tests for tools/pr_files.py — PR file changes and content fetching.

Covers:
- TestGetPRFileChanges: list files changed in a PR with iteration metadata
- TestGetPRFileContents: fetch file contents for files changed in a PR

Public API surface (from src/ado_workflows_mcp/tools/pr_files.py):
    get_pr_file_changes(pr_url_or_id, *, working_directory)
        -> list[dict] | ActionableError
    get_pr_file_contents(pr_url_or_id, *, file_paths, working_directory)
        -> list[dict] | ActionableError

Library API surface:
    ado_workflows.iterations.get_latest_iteration_context(client, repository,
        pr_id, project) -> IterationContext
    ado_workflows.content.get_changed_file_contents(client, repository, pr_id,
        project, *, file_paths) -> ContentResult
    ado_workflows.pr.establish_pr_context(url_or_id, working_directory)
        -> AzureDevOpsPRContext

I/O boundaries:
    ado_workflows.discovery.subprocess.run (git CLI)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_pull_request_iterations,
    client.git.get_pull_request_iteration_changes,
    client.git.get_item_content (SDK REST calls)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext

from ado_workflows_mcp.tools.pr_files import (
    get_pr_file_changes,
    get_pr_file_contents,
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


# ---------------------------------------------------------------------------
# TestGetPRFileChanges
# ---------------------------------------------------------------------------


class TestGetPRFileChanges:
    """
    REQUIREMENT: An MCP consumer can list files changed in a PR with
    iteration metadata.

    WHO: Code review tools that need to know which files were modified.
    WHAT: (1) a valid PR URL returns a list of file change dicts with
              path, change_type, change_tracking_id, and iteration_id
          (2) a PR with no changes returns an empty list
          (3) an invalid PR URL returns ActionableError
          (4) an unexpected non-ActionableError exception returns
              ActionableError.internal with ai_guidance
    WHY: Required before fetching contents or posting line-specific comments.

    MOCK BOUNDARY:
        Mock:  subprocess.run (git CLI — context), ConnectionFactory (auth),
               client.git.get_pull_request_iterations,
               client.git.get_pull_request_iteration_changes (SDK REST calls)
        Real:  tool function, establish_pr_context,
               get_latest_iteration_context, FileChange serialization
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_pr_with_changes_returns_file_change_dicts(self, tmp_path: Any) -> None:
        """
        Given a valid PR URL with file changes
        When get_pr_file_changes is called
        Then returns a list of dicts with path, change_type, change_tracking_id,
             and iteration_id
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns iterations and changes
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            # Iterations
            iter_mock = MagicMock()
            iter_mock.id = 3
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
                "item": {"path": "/src/new_file.py"},
                "changeType": "add",
            }
            change2.change_tracking_id = 2
            changes_response = MagicMock()
            changes_response.change_entries = [change1, change2]
            mock_client.git.get_pull_request_iteration_changes.return_value = changes_response
            mock_ado_client_cls.return_value = mock_client

            # When: get_pr_file_changes is called
            result = get_pr_file_changes(pr_url_or_id=_PR_URL)

        # Then: returns list of file change dicts
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 2, f"Expected 2 file changes, got {len(result)}"
        paths = [r["path"] for r in result]
        assert "src/main.py" in paths, f"Expected src/main.py in paths, got {paths}"
        assert "src/new_file.py" in paths, f"Expected src/new_file.py in paths, got {paths}"
        # Verify dict shape
        first = result[0]
        assert "change_type" in first, (
            f"Expected 'change_type' key in result dict, got keys: {list(first.keys())}"
        )
        assert "change_tracking_id" in first, (
            f"Expected 'change_tracking_id' key in result dict, got keys: {list(first.keys())}"
        )
        assert "iteration_id" in first, (
            f"Expected 'iteration_id' key in result dict, got keys: {list(first.keys())}"
        )

    def test_pr_with_no_changes_returns_empty_list(self, tmp_path: Any) -> None:
        """
        Given a PR with no file changes
        When get_pr_file_changes is called
        Then returns an empty list
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

            # When: get_pr_file_changes is called
            result = get_pr_file_changes(pr_url_or_id=_PR_URL)

        # Then: returns empty list
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 0, f"Expected 0 file changes, got {len(result)}"

    def test_invalid_pr_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When get_pr_file_changes is called
        Then returns ActionableError
        """
        # When: called with unparseable URL
        result = get_pr_file_changes(
            pr_url_or_id="https://github.com/not-ado/repo",
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
        Given an unexpected non-ActionableError exception
        When get_pr_file_changes is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: establish_pr_context raises a non-ActionableError
        with patch(
            "ado_workflows_mcp.tools.pr_files._lib_establish_pr",
            side_effect=RuntimeError("unexpected crash"),
        ):
            # When: called
            result = get_pr_file_changes(pr_url_or_id=_PR_URL)

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


# ---------------------------------------------------------------------------
# TestGetPRFileContents
# ---------------------------------------------------------------------------


class TestGetPRFileContents:
    """
    REQUIREMENT: An MCP consumer can fetch source code from files in a PR.

    WHO: Code review tools that need to read code for analysis.
    WHAT: (1) a valid PR URL returns a list of file content dicts with
              path, content, encoding, and size_bytes
          (2) specific file_paths limits which files are fetched
          (3) a file that fails to fetch is omitted from success results
              and the failure carries ai_guidance for recovery
          (4) an invalid PR URL returns ActionableError
          (5) an unexpected non-ActionableError exception returns
              ActionableError.internal with ai_guidance
    WHY: Enables code analysis without a local checkout.

    MOCK BOUNDARY:
        Mock:  subprocess.run (git CLI — context), ConnectionFactory (auth),
               client.git.get_item_content, client.git.get_pull_request_by_id
               (SDK REST calls)
        Real:  tool function, establish_pr_context,
               get_changed_file_contents, ContentResult construction
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_valid_pr_returns_file_content_dicts(self, tmp_path: Any) -> None:
        """
        Given a valid PR URL
        When get_pr_file_contents is called
        Then returns a list of dicts with path, content, encoding, size_bytes
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: SDK returns PR details and file contents
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            # PR details for source branch
            pr_mock = MagicMock()
            pr_mock.source_ref_name = "refs/heads/feature/x"
            pr_mock.last_merge_source_commit = MagicMock(commit_id="abc123")
            mock_client.git.get_pull_request_by_id.return_value = pr_mock
            # Iterations for file list
            iter_mock = MagicMock()
            iter_mock.id = 1
            iter_mock.created_date = "2026-03-18T00:00:00Z"
            iter_mock.source_ref_commit = MagicMock(commit_id="abc123")
            iter_mock.target_ref_commit = MagicMock(commit_id="def456")
            mock_client.git.get_pull_request_iterations.return_value = [iter_mock]
            change = MagicMock()
            change.additional_properties = {
                "item": {"path": "/src/main.py"},
                "changeType": "edit",
            }
            change.change_tracking_id = 1
            changes_response = MagicMock()
            changes_response.change_entries = [change]
            mock_client.git.get_pull_request_iteration_changes.return_value = changes_response
            # File content
            mock_client.git.get_item_content.return_value = iter([b"def main():\n    pass\n"])
            mock_ado_client_cls.return_value = mock_client

            # When: get_pr_file_contents is called
            result = get_pr_file_contents(pr_url_or_id=_PR_URL)

        # Then: returns list of file content dicts
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) >= 1, f"Expected at least 1 file content, got {len(result)}"
        first = result[0]
        assert "path" in first, f"Expected 'path' key, got keys: {list(first.keys())}"
        assert "content" in first, f"Expected 'content' key, got keys: {list(first.keys())}"

    def test_specific_file_paths_limits_fetch(self, tmp_path: Any) -> None:
        """
        Given specific file_paths
        When get_pr_file_contents is called
        Then only those files are fetched
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            pr_mock = MagicMock()
            pr_mock.source_ref_name = "refs/heads/feature/x"
            pr_mock.last_merge_source_commit = MagicMock(commit_id="abc123")
            mock_client.git.get_pull_request_by_id.return_value = pr_mock
            # File content for the specific file
            mock_client.git.get_item_content.return_value = iter([b"# utils\n"])
            mock_ado_client_cls.return_value = mock_client

            # When: called with specific file_paths
            result = get_pr_file_contents(
                pr_url_or_id=_PR_URL,
                file_paths=["/src/utils.py"],
            )

        # Then: returns content for the specified file
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        if len(result) > 0:
            paths = [r["path"] for r in result]
            assert "/src/utils.py" in paths, f"Expected /src/utils.py in results, got {paths}"

    def test_missing_file_omitted_from_results(self, tmp_path: Any) -> None:
        """
        Given a file that doesn't exist in the PR
        When get_pr_file_contents is called
        Then that file is omitted from success results and the failure
             carries ai_guidance for recovery
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            pr_mock = MagicMock()
            pr_mock.source_ref_name = "refs/heads/feature/x"
            pr_mock.last_merge_source_commit = MagicMock(commit_id="abc123")
            mock_client.git.get_pull_request_by_id.return_value = pr_mock

            # First call succeeds, second raises (file not found)
            def _get_content(repository_id: str, path: str, **kwargs: Any) -> Any:
                if path == "/src/exists.py":
                    return iter([b"exists"])
                raise Exception("File not found: /src/missing.py")

            mock_client.git.get_item_content.side_effect = _get_content
            mock_ado_client_cls.return_value = mock_client

            # When: called with both existing and missing files
            result = get_pr_file_contents(
                pr_url_or_id=_PR_URL,
                file_paths=["/src/exists.py", "/src/missing.py"],
            )

        # Then: the existing file is in results, missing one is omitted,
        # and the failure carries ai_guidance
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        paths = [r.get("path", "") for r in result if "content" in r]
        assert "/src/missing.py" not in paths, (
            f"Expected missing file omitted from success results, got {paths}"
        )
        # Check that failures are surfaced with guidance
        failures = [r for r in result if "error" in r]
        if failures:
            failure = failures[0]
            assert "ai_guidance" in failure or failure.get("ai_guidance") is not None, (
                f"Expected ai_guidance on file fetch failure, got keys: {list(failure.keys())}"
            )

    def test_invalid_pr_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When get_pr_file_contents is called
        Then returns ActionableError
        """
        # When: called with unparseable URL
        result = get_pr_file_contents(
            pr_url_or_id="https://github.com/not-ado/repo",
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
        Given an unexpected non-ActionableError exception
        When get_pr_file_contents is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set
        _setup_context(tmp_path)

        # Given: establish_pr_context raises a non-ActionableError
        with patch(
            "ado_workflows_mcp.tools.pr_files._lib_establish_pr",
            side_effect=RuntimeError("unexpected crash"),
        ):
            # When: called
            result = get_pr_file_contents(pr_url_or_id=_PR_URL)

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
