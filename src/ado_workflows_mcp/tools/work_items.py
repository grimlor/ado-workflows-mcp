"""MCP tools for work item operations — read, create, update, move, clone, and field discovery."""

from __future__ import annotations

from typing import Any

from actionable_errors import ActionableError, AIGuidance
from ado_workflows.listing import (
    get_work_item as _lib_get_work_item,
    get_work_items as _lib_get_work_items,
)
from ado_workflows.models import WorkItemDetail, WorkItemFieldInfo
from ado_workflows.mutations import (
    clone_work_item as _lib_clone_work_item,
    create_work_item as _lib_create_work_item,
    get_work_item_type_fields as _lib_get_work_item_type_fields,
    move_work_items_to_sprint as _lib_move_work_items_to_sprint,
    update_work_item as _lib_update_work_item,
)

from ado_workflows_mcp.mcp_instance import mcp
from ado_workflows_mcp.tools._helpers import get_client


@mcp.tool()
def get_work_item(
    project: str,
    work_item_id: int,
    *,
    working_directory: str | None = None,
) -> WorkItemDetail | ActionableError:
    """
    Fetch a single work item by ID with full field data.

    Returns WorkItemDetail with all fields, area path, parent ID,
    and a full fields dict for type-specific access.

    Args:
        project: Azure DevOps project name.
        work_item_id: Numeric work item ID.
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_get_work_item(client, project, work_item_id)
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_work_item",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Work item fetch failed. Verify the work item ID and credentials.",
                checks=[
                    "Confirm the work item ID exists in the project",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )


@mcp.tool()
def get_work_items(
    project: str,
    work_item_ids: list[int],
    *,
    working_directory: str | None = None,
) -> list[WorkItemDetail] | ActionableError:
    """
    Batch-fetch multiple work items by ID with full field data.

    Args:
        project: Azure DevOps project name.
        work_item_ids: List of numeric work item IDs.
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_get_work_items(client, project, work_item_ids)
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_work_items",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Work item batch fetch failed. Verify IDs and credentials.",
                checks=[
                    "Confirm the work item IDs exist in the project",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )


@mcp.tool()
def update_work_item(
    project: str,
    work_item_id: int,
    *,
    fields: dict[str, Any],
    working_directory: str | None = None,
) -> WorkItemDetail | ActionableError:
    """
    Update fields on an existing work item.

    Accepts a dict of field reference names to values (e.g.
    ``{"System.State": "Closed", "System.IterationPath": "..."}``).

    Args:
        project: Azure DevOps project name.
        work_item_id: Numeric work item ID.
        fields: Dict mapping field reference names to new values.
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_update_work_item(client, project, work_item_id, fields=fields)
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="update_work_item",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Work item update failed. Verify field names and credentials.",
                checks=[
                    "Confirm the work item ID exists in the project",
                    "Verify field reference names are valid (use get_work_item_type_fields)",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )


@mcp.tool()
def create_work_item(
    project: str,
    work_item_type: str,
    *,
    fields: dict[str, Any],
    parent_id: int | None = None,
    working_directory: str | None = None,
) -> WorkItemDetail | ActionableError:
    """
    Create a new work item of any type.

    Args:
        project: Azure DevOps project name.
        work_item_type: Work item type (e.g. "Task", "Bug", "Product Backlog Item").
        fields: Dict mapping field reference names to values.
        parent_id: Optional parent work item ID for hierarchy linking.
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_create_work_item(
            client,
            project,
            work_item_type,
            fields=fields,
            parent_id=parent_id,
        )
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="create_work_item",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Work item creation failed. Verify type, fields, and credentials.",
                checks=[
                    "Confirm the work item type is valid for the project",
                    "Verify required fields are provided (use get_work_item_type_fields)",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )


@mcp.tool()
def move_work_items_to_sprint(
    project: str,
    work_item_ids: list[int],
    iteration_path: str,
    *,
    working_directory: str | None = None,
) -> list[WorkItemDetail] | ActionableError:
    r"""
    Move work items to a target sprint by updating their iteration path.

    Does not auto-include children — callers decide which IDs to move.

    Args:
        project: Azure DevOps project name.
        work_item_ids: List of work item IDs to move.
        iteration_path: Target iteration path (e.g. "One\\FY26\\Q4\\2Wk\\2Wk22").
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_move_work_items_to_sprint(
            client,
            project,
            work_item_ids,
            iteration_path,
        )
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="move_work_items_to_sprint",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Sprint move failed. Verify iteration path and credentials.",
                checks=[
                    "Confirm the iteration path exists in the project",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                    "Confirm the work item IDs exist",
                ],
            ),
        )


@mcp.tool()
def clone_work_item(
    project: str,
    source_id: int,
    *,
    field_overrides: dict[str, Any] | None = None,
    working_directory: str | None = None,
) -> WorkItemDetail | ActionableError:
    """
    Clone a work item into a new item of the same type.

    Copies all fields from the source, applies optional overrides,
    and preserves the parent link. Does not close the source.

    Args:
        project: Azure DevOps project name.
        source_id: Work item ID to clone from.
        field_overrides: Optional dict of fields to override in the clone.
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_clone_work_item(
            client,
            project,
            source_id,
            field_overrides=field_overrides,
        )
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="clone_work_item",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Clone failed. Verify source work item and credentials.",
                checks=[
                    "Confirm the source work item ID exists",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )


@mcp.tool()
def get_work_item_type_fields(
    project: str,
    work_item_type: str,
    *,
    working_directory: str | None = None,
) -> list[WorkItemFieldInfo] | ActionableError:
    """
    Discover available fields for a work item type in a project.

    Returns field metadata including name, reference name, type, and
    whether the field is required.

    Args:
        project: Azure DevOps project name.
        work_item_type: Work item type (e.g. "Task", "Bug").
        working_directory: Optional path for ADO context resolution.

    """
    try:
        client = get_client(working_directory)
        return _lib_get_work_item_type_fields(client, project, work_item_type)
    except ActionableError as exc:
        return exc
    except Exception as exc:
        return ActionableError.internal(
            service="ado-workflows-mcp",
            operation="get_work_item_type_fields",
            raw_error=str(exc),
            ai_guidance=AIGuidance(
                action_required="Field discovery failed. Verify work item type and credentials.",
                checks=[
                    "Confirm the work item type is valid for the project",
                    "Verify Azure DevOps authentication (run 'az login' if needed)",
                    "Confirm the project name is correct",
                ],
            ),
        )
