"""Tortoise model mirroring the MCP tools exposed from app views.

Rows are synced from the live MCP server on every startup. Toggling
``enabled`` off in the admin excludes that tool on the next start.
"""

from __future__ import annotations

from tortoise import fields

from core.models import TimestampedModel


class MCPTool(TimestampedModel):
    """One MCP tool, derived from a FastAPI view (operation)."""

    name = fields.CharField(max_length=128, unique=True)
    description = fields.TextField(null=True)
    method = fields.CharField(max_length=10, default="")
    path = fields.CharField(max_length=255, default="")
    input_schema = fields.JSONField(null=True)
    #: Uncheck in the admin to stop exposing this tool (applied on restart).
    enabled = fields.BooleanField(default=True)

    class Meta:
        table = "mcp_tools"

    def __str__(self) -> str:
        return self.name
