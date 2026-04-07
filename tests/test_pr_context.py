"""
BDD tests for tools/pr_context.py — PR context and creation tools.

Covers:
- TestEstablishPRContext: resolving PR context from URL or numeric ID
- TestCreatePullRequest: creating a pull request via SDK

Public API surface (from src/ado_workflows_mcp/tools/pr_context.py):
    establish_pr_context(pr_url_or_id: str, working_directory: str | None)
        -> AzureDevOpsPRContext | ActionableError
    create_pull_request(source_branch: str, target_branch: str, ...)
        -> CreatedPR | ActionableError

Library API surface:
    ado_workflows.pr.establish_pr_context(url_or_id, working_directory) -> AzureDevOpsPRContext
    ado_workflows.lifecycle.create_pull_request(client, repository, source, target, project, ...)
        -> CreatedPR
    ado_workflows.auth.ConnectionFactory(credential).get_connection(org_url) -> Connection
    ado_workflows.client.AdoClient(connection) — wraps SDK client

I/O boundaries:
    ado_workflows.discovery.Repo (GitPython)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.create_pull_request (SDK REST call)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.context import RepositoryContext
from ado_workflows.models import CreatedPR
from ado_workflows.pr import AzureDevOpsPRContext

from ado_workflows_mcp.tools.pr_context import (
    create_pull_request,
    establish_pr_context,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_PR_URL = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo/pullrequest/42"
_REPO_PATCH = "ado_workflows.discovery.Repo"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"


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


def _mock_connection_factory() -> MagicMock:
    """Return a mock ConnectionFactory that produces a mock Connection."""
    factory = MagicMock()
    factory.return_value.get_connection.return_value = MagicMock()
    return factory


def _mock_sdk_pr_response() -> MagicMock:
    """Return a mock SDK pull request response object."""
    response = MagicMock()
    response.pull_request_id = 42
    response.url = _PR_URL
    response.title = "feat: add widget"
    response.source_ref_name = "refs/heads/feature/widget"
    response.target_ref_name = "refs/heads/main"
    response.is_draft = False
    return response


def _error_with_guidance() -> ActionableError:
    """Return an ActionableError that already has ai_guidance set."""
    return ActionableError.connection(
        service="AzureDevOps",
        url="https://dev.azure.com",
        raw_error="test error",
        suggestion="test suggestion",
        ai_guidance=AIGuidance(action_required="pre-set guidance"),
    )


class TestEstablishPRContext:
    """
    REQUIREMENT: Create reusable PR context from URL or numeric ID.

    WHO: Agents that need to perform multiple operations against one PR.
    WHAT: Parses URL or resolves PR ID to org/project/repo/pr_id context.
    WHY: Eliminates repeated URL parsing across comment/review tools.

    MOCK BOUNDARY:
        Mock:  `git.Repo` (GitPython — for context resolution when using
               numeric ID)
        Real:  tool function, `establish_pr_context`, URL parsing,
               `tmp_path` filesystem
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_pr_url_returns_context(self) -> None:
        """
        Given a valid PR URL
        When establish_pr_context is called
        Then returns AzureDevOpsPRContext
        """
        # When: called with a full PR URL
        result = establish_pr_context(pr_url_or_id=_PR_URL)

        # Then: returns resolved context
        assert isinstance(result, AzureDevOpsPRContext), (
            f"Expected AzureDevOpsPRContext, got {type(result).__name__}: {result}"
        )
        assert result.organization == "TestOrg", (
            f"Expected organization='TestOrg', got '{result.organization}'"
        )
        assert result.project == "TestProject", (
            f"Expected project='TestProject', got '{result.project}'"
        )
        assert result.repository == "TestRepo", (
            f"Expected repository='TestRepo', got '{result.repository}'"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"

    def test_numeric_pr_id_with_context_resolves(self, tmp_path: Any) -> None:
        """
        Given a numeric PR ID with repo context set
        When establish_pr_context is called
        Then resolves via context and returns AzureDevOpsPRContext
        """
        # Given: repository context is set
        (tmp_path / ".git").mkdir()
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
            RepositoryContext.set(working_directory=str(tmp_path))

        # When: called with a numeric ID
        result = establish_pr_context(pr_url_or_id="42")

        # Then: resolves context from cache
        assert isinstance(result, AzureDevOpsPRContext), (
            f"Expected AzureDevOpsPRContext, got {type(result).__name__}: {result}"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"
        assert result.source == "repository_context", (
            f"Expected source='repository_context', got '{result.source}'"
        )

    def test_numeric_pr_id_without_context_returns_error(self) -> None:
        """
        Given a numeric PR ID without context
        When establish_pr_context is called
        Then returns ActionableError with suggestion
        """
        # Given: no context set
        RepositoryContext.clear()

        # When: called with numeric ID and no context
        result = establish_pr_context(pr_url_or_id="42")

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "context" in guidance or "url" in guidance, (
            f"ai_guidance should mention context or URL for numeric ID, got: {guidance}"
        )

    def test_invalid_url_returns_error(self) -> None:
        """
        Given an invalid URL
        When establish_pr_context is called
        Then returns ActionableError with suggestion
        """
        # When: called with garbage input
        result = establish_pr_context(pr_url_or_id="not-a-url-or-id")

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "pr" in guidance or "url" in guidance, (
            f"ai_guidance should mention PR or URL for invalid input, got: {guidance}"
        )

    def test_actionable_error_without_guidance_gets_enriched(self) -> None:
        """
        Given input that the library rejects with ActionableError (ai_guidance=None)
        When establish_pr_context is called
        Then returns the error with ai_guidance enriched
        """
        # When: called with a non-URL, non-numeric string
        # Real establish_pr_context raises ActionableError.validation (ai_guidance=None)
        result = establish_pr_context(pr_url_or_id="not-a-valid-id")

        # Then: returns ActionableError with ai_guidance enriched
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance to be enriched, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "pr" in guidance or "context" in guidance or "url" in guidance, (
            f"ai_guidance should mention PR/context/URL, got: {guidance}"
        )

    @patch("ado_workflows_mcp.tools.pr_context._lib_establish", side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When establish_pr_context is called
        Then returns the error with original ai_guidance preserved
        """
        result = establish_pr_context(
            pr_url_or_id="https://dev.azure.com/O/P/_git/R/pullrequest/1"
        )
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )

    def test_unexpected_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given an unexpected exception at the I/O boundary
        When establish_pr_context is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: .git dir exists so discovery enters inspect_git_repository,
        # but git.Repo raises an unexpected RuntimeError
        (tmp_path / ".git").mkdir()
        with patch(
            _REPO_PATCH,
            side_effect=RuntimeError("unexpected parse error"),
        ):
            # When: called with numeric ID (triggers context discovery)
            result = establish_pr_context(
                pr_url_or_id="42",
                working_directory=str(tmp_path),
            )

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


class TestCreatePullRequest:
    """
    REQUIREMENT: Create a new pull request via the SDK.

    WHO: Agents automating PR creation workflows.
    WHAT: Constructs PR from branch names, optional title/description, draft mode.
    WHY: Replaces `az repos pr create` subprocess.

    MOCK BOUNDARY:
        Mock:  `git.Repo` (GitPython — context), `ConnectionFactory` (auth),
               `client.git.create_pull_request` (SDK REST call)
        Real:  tool function, `create_pull_request`, `get_client`, branch
               normalization, response formatting
        Never: FastMCP framework, library functions in our codebase
    """

    def test_valid_branches_creates_pr(self, tmp_path: Any) -> None:
        """
        Given valid branches and context
        When create_pull_request is called
        Then creates PR and returns CreatedPR
        """
        # Given: repository context is set
        (tmp_path / ".git").mkdir()
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
            RepositoryContext.set(working_directory=str(tmp_path))

        # Given: auth and SDK mocked
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch("ado_workflows_mcp.tools._helpers.AdoClient") as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.create_pull_request.return_value = _mock_sdk_pr_response()
            mock_ado_client_cls.return_value = mock_client

            # When: create_pull_request is called
            result = create_pull_request(
                source_branch="feature/widget",
                target_branch="main",
                title="feat: add widget",
            )

        # Then: returns CreatedPR
        assert isinstance(result, CreatedPR), (
            f"Expected CreatedPR, got {type(result).__name__}: {result}"
        )
        assert result.pr_id == 42, f"Expected pr_id=42, got {result.pr_id}"
        assert result.title == "feat: add widget", (
            f"Expected title='feat: add widget', got '{result.title}'"
        )

    def test_missing_context_returns_error(self) -> None:
        """
        Given missing context
        When create_pull_request is called
        Then returns ActionableError with suggestion and ai_guidance
        """
        # Given: no context set
        RepositoryContext.clear()

        # When: create_pull_request called without context
        result = create_pull_request(
            source_branch="feature/widget",
            target_branch="main",
        )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "branch" in guidance or "credential" in guidance, (
            f"ai_guidance should mention branches or credentials, got: {guidance}"
        )

    def test_sdk_failure_returns_error(self, tmp_path: Any) -> None:
        """
        Given SDK failure
        When create_pull_request is called
        Then returns ActionableError with suggestion and ai_guidance
        """
        # Given: repository context is set
        (tmp_path / ".git").mkdir()
        with patch(_REPO_PATCH, return_value=_mock_git_repo()):
            RepositoryContext.set(working_directory=str(tmp_path))

        # Given: auth mocked, SDK raises
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch("ado_workflows_mcp.tools._helpers.AdoClient") as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.git.create_pull_request.side_effect = Exception("403 Forbidden")
            mock_ado_client_cls.return_value = mock_client

            # When: create_pull_request called
            result = create_pull_request(
                source_branch="feature/widget",
                target_branch="main",
            )

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.suggestion is not None, (
            f"Expected suggestion on error, got None. Error: {result.error}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )
        guidance = result.ai_guidance.action_required.lower()
        assert "create" in guidance or "retry" in guidance or "ask" in guidance, (
            f"ai_guidance should mention retry or ask user for SDK failure, got: {guidance}"
        )

    @patch("ado_workflows_mcp.tools.pr_context.get_context", side_effect=_error_with_guidance())
    def test_actionable_error_with_guidance_passes_through(
        self, mock_establish: MagicMock
    ) -> None:
        """
        Given an ActionableError that already has ai_guidance set
        When create_pull_request is called
        Then returns the error with original ai_guidance preserved
        """
        result = create_pull_request(source_branch="feature/x")
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance preserved"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original guidance, got: {result.ai_guidance.action_required}"
        )
