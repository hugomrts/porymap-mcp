"""MCP tool implementations.

Each submodule exports a ``register(mcp)`` function that attaches its tools
to a FastMCP server. Tools are thin orchestrators over
:class:`porymap_mcp.project.Project`; all business logic lives in
``parsers/`` and ``Project`` itself.
"""

from __future__ import annotations
