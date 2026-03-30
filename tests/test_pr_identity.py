"""
BDD tests for tools/pr_identity.py — PR author and current user identity.

Covers:
- TestGetPRAuthor: retrieve PR creator identity
- TestGetCurrentUser: retrieve authenticated user identity

Public API surface (from src/ado_workflows_mcp/tools/pr_identity.py):
    get_pr_author(pr_url_or_id, working_directory) -> UserIdentity | ActionableError
    get_current_user(working_directory) -> UserIdentity | ActionableError

Library API surface:
    ado_workflows.pr.get_pr_author(client, pr_id, project) -> UserIdentity
    ado_workflows.auth.get_current_user(client) -> UserIdentity

I/O boundaries:
    ado_workflows.discovery.subprocess.run (git CLI)
    ado_workflows.auth.ConnectionFactory / DefaultAzureCredential (auth)
    client.git.get_pull_request_by_id, client.location.get_connection_data (SDK REST calls)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext
from ado_workflows.models import UserIdentity

from ado_workflows_mcp.tools.pr_identity import (
    get_current_user,
    get_pr_author,
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
# TestGetPRAuthor
# ---------------------------------------------------------------------------


class TestGetPRAuthor:
    """
    REQUIREMENT: An MCP consumer can retrieve the identity of a PR's creator.

    WHO: Code review tools that need the PR author for filtering or attribution.
    WHAT: (1) a valid PR URL returns UserIdentity with display_name and id
          (2) an invalid PR URL returns ActionableError with ai_guidance
          (3) an unexpected exception returns ActionableError.internal with
              ai_guidance
    WHY: Enables self-praise filtering and author-aware review workflows
         without requiring the consumer to construct SDK clients.

    MOCK BOUNDARY:
        Mock:  subprocess.run (git CLI — context), ConnectionFactory (auth),
               client.git.get_pull_request_by_id (SDK REST call)
        Real:  tool function, establish_pr_context, get_pr_author,
               UserIdentity construction
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_valid_pr_returns_user_identity(self, tmp_path: Any) -> None:
        """
        Given a valid PR URL
        When get_pr_author is called
        Then returns UserIdentity with display_name and id
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
            pr_mock.created_by.display_name = "Alice Dev"
            pr_mock.created_by.id = "guid-alice"
            pr_mock.created_by.unique_name = "alice@example.com"
            mock_client.git.get_pull_request_by_id.return_value = pr_mock
            mock_ado_client_cls.return_value = mock_client

            # When: get_pr_author is called
            result = get_pr_author(pr_url_or_id=_PR_URL)

        # Then: returns UserIdentity
        assert isinstance(result, UserIdentity), (
            f"Expected UserIdentity, got {type(result).__name__}: {result}"
        )
        assert result.display_name == "Alice Dev", (
            f"Expected display_name='Alice Dev', got '{result.display_name}'"
        )
        assert result.id == "guid-alice", f"Expected id='guid-alice', got '{result.id}'"

    def test_invalid_pr_url_returns_actionable_error(self) -> None:
        """
        Given an invalid PR URL
        When get_pr_author is called
        Then returns ActionableError with ai_guidance
        """
        # When: called with unparseable URL
        result = get_pr_author(pr_url_or_id="https://github.com/not-ado/repo")

        # Then: returns ActionableError
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.ai_guidance is not None, (
            f"Expected ai_guidance on error, got None. Error: {result.error}"
        )

    def test_unexpected_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given an unexpected non-ActionableError exception at the I/O boundary
        When get_pr_author is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set, but ConnectionFactory.get_connection raises
        _setup_context(tmp_path)

        mock_factory = MagicMock()
        mock_factory.return_value.get_connection.side_effect = RuntimeError(
            "unexpected crash",
        )
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            # When: called (establish_pr_context parses URL, then get_client fails)
            result = get_pr_author(pr_url_or_id=_PR_URL)

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
# TestGetCurrentUser
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    """
    REQUIREMENT: An MCP consumer can retrieve the authenticated user's identity.

    WHO: Code review tools needing identity for self-praise filtering,
         commit attribution, or permission checks.
    WHAT: (1) authenticated context returns UserIdentity with display_name and id
          (2) an SDK auth failure returns ActionableError produced by the
              library's real error handling chain
          (3) an unexpected exception returns ActionableError.internal with
              ai_guidance
    WHY: Enables identity-aware workflows without requiring the consumer
         to understand the Azure DevOps auth chain.

    MOCK BOUNDARY:
        Mock:  subprocess.run (git CLI — context), ConnectionFactory (auth),
               client.location.get_connection_data (SDK REST call)
        Real:  tool function, get_current_user, UserIdentity construction
        Never: FastMCP framework
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_authenticated_returns_user_identity(self, tmp_path: Any) -> None:
        """
        Given valid authentication
        When get_current_user is called
        Then returns UserIdentity with display_name and id
        """
        # Given: context is set
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            conn_data = MagicMock()
            conn_data.authenticated_user.provider_display_name = "Bob Builder"
            conn_data.authenticated_user.id = "guid-bob"
            mock_client.location.get_connection_data.return_value = conn_data
            mock_ado_client_cls.return_value = mock_client

            # When: get_current_user is called (uses cached context)
            result = get_current_user()

        # Then: returns UserIdentity
        assert isinstance(result, UserIdentity), (
            f"Expected UserIdentity, got {type(result).__name__}: {result}"
        )
        assert result.display_name == "Bob Builder", (
            f"Expected display_name='Bob Builder', got '{result.display_name}'"
        )
        assert result.id == "guid-bob", f"Expected id='guid-bob', got '{result.id}'"

    def test_auth_failure_returns_actionable_error(self, tmp_path: Any) -> None:
        """
        Given the SDK raises an auth failure during get_connection_data
        When get_current_user is called
        Then returns ActionableError produced by the library's real error handling
        """
        # Given: context is set, SDK auth call fails
        _setup_context(tmp_path)

        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_ado_client_cls,
        ):
            mock_client = Mock()
            mock_client.location.get_connection_data.side_effect = Exception(
                "Token expired",
            )
            mock_ado_client_cls.return_value = mock_client

            # When: called — real _lib_current_user catches SDK error,
            # raises ActionableError, tool's except handler returns it
            result = get_current_user()

        # Then: returns ActionableError with auth details from the library
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert "Token expired" in result.error, (
            f"Expected 'Token expired' in error, got: {result.error}"
        )

    def test_unexpected_exception_returns_internal_error(self, tmp_path: Any) -> None:
        """
        Given an unexpected non-ActionableError exception at the I/O boundary
        When get_current_user is called
        Then returns ActionableError.internal with ai_guidance
        """
        # Given: context is set, but ConnectionFactory.get_connection raises
        _setup_context(tmp_path)

        mock_factory = MagicMock()
        mock_factory.return_value.get_connection.side_effect = RuntimeError(
            "unexpected crash",
        )
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            # When: called
            result = get_current_user()

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
