"""Patch ado_workflows.models so pydantic can resolve forward references.

The upstream ``models`` module guards ``ActionableError`` and ``datetime``
behind ``TYPE_CHECKING``.  With ``from __future__ import annotations``,
field annotations like ``list[ActionableError]`` become strings that
pydantic's ``TypeAdapter`` cannot resolve at runtime — the names simply
aren't in the module's namespace.

Importing this module injects the missing names so schema generation
succeeds when fastmcp's ``@mcp.tool()`` decorator runs.
"""

from datetime import datetime

import ado_workflows.models as _models
from actionable_errors import ActionableError

_models.ActionableError = ActionableError  # type: ignore[attr-defined]
_models.datetime = datetime  # type: ignore[attr-defined]
