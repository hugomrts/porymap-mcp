"""L1 project-structure mutation tools (ADR-0006 §7-8).

Implements ``register_map`` and ``unregister_map`` — the repair tools
for attaching / detaching maps from ``map_groups.json`` without
touching their on-disk files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from porymap_mcp.errors import MapNotFoundError, ProjectError
from porymap_mcp.parsers.mapgroups import MapGroups
from porymap_mcp.project import Project
from porymap_mcp.tools._common import load_project as _load_project
from porymap_mcp.tools._common import posix_str as _posix_str
from porymap_mcp.tools._common import summarize_files as _summarize_files

if TYPE_CHECKING:
    from fastmcp import FastMCP


# --- 7. register_map ------------------------------------------------------


def register_map(
    project_path: str,
    map_name: str,
    group: str,
) -> dict[str, Any]:
    """See ADR-0006 §7."""
    project = _load_project(project_path)
    bare = project.find_bare_by_map_id(map_name)
    if bare is None:
        raise MapNotFoundError(map_name)

    existing_groups = project.map_groups
    current_group = project.group_of(bare)

    if current_group == group:
        return {
            "summary": f"{map_name} already registered in {group}; no change.",
            "project_path": _posix_str(project.root),
            "map_name": map_name,
            "bare_name": bare,
            "group": group,
            "group_created": False,
            "was_already_registered": True,
            "files_modified": [],
        }
    if current_group is not None:
        raise ProjectError(
            f"register_map: {map_name} is already registered in "
            f"{current_group!r}, not {group!r}. Call unregister_map "
            f"first, then re-register."
        )

    group_created = group not in existing_groups.group_order
    if group_created:
        new_group_order = (*existing_groups.group_order, group)
        new_groups = dict(existing_groups.groups)
        new_groups[group] = (bare,)
    else:
        new_group_order = existing_groups.group_order
        new_groups = dict(existing_groups.groups)
        new_groups[group] = (*existing_groups.groups.get(group, ()), bare)

    project.map_groups = MapGroups(
        group_order=new_group_order,
        groups=new_groups,
        custom=existing_groups.custom,
    )
    project.save_map_groups()
    created_msg = " (created)" if group_created else ""
    return {
        "summary": (f"Registered {map_name} (bare {bare!r}) in group {group}{created_msg}."),
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "bare_name": bare,
        "group": group,
        "group_created": group_created,
        "was_already_registered": False,
        "files_modified": _summarize_files([project.map_groups_json_path], project.root),
    }


# --- 8. unregister_map ----------------------------------------------------


def unregister_map(
    project_path: str,
    map_name: str,
) -> dict[str, Any]:
    """See ADR-0006 §8."""
    project = _load_project(project_path)
    bare = project.find_bare_by_map_id(map_name)
    if bare is None:
        raise MapNotFoundError(map_name)

    existing_groups = project.map_groups
    current_group = project.group_of(bare)

    orphaned_files = _orphaned_files_for(project, bare)

    if current_group is None:
        return {
            "summary": (
                f"{map_name} is not registered in any group; no change. "
                f"Files preserved at data/maps/{bare}/ and data/layouts/{bare}/."
            ),
            "project_path": _posix_str(project.root),
            "map_name": map_name,
            "group": None,
            "group_removed": False,
            "was_already_unregistered": True,
            "orphaned_files": orphaned_files,
            "files_modified": [],
        }

    new_groups = dict(existing_groups.groups)
    new_members = tuple(n for n in existing_groups.groups.get(current_group, ()) if n != bare)
    group_removed = len(new_members) == 0
    if group_removed:
        del new_groups[current_group]
        new_group_order = tuple(g for g in existing_groups.group_order if g != current_group)
    else:
        new_groups[current_group] = new_members
        new_group_order = existing_groups.group_order

    project.map_groups = MapGroups(
        group_order=new_group_order,
        groups=new_groups,
        custom=existing_groups.custom,
    )
    project.save_map_groups()
    removal_msg = " (group emptied and removed)" if group_removed else ""
    return {
        "summary": (
            f"Unregistered {map_name} from {current_group}{removal_msg}. "
            f"Files preserved at data/maps/{bare}/ and data/layouts/{bare}/."
        ),
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "group": current_group,
        "group_removed": group_removed,
        "was_already_unregistered": False,
        "orphaned_files": orphaned_files,
        "files_modified": _summarize_files([project.map_groups_json_path], project.root),
    }


def _orphaned_files_for(project: Project, bare: str) -> list[str]:
    """Return the on-disk file paths that survive unregistration.

    Walks ``data/maps/<bare>/`` and ``data/layouts/<bare>/`` and reports
    every existing file as POSIX-relative paths, sorted. Missing
    directories are skipped silently.
    """
    out: list[str] = []
    for sub in (project.maps_dir / bare, project.root / "data" / "layouts" / bare):
        if not sub.is_dir():
            continue
        for path in sorted(sub.rglob("*")):
            if path.is_file():
                out.append(path.relative_to(project.root).as_posix())
    return out


# --- FastMCP registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    mcp.tool(name="register_map")(_tool_register_map)
    mcp.tool(name="unregister_map")(_tool_unregister_map)


def _tool_register_map(
    project_path: str,
    map_name: str,
    group: str,
) -> dict[str, Any]:
    """Register an existing on-disk map directory in map_groups.json.

    Repair tool. Use when a map's files exist on disk
    (data/maps/<bare>/map.json + data/layouts/<bare>/) but it is not
    listed in any group. Scans every map.json on disk to locate the map
    (does NOT require it to already be registered).

    Idempotence:
      - Already in the requested group: no-op success.
      - Already in a different group: error (use unregister_map first).
      - Not in any group: append (group created if missing).

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      group: C symbol for the map group.
    """
    return register_map(project_path, map_name, group)


def _tool_unregister_map(
    project_path: str,
    map_name: str,
) -> dict[str, Any]:
    """Remove a map from map_groups.json. Does NOT delete files.

    The map's data/maps/<bare>/ and data/layouts/<bare>/ directories
    are left in place. Idempotent: a map already absent from every
    group is a no-op success. If unregistering empties the group, the
    group itself is also removed.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
    """
    return unregister_map(project_path, map_name)


__all__ = [
    "register",
    "register_map",
    "unregister_map",
]
