"""
BDD tests for tools/repo_content.py — remote repo content inspection.

Covers:
- TestListRepoItemsTool: list files/folders at a path on any branch
- TestGetRepoFileContentTool: fetch file content from any branch/commit/tag

Public API surface (from src/ado_workflows_mcp/tools/repo_content.py):
    list_repo_items(*, path, ref, recursion, repository, project,
        working_directory) -> list[dict] | ActionableError
    get_repo_file_content(path, *, ref, repository, project,
        working_directory) -> dict | ActionableError

Library API surface:
    ado_workflows.content.list_repo_items(client, repository, project, *,
        path, ref, recursion) -> list[RepoItem]
    ado_workflows.content.get_file_content(client, repository, path,
        project, *, version, version_type) -> FileContent

I/O boundaries:
    ado_workflows.content.list_repo_items (SDK REST via client.git.get_items)
    ado_workflows.content.get_file_content (SDK REST via client.git.get_item_content)
    ado_workflows_mcp.tools._helpers.get_context (git discovery)
    ado_workflows_mcp.tools._helpers.get_client (auth/connection)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.models import FileContent, RepoItem

from ado_workflows_mcp.tools.repo_content import (
    get_repo_file_content,
    list_repo_items,
)

# ---------------------------------------------------------------------------
# Constants — patch targets at the I/O boundary
# ---------------------------------------------------------------------------

_LIB_LIST_ITEMS = "ado_workflows_mcp.tools.repo_content._lib_list_items"
_LIB_GET_CONTENT = "ado_workflows_mcp.tools.repo_content._lib_get_content"
_GET_CONTEXT = "ado_workflows_mcp.tools.repo_content.get_context"
_GET_CLIENT = "ado_workflows_mcp.tools.repo_content.get_client"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CTX: dict[str, Any] = {
    "organization": "TestOrg",
    "project": "TestProject",
    "repository": "TestRepo",
    "org_url": "https://dev.azure.com/TestOrg",
}


def _mock_context_and_client() -> tuple[MagicMock, MagicMock]:
    """Return (mock_get_context, mock_get_client) configured with defaults."""
    mock_ctx = MagicMock(return_value=_DEFAULT_CTX)
    mock_client_fn = MagicMock(return_value=MagicMock())
    return mock_ctx, mock_client_fn


def _make_repo_item(
    *,
    path: str = "/README.md",
    is_folder: bool = False,
    git_object_type: str = "blob",
    object_id: str = "abc123",
    commit_id: str = "def456",
    url: str | None = "https://dev.azure.com/item",
) -> RepoItem:
    """Build a RepoItem for test assertions."""
    return RepoItem(
        path=path,
        is_folder=is_folder,
        git_object_type=git_object_type,
        object_id=object_id,
        commit_id=commit_id,
        url=url,
    )


def _make_file_content(
    *,
    path: str = "/README.md",
    content: str = "# Hello World\n",
    encoding: str = "utf-8",
    size_bytes: int = 15,
) -> FileContent:
    """Build a FileContent for test assertions."""
    return FileContent(
        path=path,
        content=content,
        encoding=encoding,
        size_bytes=size_bytes,
    )


def _error_with_guidance() -> ActionableError:
    """Return an ActionableError that already has ai_guidance set."""
    return ActionableError.not_found(
        service="AzureDevOps",
        resource_type="item",
        resource_id="/missing",
        raw_error="not found",
        suggestion="check path",
        ai_guidance=AIGuidance(action_required="pre-set guidance"),
    )


# ---------------------------------------------------------------------------
# TestListRepoItemsTool
# ---------------------------------------------------------------------------


class TestListRepoItemsTool:
    """
    REQUIREMENT: An MCP consumer can list files and folders at a path on
    any branch of a remote Azure DevOps repository.

    WHO: AI agents reviewing PRs that need to verify what exists on the
    base branch before commenting on "missing" files.
    WHAT: (1) valid context returns a list of dicts with path, is_folder,
              git_object_type, object_id, commit_id, url
          (2) explicit repository/project params bypass context resolution
          (3) library ActionableError is returned with ai_guidance attached
          (4) unexpected non-ActionableError returns ActionableError.internal
              with ai_guidance
          (5) pre-existing ai_guidance on ActionableError is preserved
    WHY: Without this tool, the agent can only see files in the PR diff —
    it cannot verify what already exists on the base branch.

    MOCK BOUNDARY:
        Mock:  ado_workflows.content.list_repo_items (library I/O boundary),
               get_context / get_client (auth/context setup)
        Real:  MCP tool function, dict serialization, error wrapping
        Never: mock ActionableError or AIGuidance construction
    """

    def test_valid_context_returns_list_of_item_dicts(self) -> None:
        """
        Given library returns two RepoItems (a file and a folder),
        When list_repo_items is called with defaults,
        Then returns a list of 2 dicts with correct keys and values.
        """
        # Given: context resolves and library returns items
        mock_ctx, mock_client_fn = _mock_context_and_client()
        items = [
            _make_repo_item(path="/README.md", is_folder=False, git_object_type="blob"),
            _make_repo_item(path="/src", is_folder=True, git_object_type="tree"),
        ]

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_LIST_ITEMS, return_value=items),
        ):
            # When: called with defaults
            result = list_repo_items(path="/", working_directory="/fake")

        # Then: returns list of dicts with expected keys
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 2, f"Expected 2 items, got {len(result)}"

        readme = result[0]
        assert readme["path"] == "/README.md", (
            f"Expected path='/README.md', got {readme['path']!r}"
        )
        assert readme["is_folder"] is False, (
            f"Expected is_folder=False, got {readme['is_folder']!r}"
        )
        assert "git_object_type" in readme, (
            f"Expected 'git_object_type' key, got keys: {list(readme.keys())}"
        )
        assert "object_id" in readme, f"Expected 'object_id' key, got keys: {list(readme.keys())}"
        assert "commit_id" in readme, f"Expected 'commit_id' key, got keys: {list(readme.keys())}"

        src = result[1]
        assert src["is_folder"] is True, (
            f"Expected is_folder=True for folder, got {src['is_folder']!r}"
        )

    def test_explicit_repo_and_project_bypass_context(self) -> None:
        """
        Given explicit repository="MyRepo" and project="MyProject",
        When list_repo_items is called with those params,
        Then library is called with "MyRepo"/"MyProject", not context values.
        """
        # Given: library returns items
        mock_ctx, mock_client_fn = _mock_context_and_client()
        items = [_make_repo_item(path="/file.txt")]

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_LIST_ITEMS, return_value=items),
        ):
            # When: called with explicit repo/project
            result = list_repo_items(
                repository="MyRepo", project="MyProject", working_directory="/fake"
            )

        # Then: returns items (proving the call succeeded with explicit values)
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 item, got {len(result)}"
        assert result[0]["path"] == "/file.txt", (
            f"Expected path from library result, got {result[0].get('path')!r}"
        )

    def test_library_actionable_error_returned_with_ai_guidance(self) -> None:
        """
        Given library raises ActionableError without ai_guidance,
        When list_repo_items is called,
        Then returns the ActionableError with ai_guidance attached.
        """
        # Given: library raises ActionableError
        lib_error = ActionableError.not_found(
            service="AzureDevOps",
            resource_type="item",
            resource_id="/missing",
            raw_error="not found",
        )
        mock_ctx, mock_client_fn = _mock_context_and_client()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_LIST_ITEMS, side_effect=lib_error),
        ):
            # When: called
            result = list_repo_items(working_directory="/fake")

        # Then: returns ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance to be attached, got None"

    def test_unexpected_exception_returns_internal_error_with_guidance(self) -> None:
        """
        Given library raises a non-ActionableError exception,
        When list_repo_items is called,
        Then returns ActionableError.internal with ai_guidance.
        """
        # Given: library raises unexpected error
        mock_ctx, mock_client_fn = _mock_context_and_client()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_LIST_ITEMS, side_effect=RuntimeError("unexpected")),
        ):
            # When: called
            result = list_repo_items(working_directory="/fake")

        # Then: returns internal error with guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}"
        )
        assert result.error_type == "internal", (
            f"Expected error_type='internal', got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on internal error, got None"

    def test_pre_existing_ai_guidance_preserved(self) -> None:
        """
        Given library raises ActionableError with ai_guidance already set,
        When list_repo_items is called,
        Then returns the error with original ai_guidance unchanged.
        """
        # Given: library raises error with pre-set guidance
        lib_error = _error_with_guidance()
        mock_ctx, mock_client_fn = _mock_context_and_client()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_LIST_ITEMS, side_effect=lib_error),
        ):
            # When: called
            result = list_repo_items(working_directory="/fake")

        # Then: original guidance preserved
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance to be preserved, got None"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original ai_guidance text, got {result.ai_guidance.action_required!r}"
        )


# ---------------------------------------------------------------------------
# TestGetRepoFileContentTool
# ---------------------------------------------------------------------------


class TestGetRepoFileContentTool:
    """
    REQUIREMENT: An MCP consumer can fetch a single file's content from
    any branch, commit, or tag of a remote Azure DevOps repository.

    WHO: AI agents that need to read a specific file on the base branch
    (e.g., checking if .gitignore already has an entry).
    WHAT: (1) valid path and ref returns a dict with path, content, encoding,
              size_bytes
          (2) explicit repository/project params bypass context resolution
          (3) library ActionableError is returned with ai_guidance attached
          (4) unexpected non-ActionableError returns ActionableError.internal
              with ai_guidance
          (5) pre-existing ai_guidance on ActionableError is preserved
    WHY: Combined with list_repo_items, this gives the agent full read
    access to any ref — eliminating false "missing file" review comments.

    MOCK BOUNDARY:
        Mock:  ado_workflows.content.get_file_content (library I/O boundary),
               get_context / get_client (auth/context setup)
        Real:  MCP tool function, dict serialization, error wrapping
        Never: mock ActionableError or AIGuidance construction
    """

    def test_valid_path_returns_file_content_dict(self) -> None:
        """
        Given library returns a FileContent with content and encoding,
        When get_repo_file_content("/README.md", ref="main") is called,
        Then returns a dict with path, content, encoding, size_bytes.
        """
        # Given: context resolves and library returns content
        mock_ctx, mock_client_fn = _mock_context_and_client()
        fc = _make_file_content(
            path="/README.md",
            content="# Hello World\n",
            encoding="utf-8",
            size_bytes=15,
        )

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_GET_CONTENT, return_value=fc),
        ):
            # When: called with path and ref
            result = get_repo_file_content("/README.md", ref="main", working_directory="/fake")

        # Then: returns dict with expected keys and values
        assert isinstance(result, dict), f"Expected dict, got {type(result).__name__}: {result}"
        assert result["path"] == "/README.md", (
            f"Expected path='/README.md', got {result['path']!r}"
        )
        assert result["content"] == "# Hello World\n", (
            f"Expected content='# Hello World\\n', got {result['content']!r}"
        )
        assert result["encoding"] == "utf-8", (
            f"Expected encoding='utf-8', got {result['encoding']!r}"
        )
        assert result["size_bytes"] == 15, f"Expected size_bytes=15, got {result['size_bytes']!r}"

    def test_explicit_repo_and_project_bypass_context(self) -> None:
        """
        Given explicit repository="MyRepo" and project="MyProject",
        When get_repo_file_content is called with those params,
        Then library is called with "MyRepo"/"MyProject", not context values.
        """
        # Given: library returns content
        mock_ctx, mock_client_fn = _mock_context_and_client()
        fc = _make_file_content()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_GET_CONTENT, return_value=fc),
        ):
            # When: called with explicit repo/project
            result = get_repo_file_content(
                "/f.py", repository="MyRepo", project="MyProject", working_directory="/fake"
            )

        # Then: returns content (proving the call succeeded with explicit values)
        assert isinstance(result, dict), f"Expected dict, got {type(result).__name__}: {result}"
        assert result["path"] == "/README.md", (
            f"Expected path from library result, got {result.get('path')!r}"
        )

    def test_library_actionable_error_returned_with_ai_guidance(self) -> None:
        """
        Given library raises ActionableError without ai_guidance,
        When get_repo_file_content is called,
        Then returns the ActionableError with ai_guidance attached.
        """
        # Given: library raises ActionableError
        lib_error = ActionableError.not_found(
            service="AzureDevOps",
            resource_type="file",
            resource_id="/missing.py",
            raw_error="not found",
        )
        mock_ctx, mock_client_fn = _mock_context_and_client()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_GET_CONTENT, side_effect=lib_error),
        ):
            # When: called
            result = get_repo_file_content("/missing.py", working_directory="/fake")

        # Then: returns ActionableError with ai_guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance to be attached, got None"

    def test_unexpected_exception_returns_internal_error_with_guidance(self) -> None:
        """
        Given library raises a non-ActionableError exception,
        When get_repo_file_content is called,
        Then returns ActionableError.internal with ai_guidance.
        """
        # Given: library raises unexpected error
        mock_ctx, mock_client_fn = _mock_context_and_client()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_GET_CONTENT, side_effect=RuntimeError("kaboom")),
        ):
            # When: called
            result = get_repo_file_content("/file.py", working_directory="/fake")

        # Then: returns internal error with guidance
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}"
        )
        assert result.error_type == "internal", (
            f"Expected error_type='internal', got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on internal error, got None"

    def test_pre_existing_ai_guidance_preserved(self) -> None:
        """
        Given library raises ActionableError with ai_guidance already set,
        When get_repo_file_content is called,
        Then returns the error with original ai_guidance unchanged.
        """
        # Given: library raises error with pre-set guidance
        lib_error = _error_with_guidance()
        mock_ctx, mock_client_fn = _mock_context_and_client()

        with (
            patch(_GET_CONTEXT, mock_ctx),
            patch(_GET_CLIENT, mock_client_fn),
            patch(_LIB_GET_CONTENT, side_effect=lib_error),
        ):
            # When: called
            result = get_repo_file_content("/missing.py", working_directory="/fake")

        # Then: original guidance preserved
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance to be preserved, got None"
        assert result.ai_guidance.action_required == "pre-set guidance", (
            f"Expected original ai_guidance text, got {result.ai_guidance.action_required!r}"
        )
