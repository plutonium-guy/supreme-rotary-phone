"""Admin registration for MCP tools — shows every exposed tool in the dashboard."""

from core.admin import register_model

from apps.mcp.models import MCPTool

register_model(
    MCPTool,
    list_display=("id", "name", "method", "path", "enabled", "updated_at"),
    search_fields=("name", "path"),
    list_filter=("enabled", "method"),
)
