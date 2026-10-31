"""porymap-mcp — MCP server for authoring pokeemerald-family map files.

Public API surface is intentionally minimal at the package level. The MCP
server entry point is `porymap_mcp.__main__`. Library consumers (rare) import
from the typed submodules: ``porymap_mcp.parsers``, ``porymap_mcp.errors``.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
