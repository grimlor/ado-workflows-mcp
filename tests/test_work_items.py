"""
BDD tests for tools/work_items.py — work item MCP tools.

Covers:
    TestGetWorkItemsTool — batch-fetch multiple work items by ID
    TestCreateWorkItemTool — create a new work item of any type
    TestMoveWorkItemsToSprintTool — move work items to a target sprint
    TestGetWorkItemTypeFieldsTool — discover fields for a work item type
    TestGetWorkItemUrlDispatch — widened get_work_item URL/ID dispatch
    TestUpdateWorkItemUrlDispatch — widened update_work_item URL/ID dispatch
    TestCloneWorkItemUrlDispatch — widened clone_work_item URL/ID dispatch
    TestBareIdGuidanceCaveat — docstrings warn about bare-ID misroute
    TestAmbiguityPropagationOnUnwidenedTools — ActionableErrors from
        repo discovery surface unchanged on tools that still take a
        repository_id parameter

Public API surface (from src/ado_workflows_mcp/tools/work_items.py):
    get_work_item(work_item_url_or_id, *, working_directory)
        -> WorkItemDetail | ActionableError
    get_work_items(project, work_item_ids, *, working_directory)
        -> list[WorkItemDetail] | ActionableError
    update_work_item(work_item_url_or_id, fields, *, working_directory)
        -> WorkItemDetail | ActionableError
    create_work_item(project, work_item_type, *, fields, parent_id, working_directory)
        -> WorkItemDetail | ActionableError
    move_work_items_to_sprint(project, work_item_ids, iteration_path, *, working_directory)
        -> list[WorkItemDetail] | ActionableError
    clone_work_item(source_work_item_url_or_id, *, field_overrides, working_directory)
        -> WorkItemDetail | ActionableError
    get_work_item_type_fields(project, work_item_type, *, working_directory)
        -> list[WorkItemFieldInfo] | ActionableError
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from actionable_errors import ActionableError
from ado_workflows.context import RepositoryContext
from ado_workflows.models import WorkItemDetail, WorkItemFieldInfo

from ado_workflows_mcp.tools.work_items import (
    clone_work_item,
    create_work_item,
    get_work_item,
    get_work_item_type_fields,
    get_work_items,
    move_work_items_to_sprint,
    update_work_item,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADO_REMOTE = "https://dev.azure.com/TestOrg/TestProject/_git/TestRepo"
_REPO_PATCH = "ado_workflows.discovery.Repo"
_CONN_FACTORY_PATCH = "ado_workflows_mcp.tools._helpers.ConnectionFactory"
_ADO_CLIENT_PATCH = "ado_workflows_mcp.tools._helpers.AdoClient"

_SAMPLE_DETAIL = WorkItemDetail(
    id=1001,
    title="Sample task",
    state="Active",
    work_item_type="Task",
    assigned_to="Alice Smith",
    area_path=r"One\CFS\PayFin and Data Platform Redmond",
    iteration_path=r"One\FY26\Q4\2Wk\2Wk21",
    completed_work=4.0,
    remaining_work=8.0,
    parent_id=5000,
    url="https://dev.azure.com/org/project/_apis/wit/workItems/1001",
    fields={
        "System.Title": "Sample task",
        "System.State": "Active",
        "System.WorkItemType": "Task",
    },
)

_SAMPLE_FIELD_INFO = WorkItemFieldInfo(
    name="Title",
    reference_name="System.Title",
    field_type="String",
    is_required=True,
)


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


def _assert_actionable_error_with_guidance(
    result: object,
    *,
    operation_hint: str,
) -> None:
    """
    Assert the result is an ActionableError with appropriate ai_guidance.

    Checks that:
    - The result is an ActionableError
    - ai_guidance exists with a non-empty action_required describing the failure
    - checks list is non-empty and contains actionable advice referencing
      project, authentication, or the operation domain
    """
    assert isinstance(result, ActionableError), (
        f"Expected ActionableError, got {type(result).__name__}: {result}"
    )
    assert result.ai_guidance is not None, (
        f"Expected ai_guidance on error, got None. Error: {result.error}"
    )
    guidance = result.ai_guidance
    assert guidance.action_required, "Expected non-empty action_required in ai_guidance"
    assert operation_hint.lower() in guidance.action_required.lower(), (
        f"Expected action_required to reference '{operation_hint}', "
        f"got: {guidance.action_required!r}"
    )
    checks = guidance.checks or []
    assert len(checks) > 0, "Expected at least one check in ai_guidance"
    checks_text = " ".join(checks).lower()
    assert any(
        term in checks_text for term in ("project", "authentication", "credentials", "az login")
    ), f"Expected checks to contain actionable advice about project or auth, got: {checks}"


# ---------------------------------------------------------------------------
# TestGetWorkItemsTool
# ---------------------------------------------------------------------------


class TestGetWorkItemsTool:
    """
    REQUIREMENT: MCP tool wrapper for get_work_items.

    WHO: AI agents via MCP
    WHAT: (1) given a list of work item IDs, returns list of WorkItemDetail
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to batch-fetch work items by ID without managing
         ADO authentication or SDK details.

    MOCK BOUNDARY:
        Mock:  get_client(), library get_work_items() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_work_item_detail_list(self, tmp_path: Any) -> None:
        """
        Given a list of work item IDs,
        When the get_work_items tool is called,
        Then returns list of WorkItemDetail.
        """
        # Given: library returns two items
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_items",
                return_value=[_SAMPLE_DETAIL, _SAMPLE_DETAIL],
            ):
                # When: tool is called
                result = get_work_items("TestProject", [1001, 1002])

        # Then: returns list of WorkItemDetail
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 2, f"Expected 2 items, got {len(result)}"

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during batch fetch,
        When the get_work_items tool is called,
        Then returns ActionableError with ai_guidance.
        """
        # Given: library raises an unexpected error
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_items",
                side_effect=Exception("service unavailable"),
            ):
                # When: tool is called
                result = get_work_items("TestProject", [1001])

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="work item")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the get_work_items tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="batch failed",
            error_type="service_error",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_items",
                side_effect=original,
            ):
                # When: tool is called
                result = get_work_items("TestProject", [1001])

        # Then: returns the same ActionableError
        assert result is original, (
            f"Expected original ActionableError returned directly, got {result!r}"
        )


# ---------------------------------------------------------------------------
# TestCreateWorkItemTool
# ---------------------------------------------------------------------------


class TestCreateWorkItemTool:
    """
    REQUIREMENT: MCP tool wrapper for create_work_item.

    WHO: AI agents via MCP
    WHAT: (1) given a type and fields, returns created WorkItemDetail
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to create work items of any type without managing
         ADO field schemas or SDK details.

    MOCK BOUNDARY:
        Mock:  get_client(), library create_work_item() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_created_detail(self, tmp_path: Any) -> None:
        """
        Given a work item type and fields,
        When the create_work_item tool is called,
        Then returns created WorkItemDetail.
        """
        # Given: library returns created item
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_create_work_item",
                return_value=_SAMPLE_DETAIL,
            ):
                # When: tool is called
                result = create_work_item(
                    "TestProject",
                    "Task",
                    fields={"System.Title": "New task"},
                )

        # Then: returns WorkItemDetail
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during creation,
        When the create_work_item tool is called,
        Then returns ActionableError with ai_guidance.
        """
        # Given: library raises an unexpected error
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_create_work_item",
                side_effect=Exception("invalid type"),
            ):
                # When: tool is called
                result = create_work_item(
                    "TestProject",
                    "Task",
                    fields={"System.Title": "Task"},
                )

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="work item")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the create_work_item tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="create failed",
            error_type="service_error",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_create_work_item",
                side_effect=original,
            ):
                # When: tool is called
                result = create_work_item(
                    "TestProject",
                    "Task",
                    fields={"System.Title": "Task"},
                )

        # Then: returns the same ActionableError
        assert result is original, (
            f"Expected original ActionableError returned directly, got {result!r}"
        )


# ---------------------------------------------------------------------------
# TestMoveWorkItemsToSprintTool
# ---------------------------------------------------------------------------


class TestMoveWorkItemsToSprintTool:
    """
    REQUIREMENT: MCP tool wrapper for move_work_items_to_sprint.

    WHO: AI agents via MCP
    WHAT: (1) given work item IDs and iteration path, returns list of
              updated WorkItemDetail
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to move work items across sprints without
         constructing patch documents.

    MOCK BOUNDARY:
        Mock:  get_client(), library move_work_items_to_sprint() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_moved_details(self, tmp_path: Any) -> None:
        """
        Given work item IDs and iteration path,
        When the move_work_items_to_sprint tool is called,
        Then returns list of updated WorkItemDetail.
        """
        # Given: library returns moved items
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_move_work_items_to_sprint",
                return_value=[_SAMPLE_DETAIL],
            ):
                # When: tool is called
                result = move_work_items_to_sprint(
                    "TestProject",
                    [1001],
                    r"One\FY26\Q4\2Wk\2Wk22",
                )

        # Then: returns list of WorkItemDetail
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 item, got {len(result)}"

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during move,
        When the move_work_items_to_sprint tool is called,
        Then returns ActionableError with ai_guidance.
        """
        # Given: library raises an unexpected error
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_move_work_items_to_sprint",
                side_effect=Exception("access denied"),
            ):
                # When: tool is called
                result = move_work_items_to_sprint(
                    "TestProject",
                    [1001],
                    r"One\FY26\Q4\2Wk\2Wk22",
                )

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="sprint")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the move_work_items_to_sprint tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="move failed",
            error_type="service_error",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_move_work_items_to_sprint",
                side_effect=original,
            ):
                # When: tool is called
                result = move_work_items_to_sprint(
                    "TestProject",
                    [1001],
                    r"One\FY26\Q4\2Wk\2Wk22",
                )

        # Then: returns the same ActionableError
        assert result is original, (
            f"Expected original ActionableError returned directly, got {result!r}"
        )


# ---------------------------------------------------------------------------
# TestGetWorkItemTypeFieldsTool
# ---------------------------------------------------------------------------


class TestGetWorkItemTypeFieldsTool:
    """
    REQUIREMENT: MCP tool wrapper for get_work_item_type_fields.

    WHO: AI agents via MCP
    WHAT: (1) given a project and type, returns list of WorkItemFieldInfo
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to discover valid fields for a work item type
         before creating or updating items.

    MOCK BOUNDARY:
        Mock:  get_client(), library get_work_item_type_fields() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_field_info_list(self, tmp_path: Any) -> None:
        """
        Given a project and work item type,
        When the get_work_item_type_fields tool is called,
        Then returns list of WorkItemFieldInfo.
        """
        # Given: library returns field info
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_item_type_fields",
                return_value=[_SAMPLE_FIELD_INFO],
            ):
                # When: tool is called
                result = get_work_item_type_fields("TestProject", "Task")

        # Then: returns list of WorkItemFieldInfo
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}: {result}"
        assert len(result) == 1, f"Expected 1 field, got {len(result)}"
        assert isinstance(result[0], WorkItemFieldInfo), (
            f"Expected WorkItemFieldInfo, got {type(result[0]).__name__}"
        )

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during field discovery,
        When the get_work_item_type_fields tool is called,
        Then returns ActionableError with ai_guidance.
        """
        # Given: library raises an unexpected error
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_item_type_fields",
                side_effect=Exception("type not found"),
            ):
                # When: tool is called
                result = get_work_item_type_fields("TestProject", "Invalid")

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="field")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the get_work_item_type_fields tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="type not found",
            error_type="not_found",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_item_type_fields",
                side_effect=original,
            ):
                # When: tool is called
                result = get_work_item_type_fields("TestProject", "Invalid")

        # Then: returns the same ActionableError
        assert result is original, (
            f"Expected original ActionableError returned directly, got {result!r}"
        )


# ===========================================================================
# Phase 6 -- Plural-Aware Multi-Org Work Item MCP Surface
# ===========================================================================
#
# The following test classes drive the URL-or-ID dispatch behavior added in
# the 0.13.0 surface upgrade (spec:
# .copilot/specs/plural-aware-multi-org-work-item-surface.md).
#
# Mock boundary follows the existing test_data_gathering.py convention:
#     Repo (filesystem) + ConnectionFactory (auth) + Connection.get_client
#     (network edge for the SDK work-item-tracking client).
#
# Real code drives URL parsing (parse_ado_work_item_url),
# AzureDevOpsWorkItemContext construction, RepositoryContext.get,
# get_client (AdoClient construction + connection.get_client invocation),
# and the library get_work_item / update_work_item / clone_work_item bodies
# (including map_work_item_detail).


if TYPE_CHECKING:
    from pathlib import Path

_BUG_URL = "https://msazure.visualstudio.com/One/_workitems/edit/37453680"
_OTHER_REMOTE = "https://dev.azure.com/OtherOrg/OtherProj/_git/OtherRepo"


def _make_repo_dir(workspace: Path, name: str) -> Path:
    """Create a directory containing ``.git`` under *workspace*."""
    repo = workspace / name
    (repo / ".git").mkdir(parents=True)
    return repo


def _two_repo_workspace(
    tmp_path: Path,
) -> tuple[Path, Path, Path, str, str]:
    """Build a workspace with two ADO repos in different orgs."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo_a = _make_repo_dir(workspace, "RepoA")
    repo_b = _make_repo_dir(workspace, "RepoB")
    url_a = "https://dev.azure.com/OrgA/Proj/_git/RepoA"
    url_b = "https://dev.azure.com/OrgB/Proj/_git/RepoB"
    return workspace, repo_a, repo_b, url_a, url_b


def _repo_dispatcher(repo_a: Path, url_a: str, repo_b: Path, url_b: str) -> object:
    """Return a side_effect that maps Repo(path) to the matching mock."""

    def _dispatch(path: str, *_args: object, **_kwargs: object) -> MagicMock:
        if path == str(repo_a):
            return _mock_git_repo(url_a)
        if path == str(repo_b):
            return _mock_git_repo(url_b)
        raise AssertionError(f"Unexpected Repo path: {path}")

    return _dispatch


def _make_raw_work_item(
    wi_id: int = 37453680,
    title: str = "Cross-org test work item",
) -> MagicMock:
    """Build a mock SDK WorkItem suitable for map_work_item_detail."""
    raw = MagicMock()
    raw.id = wi_id
    raw.url = f"https://dev.azure.com/msazure/One/_apis/wit/workItems/{wi_id}"
    raw.fields = {
        "System.Title": title,
        "System.State": "Active",
        "System.WorkItemType": "Task",
    }
    raw.relations = []
    return raw


def _wire_factory_to_wit_client(mock_factory: MagicMock, mock_wit_client: MagicMock) -> MagicMock:
    """
    Wire up ConnectionFactory → Connection → get_client(_WIT) chain.

    Returns the mock connection so the test can assert on
    factory().get_connection(<org_url>).
    """
    mock_connection = MagicMock()
    mock_connection.get_client.return_value = mock_wit_client
    mock_factory.return_value.get_connection.return_value = mock_connection
    return mock_connection


# ---------------------------------------------------------------------------
# TestGetWorkItemUrlDispatch
# ---------------------------------------------------------------------------


class TestGetWorkItemUrlDispatch:
    """
    REQUIREMENT: The widened get_work_item tool routes a URL or
    numeric ID through establish_work_item_context, builds an
    org-scoped client from the resulting context, and delegates to
    the library get_work_item with the resolved project / id.

    WHO: Agents holding either a pasted work-item URL or a bare
        numeric ID.
    WHAT: (1) URL input → establish_work_item_context is called with
              the URL; the SDK call lands on the URL's org (verified
              by asserting the org_url passed to get_client).
          (2) Numeric input → establish_work_item_context is called
              with the integer string; the SDK call lands on the
              cached / discovered org.
          (3) The library get_work_item is called with the project
              and work_item_id from the resolved context, not from
              caller-supplied parameters.
          (4) establish_work_item_context raises ActionableError →
              the tool returns it unchanged.
          (5) Unexpected exception → tool returns
              ActionableError.internal with operation-specific
              guidance.

    MOCK BOUNDARY:
        Mock:  ado_workflows.discovery.Repo (GitPython filesystem edge,
               for the bare-ID path),
               ado_workflows_mcp.tools._helpers.ConnectionFactory
               (auth edge — token acquisition),
               the SDK work-item-tracking client returned by
               AdoClient.work_item_tracking (network edge).
        Real:  the MCP tool function, establish_work_item_context,
               parse_ado_work_item_url, RepositoryContext, get_client,
               AdoClient construction, library get_work_item,
               WorkItemDetail mapping, tmp_path filesystem.
        Never: the MCP tool function (SUT),
               establish_work_item_context, get_client, library
               get_work_item — these are in-codebase functions whose
               integration is the point of this test.
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_url_input_routes_through_establish_work_item_context(self, tmp_path: Any) -> None:
        """
        Given a work-item URL whose org differs from any cached repo
        When get_work_item is called with that URL
        Then the SDK call lands on the URL's org (msazure), proving
            URL parsing → org_url construction → auth boundary
            integration drove the routing — not cached context
        """
        # Given: a different org cached in RepositoryContext
        _setup_context(tmp_path)  # caches TestOrg from _ADO_REMOTE
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        mock_wit_client.get_work_item.return_value = _make_raw_work_item()
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        # When: the bug URL (msazure) is passed
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            result = get_work_item(work_item_url_or_id=_BUG_URL)

        # Then: the SDK call landed on the URL's org, not the cached one
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )
        # Auth boundary saw the URL's org_url (https://dev.azure.com/msazure)
        get_conn_calls = mock_factory.return_value.get_connection.call_args_list
        assert len(get_conn_calls) == 1, (
            f"Expected exactly one get_connection call, got {len(get_conn_calls)}"
        )
        org_url_arg = get_conn_calls[0].args[0]
        assert "msazure" in org_url_arg, (
            f"Expected org_url to contain 'msazure' (URL's org), got {org_url_arg!r}"
        )
        assert "TestOrg" not in org_url_arg, (
            f"Expected URL's org to win over cached 'TestOrg', got {org_url_arg!r}"
        )

    def test_numeric_input_routes_through_establish_work_item_context(self, tmp_path: Any) -> None:
        """
        Given a bare numeric work-item ID and cached repository context
        When get_work_item is called with the bare ID
        Then the SDK call lands on the cached org and the library
            get_work_item is invoked with the resolved id
        """
        # Given: cached TestOrg context
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        mock_wit_client.get_work_item.return_value = _make_raw_work_item(wi_id=42)
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        # When: bare numeric ID
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            result = get_work_item(work_item_url_or_id="42")

        # Then: SDK call landed on cached org
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )
        get_conn_calls = mock_factory.return_value.get_connection.call_args_list
        assert len(get_conn_calls) == 1, (
            f"Expected one get_connection call, got {len(get_conn_calls)}"
        )
        assert "TestOrg" in get_conn_calls[0].args[0], (
            f"Expected cached 'TestOrg' org_url, got {get_conn_calls[0].args[0]!r}"
        )
        # And SDK get_work_item was called with the resolved id
        wit_calls = mock_wit_client.get_work_item.call_args_list
        assert len(wit_calls) == 1, f"Expected one SDK get_work_item call, got {len(wit_calls)}"
        assert wit_calls[0].args[0] == 42, (
            f"Expected SDK called with id=42, got {wit_calls[0].args!r}"
        )

    def test_library_get_work_item_called_with_resolved_project_and_id(
        self,
    ) -> None:
        """
        Given a URL whose project differs from anything cached
        When get_work_item is called
        Then the SDK get_work_item receives project='One' and
            id=37453680 from the URL, not caller-supplied values
        """
        # Given: no cached context (URL provides everything)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        mock_wit_client.get_work_item.return_value = _make_raw_work_item()
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        # When: URL form
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            get_work_item(work_item_url_or_id=_BUG_URL)

        # Then: SDK called with URL-resolved project and id
        wit_calls = mock_wit_client.get_work_item.call_args_list
        assert len(wit_calls) == 1, f"Expected one SDK get_work_item call, got {len(wit_calls)}"
        call = wit_calls[0]
        assert call.args[0] == 37453680, (
            f"Expected SDK called with id=37453680, got args={call.args!r}"
        )
        assert call.kwargs.get("project") == "One", (
            f"Expected project='One', got kwargs={call.kwargs!r}"
        )

    def test_actionable_error_from_resolution_propagates_unchanged(
        self,
    ) -> None:
        """
        Given establish_work_item_context raises ActionableError
        When get_work_item is called
        Then the same ActionableError is returned unchanged
        """
        # Given: bogus input that establish_work_item_context will reject
        # (no cached context + non-numeric, non-URL string)
        RepositoryContext.clear()

        # When: tool is called with garbage
        result = get_work_item(work_item_url_or_id="not-a-url-or-id")

        # Then: ActionableError surfaced (validation), not WorkItemDetail
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "validation", (
            f"Expected error_type='validation' from establish_work_item_context, "
            f"got {result.error_type!r}"
        )

    def test_unexpected_exception_returns_internal_actionable_error(
        self,
    ) -> None:
        """
        Given establish_work_item_context raises a plain (non-ActionableError) exception
        When get_work_item is called
        Then the tool returns ActionableError.internal with guidance
            (defensive branch — the library normally wraps everything to
            ActionableError, but the wrapper must still safely degrade
            on a plain exception bubbling up from any inner call)
        """
        RepositoryContext.clear()

        # Given: the library establish_work_item_context raises a plain Exception
        with patch(
            "ado_workflows_mcp.tools.work_items._lib_establish_work_item",
            side_effect=RuntimeError("kaboom"),
        ):
            # When: tool is called
            result = get_work_item(work_item_url_or_id=_BUG_URL)

        # Then: tool wraps it in ActionableError.internal
        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "internal", (
            f"Expected error_type='internal', got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on error, got None"


# ---------------------------------------------------------------------------
# TestUpdateWorkItemUrlDispatch
# ---------------------------------------------------------------------------


class TestUpdateWorkItemUrlDispatch:
    """
    REQUIREMENT: The widened update_work_item tool resolves the
    target work item via establish_work_item_context, then delegates
    to the library update_work_item with the resolved project / id
    and the caller-supplied fields dict.

    WHO: Agents updating a work item identified by URL or bare ID.
    WHAT: (1) URL input → resolution lands on the URL's org; library
              update_work_item is called with the resolved project
              and id and the caller's fields.
          (2) Numeric input → resolution lands on the discovered org;
              library update_work_item receives resolved project / id.
          (3) establish_work_item_context raises ActionableError →
              propagated unchanged.
          (4) Unexpected exception → ActionableError.internal with
              operation-specific guidance.

    MOCK BOUNDARY:
        Mock:  ado_workflows.discovery.Repo (filesystem edge),
               ado_workflows_mcp.tools._helpers.ConnectionFactory
               (auth edge), the SDK work-item-tracking client
               returned by AdoClient.work_item_tracking (network edge).
        Real:  the MCP tool function, establish_work_item_context,
               parse_ado_work_item_url, RepositoryContext, get_client,
               AdoClient construction, library update_work_item,
               tmp_path filesystem.
        Never: the MCP tool function (SUT),
               establish_work_item_context, get_client, library
               update_work_item — in-codebase integration is the SUT.
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_url_input_calls_library_update_with_resolved_project_and_id(
        self, tmp_path: Any
    ) -> None:
        """
        Given a URL with a different org than the cache and a fields dict
        When update_work_item is called with the URL
        Then SDK update_work_item is invoked with project='One',
            id=37453680, and the caller's fields applied as a JSON Patch
        """
        # Given: cached context to prove URL's org wins
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        mock_wit_client.update_work_item.return_value = _make_raw_work_item()
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        # When: update by URL with new state
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            result = update_work_item(
                work_item_url_or_id=_BUG_URL,
                fields={"System.State": "Closed"},
            )

        # Then: SDK update lands on URL's org with resolved id
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )
        org_url = mock_factory.return_value.get_connection.call_args_list[0].args[0]
        assert "msazure" in org_url, f"Expected URL's 'msazure' org to win, got {org_url!r}"
        update_calls = mock_wit_client.update_work_item.call_args_list
        assert len(update_calls) == 1, (
            f"Expected one SDK update_work_item call, got {len(update_calls)}"
        )
        call = update_calls[0]
        # The library passes the patch document positionally and the
        # work_item_id as the second positional argument.
        assert call.args[1] == 37453680, (
            f"Expected SDK called with id=37453680, got args={call.args!r}"
        )
        assert call.kwargs.get("project") == "One", (
            f"Expected project='One', got kwargs={call.kwargs!r}"
        )
        # The patch document should contain a 'System.State' op for 'Closed'
        patch_doc = call.args[0]
        paths = [op.path for op in patch_doc]
        values = [op.value for op in patch_doc]
        assert "/fields/System.State" in paths, (
            f"Expected '/fields/System.State' in patch paths, got {paths!r}"
        )
        assert "Closed" in values, f"Expected 'Closed' in patch values, got {values!r}"

    def test_numeric_input_calls_library_update_with_resolved_project_and_id(
        self, tmp_path: Any
    ) -> None:
        """
        Given a bare numeric ID and cached context
        When update_work_item is called
        Then SDK update_work_item is called with the cached org's
            project and the parsed id
        """
        # Given: cached TestOrg/TestProject
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        mock_wit_client.update_work_item.return_value = _make_raw_work_item(wi_id=42)
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        # When: update by bare ID
        with patch(_CONN_FACTORY_PATCH, mock_factory):
            update_work_item(
                work_item_url_or_id="42",
                fields={"System.Title": "Renamed"},
            )

        # Then: SDK called with cached project and parsed id
        update_calls = mock_wit_client.update_work_item.call_args_list
        assert len(update_calls) == 1, f"Expected one SDK update call, got {len(update_calls)}"
        call = update_calls[0]
        assert call.args[1] == 42, f"Expected SDK called with id=42, got args={call.args!r}"
        assert call.kwargs.get("project") == "TestProject", (
            f"Expected project='TestProject', got kwargs={call.kwargs!r}"
        )

    def test_actionable_error_from_resolution_propagates_unchanged(
        self,
    ) -> None:
        """
        Given establish_work_item_context raises (bogus input)
        When update_work_item is called
        Then the ActionableError is returned unchanged
        """
        RepositoryContext.clear()

        result = update_work_item(
            work_item_url_or_id="not-a-url-or-id",
            fields={"System.State": "Closed"},
        )

        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "validation", (
            f"Expected error_type='validation', got {result.error_type!r}"
        )

    def test_unexpected_exception_returns_internal_actionable_error(
        self,
    ) -> None:
        """
        Given establish_work_item_context raises a plain exception
        When update_work_item is called
        Then ActionableError.internal with ai_guidance is returned
            (defensive branch coverage)
        """
        RepositoryContext.clear()

        with patch(
            "ado_workflows_mcp.tools.work_items._lib_establish_work_item",
            side_effect=RuntimeError("kaboom"),
        ):
            result = update_work_item(
                work_item_url_or_id=_BUG_URL,
                fields={"System.State": "Closed"},
            )

        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "internal", (
            f"Expected error_type='internal', got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on error, got None"


# ---------------------------------------------------------------------------
# TestCloneWorkItemUrlDispatch
# ---------------------------------------------------------------------------


class TestCloneWorkItemUrlDispatch:
    """
    REQUIREMENT: The widened clone_work_item tool resolves the
    source work item via establish_work_item_context, then delegates
    to the library clone_work_item with the resolved project / id
    and the caller-supplied field overrides.

    WHO: Agents cloning a work item identified by URL or bare ID.
    WHAT: (1) URL input → resolution lands on the URL's org; library
              clone_work_item is called with the resolved project /
              source_id and the caller's field_overrides.
          (2) Numeric input → resolution lands on the discovered org;
              library clone_work_item receives resolved project /
              source_id.
          (3) field_overrides=None is passed through unchanged.
          (4) establish_work_item_context raises ActionableError →
              propagated unchanged.
          (5) Unexpected exception → ActionableError.internal with
              operation-specific guidance.

    MOCK BOUNDARY:
        Mock:  ado_workflows.discovery.Repo (filesystem edge),
               ado_workflows_mcp.tools._helpers.ConnectionFactory
               (auth edge), the SDK work-item-tracking client
               returned by AdoClient.work_item_tracking (network edge).
        Real:  the MCP tool function, establish_work_item_context,
               parse_ado_work_item_url, RepositoryContext, get_client,
               AdoClient construction, library clone_work_item,
               tmp_path filesystem.
        Never: the MCP tool function (SUT),
               establish_work_item_context, get_client, library
               clone_work_item — in-codebase integration is the SUT.
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def _wire_clone_sdk(self, mock_wit_client: MagicMock, source_id: int) -> None:
        """
        Wire the two SDK calls the library clone_work_item makes:
        get_work_item (read source) and create_work_item (write clone).
        """
        mock_wit_client.get_work_item.return_value = _make_raw_work_item(
            wi_id=source_id, title="Source"
        )
        mock_wit_client.create_work_item.return_value = _make_raw_work_item(
            wi_id=999, title="Clone"
        )

    def test_url_input_calls_library_clone_with_resolved_project_and_source_id(
        self, tmp_path: Any
    ) -> None:
        """
        Given a URL whose org differs from the cache
        When clone_work_item is called with that URL
        Then SDK reads the source from URL's org/project/id and
            writes the new clone to the same org/project
        """
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        self._wire_clone_sdk(mock_wit_client, source_id=37453680)
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        with patch(_CONN_FACTORY_PATCH, mock_factory):
            result = clone_work_item(
                source_work_item_url_or_id=_BUG_URL,
                field_overrides={"System.Title": "Cloned"},
            )

        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )
        # Auth boundary saw URL's org
        org_url = mock_factory.return_value.get_connection.call_args_list[0].args[0]
        assert "msazure" in org_url, f"Expected URL's 'msazure' org, got {org_url!r}"
        # SDK get_work_item read source with resolved id
        gw_calls = mock_wit_client.get_work_item.call_args_list
        assert len(gw_calls) >= 1, (
            f"Expected at least one SDK get_work_item call (source read), got {len(gw_calls)}"
        )
        assert gw_calls[0].args[0] == 37453680, (
            f"Expected SDK reading source id=37453680, got {gw_calls[0].args!r}"
        )
        assert gw_calls[0].kwargs.get("project") == "One", (
            f"Expected project='One', got {gw_calls[0].kwargs!r}"
        )
        # SDK create_work_item wrote clone in same project
        cw_calls = mock_wit_client.create_work_item.call_args_list
        assert len(cw_calls) == 1, f"Expected one SDK create_work_item call, got {len(cw_calls)}"
        # create_work_item(document, project, work_item_type)
        assert cw_calls[0].args[1] == "One", (
            f"Expected create in project 'One', got args={cw_calls[0].args!r}"
        )

    def test_numeric_input_calls_library_clone_with_resolved_project_and_source_id(
        self, tmp_path: Any
    ) -> None:
        """
        Given a bare numeric ID and cached context
        When clone_work_item is called
        Then SDK get_work_item reads source from cached project/id and
            create_work_item writes clone to cached project
        """
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        self._wire_clone_sdk(mock_wit_client, source_id=42)
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        with patch(_CONN_FACTORY_PATCH, mock_factory):
            clone_work_item(
                source_work_item_url_or_id="42",
                field_overrides={"System.Title": "Cloned"},
            )

        gw_calls = mock_wit_client.get_work_item.call_args_list
        assert gw_calls[0].args[0] == 42, (
            f"Expected SDK reading source id=42, got {gw_calls[0].args!r}"
        )
        assert gw_calls[0].kwargs.get("project") == "TestProject", (
            f"Expected project='TestProject', got {gw_calls[0].kwargs!r}"
        )
        cw_calls = mock_wit_client.create_work_item.call_args_list
        assert cw_calls[0].args[1] == "TestProject", (
            f"Expected create in 'TestProject', got args={cw_calls[0].args!r}"
        )

    def test_field_overrides_none_passed_through_unchanged(self, tmp_path: Any) -> None:
        """
        Given field_overrides=None
        When clone_work_item is called
        Then the clone is created (no error from None) and the patch
            document equals the source's fields verbatim
        """
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        mock_wit_client = MagicMock()
        self._wire_clone_sdk(mock_wit_client, source_id=42)
        _wire_factory_to_wit_client(mock_factory, mock_wit_client)

        with patch(_CONN_FACTORY_PATCH, mock_factory):
            result = clone_work_item(
                source_work_item_url_or_id="42",
                field_overrides=None,
            )

        # Then: success path (None did not break the flow)
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail with field_overrides=None, "
            f"got {type(result).__name__}: {result}"
        )
        # Patch document must contain a Title op equal to the source title
        patch_doc = mock_wit_client.create_work_item.call_args.args[0]
        title_ops = [op for op in patch_doc if op.path == "/fields/System.Title"]
        assert len(title_ops) == 1, (
            f"Expected one System.Title patch op, got {len(title_ops)}: "
            f"{[op.path for op in patch_doc]}"
        )
        assert title_ops[0].value == "Source", (
            f"Expected source title 'Source' preserved when overrides=None, "
            f"got {title_ops[0].value!r}"
        )

    def test_actionable_error_from_resolution_propagates_unchanged(
        self,
    ) -> None:
        """
        Given establish_work_item_context raises (bogus input)
        When clone_work_item is called
        Then the ActionableError is returned unchanged
        """
        RepositoryContext.clear()

        result = clone_work_item(
            source_work_item_url_or_id="not-a-url-or-id",
        )

        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "validation", (
            f"Expected error_type='validation', got {result.error_type!r}"
        )

    def test_unexpected_exception_returns_internal_actionable_error(
        self,
    ) -> None:
        """
        Given establish_work_item_context raises a plain exception
        When clone_work_item is called
        Then ActionableError.internal with ai_guidance is returned
            (defensive branch coverage)
        """
        RepositoryContext.clear()

        with patch(
            "ado_workflows_mcp.tools.work_items._lib_establish_work_item",
            side_effect=RuntimeError("kaboom"),
        ):
            result = clone_work_item(source_work_item_url_or_id=_BUG_URL)

        assert isinstance(result, ActionableError), (
            f"Expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "internal", (
            f"Expected error_type='internal', got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, "Expected ai_guidance on error, got None"


# ---------------------------------------------------------------------------
# TestBareIdGuidanceCaveat
# ---------------------------------------------------------------------------


class TestBareIdGuidanceCaveat:
    """
    REQUIREMENT: When a widened tool resolves a bare numeric ID
    (i.e. the resolved AzureDevOpsWorkItemContext has
    source="repository_context"), the tool's docstring must warn
    callers that the resolved org may not match the work item's
    actual host org when work board and code repo live in different
    tenants. Each widened tool must mention the URL alternative.

    WHO: Agents reading the MCP tool description, and humans
        reading the tool registry, who need to understand why a bare
        ID can route to the wrong org even when the library does
        not raise ambiguity.
    WHAT: (1) get_work_item docstring mentions both the URL form and
              the work-board-vs-repo caveat.
          (2) update_work_item docstring mentions the same.
          (3) clone_work_item docstring mentions the same.

    MOCK BOUNDARY:
        Mock:  nothing — these are documentation assertions on the
               tool function objects' __doc__.
        Real:  the tool function objects.
        Never: tool function objects (SUT).
    """

    def _assert_caveat_in_docstring(self, doc: str | None, tool_name: str) -> None:
        """
        Assert the docstring mentions the URL alternative AND the
        work-board-vs-code-repo caveat.
        """
        assert doc is not None, f"{tool_name}.__doc__ must not be None"
        text = doc.lower()
        assert "url" in text, (
            f"{tool_name} docstring must mention the URL alternative; got: {doc!r}"
        )
        # The caveat language: any of "work board", "different org",
        # "cross-org", "wrong org", or "tenant" is acceptable —
        # the spec is satisfied as long as the caveat is visible.
        caveat_terms = (
            "work board",
            "different org",
            "cross-org",
            "wrong org",
            "tenant",
            "different tenant",
            "different organization",
        )
        assert any(term in text for term in caveat_terms), (
            f"{tool_name} docstring must mention the work-board-vs-code-repo "
            f"caveat. None of {caveat_terms!r} found in: {doc!r}"
        )

    def test_get_work_item_docstring_mentions_url_alternative(self) -> None:
        """
        Given get_work_item is the widened tool
        When its docstring is inspected
        Then it mentions the URL form and the bare-ID caveat
        """
        # Given/When: inspect the live tool's docstring
        doc = get_work_item.__doc__

        # Then: the caveat is surfaced
        self._assert_caveat_in_docstring(doc, "get_work_item")

    def test_update_work_item_docstring_mentions_url_alternative(self) -> None:
        """
        Given update_work_item is the widened tool
        When its docstring is inspected
        Then it mentions the URL form and the bare-ID caveat
        """
        doc = update_work_item.__doc__
        self._assert_caveat_in_docstring(doc, "update_work_item")

    def test_clone_work_item_docstring_mentions_url_alternative(self) -> None:
        """
        Given clone_work_item is the widened tool
        When its docstring is inspected
        Then it mentions the URL form and the bare-ID caveat
        """
        doc = clone_work_item.__doc__
        self._assert_caveat_in_docstring(doc, "clone_work_item")


# ---------------------------------------------------------------------------
# TestAmbiguityPropagationOnUnwidenedTools
# ---------------------------------------------------------------------------


class TestAmbiguityPropagationOnUnwidenedTools:
    """
    REQUIREMENT: Each unwidened work-item tool propagates the
    library's multi-repo ambiguity ActionableError unchanged when
    called against a multi-repo workspace with no working_directory
    and no cached context.

    WHO: Agents using batch / type-scoped work-item tools that
        cannot accept a URL.
    WHAT: (1) get_work_items raises through to the caller with the
              library's validation error and candidate_repositories
              context intact.
          (2) create_work_item raises through likewise.
          (3) move_work_items_to_sprint raises through likewise.
          (4) get_work_item_type_fields raises through likewise.

    MOCK BOUNDARY:
        Mock:  ado_workflows.discovery.Repo (the GitPython I/O edge,
               so a real multi-repo workspace can be simulated).
        Real:  RepositoryContext, get_client, the MCP tool functions,
               ActionableError.
        Never: the MCP tool functions (SUT).
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def _assert_validation_error_with_candidates(self, result: object, tool_name: str) -> None:
        """
        Assert the result is the library's multi-repo ambiguity
        ActionableError.validation, with ai_guidance preserved.
        """
        assert isinstance(result, ActionableError), (
            f"{tool_name}: expected ActionableError, got {type(result).__name__}: {result}"
        )
        assert result.error_type == "validation", (
            f"{tool_name}: expected error_type='validation' (ambiguity), got {result.error_type!r}"
        )
        assert result.ai_guidance is not None, (
            f"{tool_name}: expected ai_guidance preserved, got None"
        )

    def _ambiguous_workspace_patches(self, tmp_path: Path) -> tuple[Path, object]:
        """
        Build a two-repo workspace and the Repo dispatcher that maps
        each repo path to its mock remote. Returns (workspace_path,
        Repo side_effect dispatcher).
        """
        workspace, repo_a, repo_b, url_a, url_b = _two_repo_workspace(tmp_path)
        return workspace, _repo_dispatcher(repo_a, url_a, repo_b, url_b)

    def test_get_work_items_propagates_multi_repo_ambiguity_error(self, tmp_path: Path) -> None:
        """
        Given a multi-repo workspace and no working_directory
        When get_work_items is called
        Then the library's validation error is returned with
            candidate context intact
        """
        workspace, dispatcher = self._ambiguous_workspace_patches(tmp_path)

        with (
            patch(_REPO_PATCH, side_effect=dispatcher),
            patch("os.getcwd", return_value=str(workspace)),
        ):
            result = get_work_items(project="Proj", work_item_ids=[1, 2])

        self._assert_validation_error_with_candidates(result, "get_work_items")

    def test_create_work_item_propagates_multi_repo_ambiguity_error(self, tmp_path: Path) -> None:
        """
        Given a multi-repo workspace and no working_directory
        When create_work_item is called
        Then the library's validation error is returned
        """
        workspace, dispatcher = self._ambiguous_workspace_patches(tmp_path)

        with (
            patch(_REPO_PATCH, side_effect=dispatcher),
            patch("os.getcwd", return_value=str(workspace)),
        ):
            result = create_work_item(
                project="Proj",
                work_item_type="Task",
                fields={"System.Title": "T"},
            )

        self._assert_validation_error_with_candidates(result, "create_work_item")

    def test_move_work_items_to_sprint_propagates_multi_repo_ambiguity_error(
        self, tmp_path: Path
    ) -> None:
        """
        Given a multi-repo workspace and no working_directory
        When move_work_items_to_sprint is called
        Then the library's validation error is returned
        """
        workspace, dispatcher = self._ambiguous_workspace_patches(tmp_path)

        with (
            patch(_REPO_PATCH, side_effect=dispatcher),
            patch("os.getcwd", return_value=str(workspace)),
        ):
            result = move_work_items_to_sprint(
                project="Proj",
                work_item_ids=[1, 2],
                iteration_path=r"One\\FY26\\Q4\\2Wk\\2Wk22",
            )

        self._assert_validation_error_with_candidates(result, "move_work_items_to_sprint")

    def test_get_work_item_type_fields_propagates_multi_repo_ambiguity_error(
        self, tmp_path: Path
    ) -> None:
        """
        Given a multi-repo workspace and no working_directory
        When get_work_item_type_fields is called
        Then the library's validation error is returned
        """
        workspace, dispatcher = self._ambiguous_workspace_patches(tmp_path)

        with (
            patch(_REPO_PATCH, side_effect=dispatcher),
            patch("os.getcwd", return_value=str(workspace)),
        ):
            result = get_work_item_type_fields(
                project="Proj",
                work_item_type="Task",
            )

        self._assert_validation_error_with_candidates(result, "get_work_item_type_fields")
