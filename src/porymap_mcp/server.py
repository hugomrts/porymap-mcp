"""FastMCP server assembly.

This module holds :func:`build_server`, which constructs the ``FastMCP``
instance and registers all tools. Tools live in ``porymap_mcp.tools`` and
attach themselves via the ``register(mcp)`` pattern, keeping this module
small and free of business logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def build_server() -> FastMCP:
    """Construct the FastMCP server with all tools registered."""
    from fastmcp import FastMCP

    from porymap_mcp.tools import discovery, events, maps, projects

    mcp: FastMCP = FastMCP(
        name="porymap-mcp",
        instructions=(
            "Tools for authoring pokeemerald-family map files (Porymap-compatible). "
            "Always pass an absolute project_path. Call discovery tools "
            "(list_maps, get_map_info, list_metatiles) before mutating."
        ),
    )

    discovery.register(mcp)
    maps.register(mcp)
    projects.register(mcp)
    events.register(mcp)

    return mcp
