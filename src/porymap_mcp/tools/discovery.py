"""L1 discovery tools — read-only introspection of a pokeemerald-family project.

This module implements the seven tools specified in ADR-0005:

  - ``get_project_info``
  - ``list_maps``
  - ``get_map_info``
  - ``list_tilesets``
  - ``list_metatiles``
  - ``list_prefabs``
  - ``list_events``

Each tool takes ``project_path: str`` as its first argument, normalizes it
through :func:`_load_project` (``~`` expansion + ``resolve``), then orchestrates
calls into :class:`porymap_mcp.project.Project`. Errors propagate as
:class:`porymap_mcp.errors.PorymapMCPError` subclasses; FastMCP renders them
into structured MCP error responses.

Tools must not raise raw :class:`Exception` across the MCP boundary — every
expected failure mode is captured by the existing error hierarchy.

References:
  - ADR-0005 (`docs/decisions/0005-l1-discovery-tools-api.md`) for the
    full contract, return-shape JSON examples, and naming rationale.
  - Phase doc: `docs/phases/phase-2-l1-filesystem.md` §3 / §7.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from porymap_mcp.errors import FormatError, ProjectError
from porymap_mcp.parsers import attributes as attributes_parser
from porymap_mcp.parsers import metatiles as metatiles_parser
from porymap_mcp.parsers.attributes import AttributeMasks
from porymap_mcp.parsers.mapjson import MapJson
from porymap_mcp.parsers.tileset import TilesetEntry
from porymap_mcp.project import DEFAULT_BORDER_SIZE, Project
from porymap_mcp.tools._common import load_project as _load_project
from porymap_mcp.tools._common import posix_str as _posix_str

if TYPE_CHECKING:
    from fastmcp import FastMCP


# --- 1. get_project_info ---------------------------------------------------


def get_project_info(project_path: str) -> dict[str, Any]:
    """See ADR-0005 §1. Tool body separated from the FastMCP decorator so it
    can be unit-tested directly without spinning up a server."""
    project = _load_project(project_path)
    cfg = project.config  # raises UnsupportedBaseGameError if applicable
    layouts = project.layouts
    map_count = len(project.list_map_names())
    tilesets = project.tilesets
    primary_count = sum(1 for t in tilesets if t.kind == "primary")
    secondary_count = len(tilesets) - primary_count
    return {
        "summary": (
            f"Project at {project.root} ({cfg.base_game_version}): "
            f"{map_count} maps, {len(layouts.layouts)} layouts, "
            f"{len(tilesets)} tilesets."
        ),
        "project_path": _posix_str(project.root),
        "base_game_version": cfg.base_game_version,
        "map_count": map_count,
        "layout_count": len(layouts.layouts),
        "tileset_count": len(tilesets),
        "primary_tileset_count": primary_count,
        "secondary_tileset_count": secondary_count,
        "config_path": _posix_str(project.config_path),
        "layouts_json_path": _posix_str(project.layouts_json_path),
        "map_groups_json_path": _posix_str(project.map_groups_json_path),
    }


# --- 2. list_maps ----------------------------------------------------------


def list_maps(project_path: str) -> dict[str, Any]:
    """See ADR-0005 §2."""
    project = _load_project(project_path)
    maps: list[dict[str, Any]] = []
    group_count = len(project.map_groups.group_order)
    for _bare, group, doc in project.iter_maps():
        layout_id = doc.layout
        try:
            entry = project.get_layout(layout_id)
            dimensions: dict[str, int] | None = {
                "width": entry.width,
                "height": entry.height,
            }
        except ProjectError:
            # layout_id present in map.json but absent from layouts.json
            dimensions = None
        maps.append(
            {
                "name": doc.id,
                "group": group,
                "layout_id": layout_id or None,
                "dimensions": dimensions,
            }
        )
    return {
        "summary": f"Project has {len(maps)} maps across {group_count} group(s).",
        "project_path": _posix_str(project.root),
        "maps": maps,
    }


# --- 3. get_map_info -------------------------------------------------------


def get_map_info(project_path: str, map_name: str) -> dict[str, Any]:
    """See ADR-0005 §3."""
    project = _load_project(project_path)
    _bare, group, doc = project.get_map_entry(map_name)
    layout_entry = project.get_layout(doc.layout)

    border_width, border_height = DEFAULT_BORDER_SIZE
    if layout_entry.border_width is not None and layout_entry.border_height is not None:
        border_width, border_height = layout_entry.border_width, layout_entry.border_height

    object_count = len(doc.object_events) if doc.object_events is not None else 0
    warp_count = len(doc.warp_events) if doc.warp_events is not None else 0
    coord_count = len(doc.coord_events) if doc.coord_events is not None else 0
    bg_count = len(doc.bg_events) if doc.bg_events is not None else 0
    total_events = object_count + warp_count + coord_count + bg_count

    return {
        "summary": (
            f"{doc.id}: {layout_entry.width}x{layout_entry.height}, "
            f"layout {layout_entry.id}, {warp_count} warps, {object_count} objects."
        ),
        "project_path": _posix_str(project.root),
        "map_name": doc.id,
        "group": group,
        "dimensions": {"width": layout_entry.width, "height": layout_entry.height},
        "border_dimensions": {"width": border_width, "height": border_height},
        "layout": {
            "id": layout_entry.id,
            "name": layout_entry.name,
            "primary_tileset": layout_entry.primary_tileset,
            "secondary_tileset": layout_entry.secondary_tileset,
            "blockdata_filepath": layout_entry.blockdata_filepath,
            "border_filepath": layout_entry.border_filepath,
        },
        "header": _build_header_dict(doc),
        "event_counts": {
            "object_events": object_count,
            "warp_events": warp_count,
            "coord_events": coord_count,
            "bg_events": bg_count,
            "total": total_events,
        },
        "connection_count": len(doc.connections),
        "inherits_events_from": doc.shared_events_map,
        "inherits_scripts_from": doc.shared_scripts_map,
    }


def _build_header_dict(doc: MapJson) -> dict[str, Any]:
    return {
        "music": doc.music,
        "region_map_section": doc.region_map_section,
        "weather": doc.weather,
        "map_type": doc.map_type,
        "requires_flash": doc.requires_flash,
        "show_map_name": doc.show_map_name,
        "battle_scene": doc.battle_scene,
        "allow_cycling": doc.allow_cycling,
        "allow_escaping": doc.allow_escaping,
        "allow_running": doc.allow_running,
        "floor_number": doc.floor_number,
    }


# --- 4. list_tilesets ------------------------------------------------------


def list_tilesets(project_path: str) -> dict[str, Any]:
    """See ADR-0005 §4."""
    project = _load_project(project_path)
    tilesets = project.tilesets
    out: list[dict[str, Any]] = []
    for entry in tilesets:
        out.append(_tileset_to_dict(project, entry))
    primary = sum(1 for t in tilesets if t.kind == "primary")
    secondary = len(tilesets) - primary
    return {
        "summary": (
            f"Project has {len(tilesets)} tileset(s) ({primary} primary, {secondary} secondary)."
        ),
        "project_path": _posix_str(project.root),
        "tilesets": out,
    }


def _tileset_to_dict(project: Project, entry: TilesetEntry) -> dict[str, Any]:
    try:
        metatile_count = _metatile_count_for(project, entry)
    except FormatError:
        metatile_count = None
    return {
        "name": entry.name,
        "c_label": entry.c_label,
        "c_label_unverified": entry.c_label_unverified,
        "is_primary": entry.kind == "primary",
        "kind": entry.kind,
        "metatile_count": metatile_count,
        "paths": {
            "tiles": entry.tiles_path,
            "metatiles": entry.metatiles_path,
            "attributes": entry.attributes_path,
            "palettes": entry.palettes_dir,
        },
    }


def _metatile_count_for(project: Project, entry: TilesetEntry) -> int | None:
    """Return the metatile count for ``entry`` using the project's
    triple-layer flag, or ``None`` if ``metatiles.bin`` is missing.

    Raises :class:`FormatError` (which propagates as a `PorymapMCPError`)
    when the file is present but corrupt.
    """
    metatiles_path = project.root / Path(*entry.metatiles_path.split("/"))
    try:
        data = metatiles_path.read_bytes()
    except FileNotFoundError:
        return None
    import contextlib

    triple = False
    with contextlib.suppress(ProjectError):
        triple = project.config.enable_triple_layer_metatiles
    return metatiles_parser.count_metatiles(data, triple_layer=triple)


# --- 5. list_metatiles -----------------------------------------------------


def list_metatiles(project_path: str, tileset_name: str) -> dict[str, Any]:
    """See ADR-0005 §5. Reads ``metatiles.bin`` for the count and
    ``metatile_attributes.bin`` for per-metatile attribute decoding."""
    project = _load_project(project_path)
    entry = project.get_tileset_by_name(tileset_name)
    metatile_count = _metatile_count_for(project, entry)

    metatiles_out: list[dict[str, Any]] = []
    if metatile_count is not None and metatile_count > 0:
        attr_path = project.root / Path(*entry.attributes_path.split("/"))
        if attr_path.is_file():
            cfg = project.config
            masks = AttributeMasks(
                behavior=cfg.metatile_behavior_mask,
                terrain_type=cfg.metatile_terrain_type_mask,
                encounter_type=cfg.metatile_encounter_type_mask,
                layer_type=cfg.metatile_layer_type_mask,
            )
            try:
                decoded = attributes_parser.read(
                    attr_path.read_bytes(),
                    attribute_size=cfg.metatile_attributes_size,
                    masks=masks,
                    expected_count=metatile_count,
                )
            except FormatError:
                decoded = ()
            for i, attr in enumerate(decoded):
                metatiles_out.append(
                    {
                        "id": i,
                        "attributes": {
                            "behavior": attr.behavior,
                            "terrain_type": attr.terrain_type,
                            "encounter_type": attr.encounter_type,
                            "layer_type": attr.layer_type,
                            "raw": attr.raw,
                        },
                    }
                )
    return {
        "summary": (
            f"Tileset {entry.name!r} ({entry.kind}): "
            f"{metatile_count if metatile_count is not None else 'unknown'} "
            f"metatile(s); {len(metatiles_out)} with decoded attributes."
        ),
        "project_path": _posix_str(project.root),
        "tileset_name": entry.name,
        "kind": entry.kind,
        "c_label": entry.c_label,
        "metatile_count": metatile_count,
        "metatiles": metatiles_out,
    }


# --- 6. list_prefabs -------------------------------------------------------


def list_prefabs(project_path: str) -> dict[str, Any]:
    """See ADR-0005 §6 + ADR-0008. Reads from the built-in
    :data:`porymap_mcp.prefabs.LIBRARY`."""
    from porymap_mcp.prefabs import LIBRARY

    project = _load_project(project_path)
    prefabs: list[dict[str, Any]] = []
    for name in sorted(LIBRARY):
        p = LIBRARY[name]
        prefabs.append(
            {
                "name": p.name,
                "width": p.width,
                "height": p.height,
                "description": p.description,
                "tileset_requirements": {
                    "primary": p.primary_tileset,
                    "secondary": p.secondary_tileset,
                },
            }
        )
    summary = (
        f"Project has {len(prefabs)} bundled prefab(s) available to paint_prefab."
        if prefabs
        else "No prefabs are bundled in this version of porymap-mcp."
    )
    return {
        "summary": summary,
        "project_path": _posix_str(project.root),
        "prefabs": prefabs,
    }


# --- 7. list_events --------------------------------------------------------


def list_events(project_path: str, map_name: str) -> dict[str, Any]:
    """See ADR-0005 §7."""
    project = _load_project(project_path)
    _bare, _group, doc = project.get_map_entry(map_name)

    inherits_from = doc.shared_events_map

    objects = _annotate_events(doc.object_events, "object_events")
    warps = _annotate_events(doc.warp_events, "warp_events")
    coords = _annotate_events(doc.coord_events, "coord_events")
    bgs = _annotate_events(doc.bg_events, "bg_events")

    return {
        "summary": (
            f"{doc.id} inherits events from {inherits_from}."
            if inherits_from is not None
            else (
                f"{doc.id}: {len(objects)} objects, {len(warps)} warps, "
                f"{len(coords)} coord, {len(bgs)} bg."
            )
        ),
        "project_path": _posix_str(project.root),
        "map_name": doc.id,
        "inherits_events_from": inherits_from,
        "object_events": objects,
        "warp_events": warps,
        "coord_events": coords,
        "bg_events": bgs,
    }


def _annotate_events(
    events: tuple[dict[str, object], ...] | None,
    class_name: str,
) -> list[dict[str, object]]:
    """Return a copy of ``events`` with a synthesized ``_event_id``
    prepended to each entry. Returns ``[]`` when ``events is None``
    (the inherit-events case)."""
    if events is None:
        return []
    annotated: list[dict[str, object]] = []
    for index, event in enumerate(events):
        out: dict[str, object] = {"_event_id": f"{class_name}:{index}"}
        out.update(event)
        annotated.append(out)
    return annotated


# --- FastMCP registration --------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Attach all discovery tools to ``mcp``.

    Calling this is idempotent in the sense that ``build_server`` only
    invokes it once during construction; FastMCP itself rejects duplicate
    tool names.
    """
    mcp.tool(name="get_project_info")(_tool_get_project_info)
    mcp.tool(name="list_maps")(_tool_list_maps)
    mcp.tool(name="get_map_info")(_tool_get_map_info)
    mcp.tool(name="list_tilesets")(_tool_list_tilesets)
    mcp.tool(name="list_metatiles")(_tool_list_metatiles)
    mcp.tool(name="list_prefabs")(_tool_list_prefabs)
    mcp.tool(name="list_events")(_tool_list_events)


# The wrappers below exist so the MCP-facing surface carries the public
# docstring (LLM clients see this text) while the implementation bodies
# above stay testable as plain Python functions.


def _tool_get_project_info(project_path: str) -> dict[str, Any]:
    """Return a one-shot snapshot of a pokeemerald-family project.

    Use this as the FIRST call when you start working on an unfamiliar
    project — it tells you which decomp base the project targets, how
    many maps and tilesets it contains, and the absolute paths to the
    three index files you may want to inspect with other tools.

    Args:
      project_path: Filesystem path to the project root (the directory
        that contains porymap.project.cfg). Accepts absolute paths,
        ~-prefixed paths, and paths relative to the server's cwd.
    """
    return get_project_info(project_path)


def _tool_list_maps(project_path: str) -> dict[str, Any]:
    """List every map registered in data/maps/map_groups.json.

    Use this to translate a fuzzy user request like "edit Littleroot"
    into a canonical MAP_LITTLEROOT_TOWN identifier before calling
    map-specific tools. Maps are returned in the project's canonical
    group order (matching what Porymap shows in its sidebar).

    Args:
      project_path: project root.
    """
    return list_maps(project_path)


def _tool_get_map_info(project_path: str, map_name: str) -> dict[str, Any]:
    """Return full metadata for a single map.

    Call this immediately before any map-mutation tool. It gives the
    map's dimensions (needed to validate (x, y) for paint_*), its
    tilesets (needed to decide which metatile ids are valid), and counts
    of every event class. Coordinates inside the map are (x, y) with
    origin top-left and 0 <= x < width, 0 <= y < height.

    Args:
      project_path: project root.
      map_name: map constant, e.g. "MAP_LITTLEROOT_TOWN". Get the valid
        set with list_maps.
    """
    return get_map_info(project_path, map_name)


def _tool_list_tilesets(project_path: str) -> dict[str, Any]:
    """List every tileset discovered on disk (primary + secondary).

    The agent uses this to pick a primary_tileset / secondary_tileset
    pair when calling create_map, or to look up a tileset's metatile
    count before list_metatiles. Treat c_label_unverified=true as
    "probably right, but cross-check with layouts.json".

    Args:
      project_path: project root.
    """
    return list_tilesets(project_path)


def _tool_list_metatiles(project_path: str, tileset_name: str) -> dict[str, Any]:
    """List the metatiles in a single tileset.

    Returns one entry per metatile id with its decoded attributes.
    Does NOT return rendered images; that's a Phase 4 (L3) capability.
    In v0.1.0 prerelease ``metatiles`` is empty and ``metatile_count``
    is file-size-derived; per-metatile attributes land with
    parsers/metatiles.py.

    Args:
      project_path: project root.
      tileset_name: directory basename (NOT C label). Example: "general",
        not "gTileset_General". Get the valid set with list_tilesets.
    """
    return list_metatiles(project_path, tileset_name)


def _tool_list_prefabs(project_path: str) -> dict[str, Any]:
    """List named metatile-stamp prefabs available to paint_prefab.

    In v0.1.0 no prefabs ship; this tool returns ``{"prefabs": []}``
    so paint_prefab has a discovery pair from day one.

    Args:
      project_path: project root.
    """
    return list_prefabs(project_path)


def _tool_list_events(project_path: str, map_name: str) -> dict[str, Any]:
    """List every event on a map, grouped by class.

    Returns object_events, warp_events, coord_events, and bg_events.
    Each event carries a synthesized "_event_id" of the form
    "<class>:<index>" usable with remove_event. IDs shift across
    mutations — call list_events again after any change.

    Args:
      project_path: project root.
      map_name: map constant. Get from list_maps.
    """
    return list_events(project_path, map_name)


__all__ = [
    "get_map_info",
    "get_project_info",
    "list_events",
    "list_maps",
    "list_metatiles",
    "list_prefabs",
    "list_tilesets",
    "register",
]
