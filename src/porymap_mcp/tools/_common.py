"""Shared plumbing for MCP tool modules.

Used by ``tools/discovery.py``, ``tools/maps.py``, and ``tools/projects.py``.
Keep this module tiny — anything that grows belongs in :class:`Project`
or one of the parsers.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

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
