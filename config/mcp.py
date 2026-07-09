"""MCP server integration (fastapi-mcp).

Every app view is exposed as an MCP tool automatically — the framework mounts
each app router with ``tags=[<app label>]``, and fastapi-mcp turns those
operations into tools. An app opts out with ``expose_mcp = False`` on its
AppConfig; ``settings.MCP_EXCLUDE_TAGS`` blocks tags globally.

The live tool list is synced into the ``MCPTool`` admin model so it is visible
(and toggleable) in the dashboard. Disabling a tool there excludes it on the
next start.

Built inside the app lifespan (after Tortoise is ready) so we can read the
disabled set from the database before constructing the server.
"""

from __future__ import annotations

from fastapi import FastAPI
from loguru import logger

from config.settings import settings
from core.apps import apps


def _excluded_tags() -> list[str]:
    tags = list(settings.MCP_EXCLUDE_TAGS)
    tags += [c.label for c in apps.configs if not getattr(c, "expose_mcp", True)]
    return sorted(set(tags))


async def configure_mcp(app: FastAPI) -> None:
    """Build, mount and sync the MCP server. Safe to fail (MCP is optional)."""
    if not settings.MCP_ENABLED:
        return
    try:
        from fastapi_mcp import FastApiMCP

        from apps.mcp.models import MCPTool

        disabled = {t.name for t in await MCPTool.filter(enabled=False)}

        # fastapi-mcp only honors one filter kind at a time, so resolve tag
        # exclusions and per-tool disables down to a single include list:
        # discover the tag-allowed operations, then drop the disabled ones.
        probe = FastApiMCP(app, exclude_tags=_excluded_tags() or None)
        probe.setup_server()
        tag_allowed = set(probe.operation_map.keys())
        exposed = sorted(tag_allowed - disabled)

        mcp = FastApiMCP(
            app, name=settings.MCP_SERVER_NAME, include_operations=exposed
        )
        mcp.setup_server()
        mcp.mount_http(app, settings.MCP_MOUNT_PATH)
        app.state.mcp = mcp

        await _sync_tools(mcp)
        logger.info(
            "MCP server mounted at {} ({} tools exposed, {} disabled)",
            settings.MCP_MOUNT_PATH,
            len(exposed),
            len(disabled),
        )
    except Exception as exc:  # noqa: BLE001 - MCP is optional
        logger.warning("MCP setup skipped: {}", exc)


async def _sync_tools(mcp) -> None:
    """Upsert the live tools into ``MCPTool`` and prune vanished ones.

    Disabled rows are preserved (they are excluded from the live server, so
    they would otherwise look 'vanished').
    """
    from apps.mcp.models import MCPTool

    current: set[str] = set()
    for tool in mcp.tools:
        current.add(tool.name)
        info = mcp.operation_map.get(tool.name, {})
        values = {
            "description": (tool.description or "")[:2000],
            "method": (info.get("method") or "").upper(),
            "path": info.get("path") or "",
            "input_schema": tool.inputSchema,
        }
        existing = await MCPTool.get_or_none(name=tool.name)
        if existing:
            await existing.update_from_dict(values).save()
        else:
            await MCPTool.create(name=tool.name, enabled=True, **values)

    # Drop tools that no longer exist, but never delete admin-disabled rows.
    await MCPTool.filter(enabled=True).exclude(name__in=current).delete()
