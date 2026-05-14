"""Shared plumbing for MCP tool modules.

Used by ``tools/discovery.py``, ``tools/maps.py``, and ``tools/projects.py``.
Keep this module tiny — anything that grows belongs in :class:`Project`
or one of the parsers.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from porymap_mcp.project import Project


def load_project(project_path: str) -> Project:
    """Normalize ``project_path`` and return a :class:`Project`.

    Accepts absolute paths, ``~``-prefixed paths, and paths relative to
    the MCP server's cwd. Raises :class:`ProjectError` if the resolved
    path is not a directory.
    """
    resolved = Path(project_path).expanduser().resolve()
    return Project(resolved)


def posix_str(path: Path) -> str:
    """Return ``path`` as a POSIX-style absolute string."""
    return path.as_posix()


def maybe_attach_render(
    response: dict[str, Any],
    *,
    project_path: str,
    map_name: str,
    return_render: bool,
) -> Any:
    """Optionally wrap a mutation tool's structured response with a render.

    When ``return_render`` is ``False``, returns ``response`` unchanged
    (the historical L1 contract: plain ``dict[str, Any]``). When ``True``,
    renders the (now-edited) map via :func:`render_map` and returns a
    FastMCP ``ToolResult`` whose:

      - ``content[0]`` is the rendered PNG image block,
      - ``structured_content`` is ``response`` merged with the render
        metadata under a nested ``"render"`` key. The render's own
        ``summary`` is appended to the mutation's summary.

    The render is always done with default options (no overlays, no
    border, scale 1) — agents can call ``render_map`` explicitly with
    custom options when they need them; ``return_render=True`` is
    the cheap "show me what I just changed" path.

    Args:
        response: the mutation tool's existing structured response dict.
        project_path: project root (unchanged from the tool's first arg).
        map_name: ``MAP_*`` constant of the affected map.
        return_render: if False, return ``response`` unchanged.

    Returns:
        Either ``response`` (when ``return_render=False``) or a
        ``fastmcp.tools.base.ToolResult``.
    """
    if not return_render:
        return response

    from fastmcp.tools.base import ToolResult

    from porymap_mcp.tools.rendering import render_map

    render_result = render_map(project_path, map_name)
    image_block = render_result.content[0]
    render_extra: dict[str, Any] = dict(render_result.structured_content)
    render_summary = str(render_extra.pop("summary", ""))

    mutation_summary = str(response.get("summary", f"Mutated {map_name}."))
    combined_summary = (
        f"{mutation_summary} {render_summary}".strip() if render_summary else mutation_summary
    )

    merged: dict[str, Any] = {**response, "summary": combined_summary, "render": render_extra}
    return ToolResult(content=[image_block], structured_content=merged)


def summarize_files(paths: Iterable[Path], root: Path) -> list[str]:
    """Return ``paths`` as sorted, de-duplicated POSIX strings relative to ``root``.

    Used to build the ``files_modified`` field on every mutation tool's
    response. Stable across OSes (POSIX separators) and stable across
    runs (lexical sort) so two equivalent calls yield byte-identical
    JSON.
    """
    out: set[str] = set()
    for path in paths:
        rel = path.resolve().relative_to(root.resolve())
        out.add(rel.as_posix())
    return sorted(out)
