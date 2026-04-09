"""
BDD tests for tools/work_items.py — work item MCP tools.

Covers:
    TestGetWorkItemTool — fetch a single work item by ID
    TestGetWorkItemsTool — batch-fetch multiple work items by ID
    TestUpdateWorkItemTool — update fields on an existing work item
    TestCreateWorkItemTool — create a new work item of any type
    TestMoveWorkItemsToSprintTool — move work items to a target sprint
    TestCloneWorkItemTool — clone a work item with optional overrides
    TestGetWorkItemTypeFieldsTool — discover fields for a work item type

Public API surface (from src/ado_workflows_mcp/tools/work_items.py):
    get_work_item(project, work_item_id, *, working_directory)
        -> WorkItemDetail | ActionableError
    get_work_items(project, work_item_ids, *, working_directory)
        -> list[WorkItemDetail] | ActionableError
    update_work_item(project, work_item_id, *, fields, working_directory)
        -> WorkItemDetail | ActionableError
    create_work_item(project, work_item_type, *, fields, parent_id, working_directory)
        -> WorkItemDetail | ActionableError
    move_work_items_to_sprint(project, work_item_ids, iteration_path, *, working_directory)
        -> list[WorkItemDetail] | ActionableError
    clone_work_item(project, source_id, *, field_overrides, working_directory)
        -> WorkItemDetail | ActionableError
    get_work_item_type_fields(project, work_item_type, *, working_directory)
        -> list[WorkItemFieldInfo] | ActionableError
"""

from __future__ import annotations

from typing import Any
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
# TestGetWorkItemTool
# ---------------------------------------------------------------------------


class TestGetWorkItemTool:
    """
    REQUIREMENT: MCP tool wrapper for get_work_item.

    WHO: AI agents via MCP
    WHAT: (1) given a valid work item ID, returns WorkItemDetail
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to fetch a single work item by ID without managing
         ADO authentication or SDK details.

    MOCK BOUNDARY:
        Mock:  get_client(), library get_work_item() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_work_item_detail(self, tmp_path: Any) -> None:
        """
        Given a valid work item ID,
        When the get_work_item tool is called,
        Then returns WorkItemDetail.
        """
        # Given: library returns a work item
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_item",
                return_value=_SAMPLE_DETAIL,
            ):
                # When: tool is called
                result = get_work_item("TestProject", 1001)

        # Then: returns WorkItemDetail
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )
        assert result.id == 1001, f"Expected id=1001, got {result.id}"

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during work item fetch,
        When the get_work_item tool is called,
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
                "ado_workflows_mcp.tools.work_items._lib_get_work_item",
                side_effect=Exception("service unavailable"),
            ):
                # When: tool is called
                result = get_work_item("TestProject", 9999)

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="work item")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the get_work_item tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="item not found",
            error_type="not_found",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_get_work_item",
                side_effect=original,
            ):
                # When: tool is called
                result = get_work_item("TestProject", 9999)

        # Then: returns the same ActionableError
        assert result is original, (
            f"Expected original ActionableError returned directly, got {result!r}"
        )


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
# TestUpdateWorkItemTool
# ---------------------------------------------------------------------------


class TestUpdateWorkItemTool:
    """
    REQUIREMENT: MCP tool wrapper for update_work_item.

    WHO: AI agents via MCP
    WHAT: (1) given a work item ID and fields, returns updated WorkItemDetail
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to update work item fields without constructing
         JSON Patch documents or managing SDK details.

    MOCK BOUNDARY:
        Mock:  get_client(), library update_work_item() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_updated_detail(self, tmp_path: Any) -> None:
        """
        Given a work item ID and fields dict,
        When the update_work_item tool is called,
        Then returns updated WorkItemDetail.
        """
        # Given: library returns updated item
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_update_work_item",
                return_value=_SAMPLE_DETAIL,
            ):
                # When: tool is called
                result = update_work_item(
                    "TestProject",
                    1001,
                    fields={"System.State": "Closed"},
                )

        # Then: returns WorkItemDetail
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during update,
        When the update_work_item tool is called,
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
                "ado_workflows_mcp.tools.work_items._lib_update_work_item",
                side_effect=Exception("field not valid"),
            ):
                # When: tool is called
                result = update_work_item(
                    "TestProject",
                    1001,
                    fields={"System.State": "Closed"},
                )

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="work item")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the update_work_item tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="update failed",
            error_type="service_error",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_update_work_item",
                side_effect=original,
            ):
                # When: tool is called
                result = update_work_item(
                    "TestProject",
                    1001,
                    fields={"System.State": "Closed"},
                )

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
# TestCloneWorkItemTool
# ---------------------------------------------------------------------------


class TestCloneWorkItemTool:
    """
    REQUIREMENT: MCP tool wrapper for clone_work_item.

    WHO: AI agents via MCP
    WHAT: (1) given a source work item ID, returns cloned WorkItemDetail
          (2) given a service error, returns ActionableError with ai_guidance
          (3) given an ActionableError from the library, returns it directly
    WHY: Enables agents to clone work items across sprints without managing
         field copying or parent link preservation.

    MOCK BOUNDARY:
        Mock:  get_client(), library clone_work_item() — auth + SDK
        Real:  MCP tool function
        Never: nothing
    """

    def setup_method(self) -> None:
        """Reset global context between tests."""
        RepositoryContext.clear()

    def test_success_returns_cloned_detail(self, tmp_path: Any) -> None:
        """
        Given a source work item ID,
        When the clone_work_item tool is called,
        Then returns cloned WorkItemDetail.
        """
        # Given: library returns cloned item
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_clone_work_item",
                return_value=_SAMPLE_DETAIL,
            ):
                # When: tool is called
                result = clone_work_item("TestProject", 1001)

        # Then: returns WorkItemDetail
        assert isinstance(result, WorkItemDetail), (
            f"Expected WorkItemDetail, got {type(result).__name__}: {result}"
        )

    def test_failure_returns_actionable_error_with_guidance(self, tmp_path: Any) -> None:
        """
        Given an error during clone,
        When the clone_work_item tool is called,
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
                "ado_workflows_mcp.tools.work_items._lib_clone_work_item",
                side_effect=Exception("source not found"),
            ):
                # When: tool is called
                result = clone_work_item("TestProject", 9999)

        # Then: returns ActionableError with appropriate ai_guidance
        _assert_actionable_error_with_guidance(result, operation_hint="clone")

    def test_library_actionable_error_returned_directly(self, tmp_path: Any) -> None:
        """
        Given an ActionableError raised by the library,
        When the clone_work_item tool is called,
        Then returns the same ActionableError without wrapping.
        """
        # Given: library raises ActionableError
        _setup_context(tmp_path)
        mock_factory = _mock_connection_factory()
        original = ActionableError(
            error="clone failed",
            error_type="service_error",
            service="ado",
        )
        with (
            patch(_CONN_FACTORY_PATCH, mock_factory),
            patch(_ADO_CLIENT_PATCH) as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            with patch(
                "ado_workflows_mcp.tools.work_items._lib_clone_work_item",
                side_effect=original,
            ):
                # When: tool is called
                result = clone_work_item("TestProject", 9999)

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
