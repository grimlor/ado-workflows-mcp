"""
BDD tests for tools/repositories.py — repository discovery tool.

Covers:
- TestRepositoryDiscovery: discovering ADO repos from local git remotes

Public API surface (from src/ado_workflows_mcp/tools/repositories.py):
    repository_discovery(working_directory: str | None = None)
        -> dict[str, Any] | ActionableError

Library API surface (from ado_workflows.discovery):
    discover_repositories(search_root: str) -> list[dict[str, Any]]
    infer_target_repository(repositories, working_directory) -> dict[str, Any] | None

I/O boundary:
    ado_workflows.discovery.subprocess.run (git CLI)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError

from ado_workflows_mcp.tools.repositories import repository_discovery

if TYPE_CHECKING:
    import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_ADO_REMOTE_2 = "https://dev.azure.com/TestOrg/TestProject/_git/OtherRepo"
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


def _setup_git_repo(tmp_path: Any, remote: str = _ADO_REMOTE) -> str:
    """Create a .git directory in tmp_path and return its path as a string."""
    (tmp_path / ".git").mkdir()
    return str(tmp_path)


class TestRepositoryDiscovery:
    """
    REQUIREMENT: Discover Azure DevOps repositories from local git remotes.

    WHO: Any agent needing to identify which ADO org/project/repo it's working in.
    WHAT: Scans working directory (or cwd) for git repos, extracts ADO remote
          metadata, selects the best match.
    WHY: Prerequisite for every ADO operation — agents need org/project/repo context.

    MOCK BOUNDARY:
        Mock:  `subprocess.run` (git CLI — the only I/O in discovery)
        Real:  tool function, `discover_repositories`, `infer_target_repository`,
               response formatting, `tmp_path` filesystem
        Never: FastMCP framework, library functions in our codebase
    """

    def test_single_ado_repo_returns_metadata(self, tmp_path: Any) -> None:
        """
        Given a working directory with one ADO repo
        When repository_discovery is called
        Then returns repo metadata dict
        """
        # Given: a tmp_path with .git directory and subprocess returning ADO remote
        repo_dir = _setup_git_repo(tmp_path)
        with patch(_SUBPROCESS_PATCH, return_value=_git_success(_ADO_REMOTE)):
            # When: repository_discovery is called with working_directory
            result = repository_discovery(working_directory=repo_dir)

        # Then: result contains repo metadata
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )
        assert result.get("name") == "TestRepo", (
            f"Expected repo name 'TestRepo', got {result.get('name')!r}. Full result: {result}"
        )
        assert result.get("organization") == "TestOrg", (
            f"Expected org 'TestOrg', got {result.get('organization')!r}. Full result: {result}"
        )
        assert result.get("project") == "TestProject", (
            f"Expected project 'TestProject', got {result.get('project')!r}. Full result: {result}"
        )

    def test_multiple_repos_returns_inferred_best_match(self, tmp_path: Any) -> None:
        """
        Given a working directory with multiple repos
        When repository_discovery is called
        Then returns the inferred best match
        """
        # Given: two subdirs with .git dirs, subprocess returning different remotes
        sub1 = tmp_path / "repo1"
        sub1.mkdir()
        (sub1 / ".git").mkdir()

        sub2 = tmp_path / "repo2"
        sub2.mkdir()
        (sub2 / ".git").mkdir()

        call_count = 0

        def _side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            # First call for repo1, second for repo2
            if call_count % 2 == 1:
                return _git_success(_ADO_REMOTE)
            return _git_success(_ADO_REMOTE_2)

        with patch(_SUBPROCESS_PATCH, side_effect=_side_effect):
            # When: called on the parent directory (discovers both)
            result = repository_discovery(working_directory=str(sub1))

        # Then: returns a dict (the best match from the working directory)
        assert isinstance(result, dict), (
            f"Expected dict result, got {type(result).__name__}: {result}"
        )
        assert "name" in result, f"Expected 'name' key in result. Got keys: {list(result.keys())}"

    def test_no_ado_repos_returns_actionable_error(self, tmp_path: Any) -> None:
        """
        Given a directory with no ADO repos
        When repository_discovery is called
        Then returns ActionableError with suggestion
        """
        # Given: a tmp_path with no .git directory
        with patch(_SUBPROCESS_PATCH, return_value=_git_failure()):
            # When: repository_discovery is called
            result = repository_discovery(working_directory=str(tmp_path))

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError for no-repo dir, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "working directory" in guidance, (
            f"ai_guidance should mention 'working directory', got: {guidance}"
        )
        assert "azure devops" in guidance or "ado" in guidance, (
            f"ai_guidance should reference Azure DevOps, got: {guidance}"
        )
        assert result.ai_guidance.checks, (
            "ai_guidance.checks should list concrete verification steps"
        )

    def test_no_working_directory_uses_cwd(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Given no working_directory argument
        When repository_discovery is called
        Then uses cwd
        """
        # Given: cwd set to a directory with a .git dir
        _setup_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)

        with patch(_SUBPROCESS_PATCH, return_value=_git_success(_ADO_REMOTE)):
            # When: called with no working_directory
            result = repository_discovery()

        # Then: discovers the repo from cwd
        assert isinstance(result, dict), (
            f"Expected dict result from cwd discovery, got {type(result).__name__}: {result}"
        )
        assert result.get("organization") == "TestOrg", (
            f"Expected org 'TestOrg' from cwd, got {result.get('organization')!r}"
        )

    def test_multiple_repos_no_match_returns_actionable_error(self, tmp_path: Any) -> None:
        """
        Given multiple repos but none match working directory
        When repository_discovery is called
        Then returns ActionableError with suggestion to narrow search
        """
        # Given: discover_repositories returns repos, infer_target_repository returns None
        with (
            patch(
                "ado_workflows_mcp.tools.repositories.discover_repositories",
                return_value=[{"name": "Repo1"}, {"name": "Repo2"}],
            ),
            patch(
                "ado_workflows_mcp.tools.repositories.infer_target_repository",
                return_value=None,
            ),
        ):
            # When: called
            result = repository_discovery(working_directory=str(tmp_path))

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError for no-match, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on no-match error. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on no-match error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "narrow" in guidance or "working_directory" in guidance, (
            f"ai_guidance should suggest narrowing search, got: {guidance}"
        )

    def test_actionable_error_without_guidance_gets_enriched(self, tmp_path: Any) -> None:
        """
        Given the library raises ActionableError without ai_guidance
        When repository_discovery is called
        Then returns the error with ai_guidance enriched
        """
        # Given: library raises ActionableError with no ai_guidance
        bare_error = ActionableError(
            error="Git not found",
            error_type="VALIDATION",
            service="ado-workflows",
        )
        with patch(
            "ado_workflows_mcp.tools.repositories.discover_repositories",
            side_effect=bare_error,
        ):
            # When: called
            result = repository_discovery(working_directory=str(tmp_path))

        # Then: returns ActionableError with ai_guidance enriched
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance to be enriched, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "discovery" in guidance or "error" in guidance or "retry" in guidance, (
            f"ai_guidance should mention discovery/error/retry, got: {guidance}"
        )

    def test_unexpected_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given the library raises an unexpected Exception
        When repository_discovery is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: library raises generic exception
        with patch(
            "ado_workflows_mcp.tools.repositories.discover_repositories",
            side_effect=RuntimeError("segfault"),
        ):
            # When: called
            result = repository_discovery(working_directory=str(tmp_path))

        # Then: returns ActionableError with internal error details
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on internal error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "unexpected" in guidance or "discovery" in guidance, (
            f"ai_guidance should mention unexpected/discovery, got: {guidance}"
        )
