"""App configuration for the MCP registry app."""

from core.apps import AppConfig


class McpConfig(AppConfig):
    name = "apps.mcp"
    label = "mcp"
    verbose_name = "MCP Tools"
    # This app only mirrors tools into the admin; it is not itself a tool.
    expose_mcp = False
