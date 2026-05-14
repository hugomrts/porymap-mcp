"""L1 map-mutation tools (ADR-0006).

Implements:

  - ``paint_metatile``
  - ``paint_rectangle``
  - ``flood_fill``
  - ``set_border``
  - ``create_map``
  - ``resize_map``

Each tool body is a plain function (testable as Python); a thin
``_tool_*`` wrapper carrying the LLM-facing docstring is what FastMCP
registers via :func:`register`. See ADR-0006 for the contract (frozen
at v0.1.0) and ADR-0005 §"Convention shared by all seven" for the
``project_path``-first / structured-return / `PorymapMCPError`-only
conventions.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from porymap_mcp._atomic import write_atomic_text
from porymap_mcp.errors import (
    CoordinatesOutOfBoundsError,
    ProjectError,
)
from porymap_mcp.parsers import layoutsjson, mapbin, mapgroups, mapjson
from porymap_mcp.parsers.layoutsjson import LayoutEntry, LayoutsJson
from porymap_mcp.parsers.mapbin import (
    MAX_COLLISION,
    MAX_ELEVATION,
    MAX_METATILE_ID,
    MapBin,
    Tile,
)
from porymap_mcp.parsers.mapgroups import MapGroups
from porymap_mcp.parsers.mapjson import MapJson
from porymap_mcp.project import DEFAULT_BORDER_SIZE, Project
from porymap_mcp.tools._common import load_project as _load_project
from porymap_mcp.tools._common import maybe_attach_render as _maybe_attach_render
from porymap_mcp.tools._common import posix_str as _posix_str
from porymap_mcp.tools._common import summarize_files as _summarize_files

if TYPE_CHECKING:
    from fastmcp import FastMCP

# --- Shared validators ----------------------------------------------------


def _resolve_layout(project: Project, map_name: str) -> tuple[str, LayoutEntry]:
    """Resolve ``map_name`` (a MAP_* constant) to ``(layout_id, LayoutEntry)``."""
    _bare, _group, doc = project.get_map_entry(map_name)
    return doc.layout, project.get_layout(doc.layout)


def _check_coords(x: int, y: int, width: int, height: int) -> None:
    if not (0 <= x < width and 0 <= y < height):
        raise CoordinatesOutOfBoundsError(x, y, width, height)


def _check_metatile_id(value: int) -> None:
    if not 0 <= value <= MAX_METATILE_ID:
        raise ProjectError(
            f"metatile_id 0x{value:X} out of encoding range "
            f"0..0x{MAX_METATILE_ID:X} (10 bits). "
            "Use list_metatiles to enumerate the tileset."
        )


def _check_collision(value: int | None) -> None:
    if value is None:
        return
    if not 0 <= value <= MAX_COLLISION:
        raise ProjectError(f"collision={value} out of range 0..{MAX_COLLISION} (2 bits).")


def _check_elevation(value: int | None) -> None:
    if value is None:
        return
    if not 0 <= value <= MAX_ELEVATION:
        raise ProjectError(f"elevation={value} out of range 0..{MAX_ELEVATION} (4 bits).")


def _new_tile(
    existing: Tile,
    metatile_id: int,
    collision: int | None,
    elevation: int | None,
) -> Tile:
    return Tile(
        metatile_id=metatile_id,
        collision=existing.collision if collision is None else collision,
        elevation=existing.elevation if elevation is None else elevation,
    )


def _border_dims(layout_entry: LayoutEntry) -> tuple[int, int]:
    if layout_entry.border_width is not None and layout_entry.border_height is not None:
        return layout_entry.border_width, layout_entry.border_height
    return DEFAULT_BORDER_SIZE


def _replace_tile(layout: MapBin, x: int, y: int, tile: Tile) -> MapBin:
    """Return a copy of ``layout`` with ``(x, y)`` replaced by ``tile``."""
    rows: list[tuple[Tile, ...]] = []
    for row_y, row in enumerate(layout.tiles):
        if row_y != y:
            rows.append(row)
            continue
        new_row = tuple(tile if col_x == x else cell for col_x, cell in enumerate(row))
        rows.append(new_row)
    return MapBin(width=layout.width, height=layout.height, tiles=tuple(rows))


def _bare_to_snake(bare: str) -> str:
    """Convert ``"LittlerootTown"`` to ``"LITTLEROOT_TOWN"``.

    Inserts underscores before each interior uppercase run, then
    uppercases everything. Handles runs of caps gracefully:
    ``"BattleHQ"`` → ``"BATTLE_HQ"``.
    """
    if not bare:
        return ""
    out: list[str] = [bare[0]]
    for i in range(1, len(bare)):
        ch = bare[i]
        prev = bare[i - 1]
        boundary_lower_to_upper = ch.isupper() and (prev.islower() or prev.isdigit())
        boundary_run_end = (
            ch.isupper() and prev.isupper() and i + 1 < len(bare) and bare[i + 1].islower()
        )
        if boundary_lower_to_upper or boundary_run_end:
            out.append("_")
        out.append(ch)
    return "".join(out).upper()


def _validate_bare_name(name: str) -> None:
    """Enforce ADR-0006 CC-5: ``name`` is bare PascalCase, not a MAP_* constant."""
    if not name:
        raise ProjectError("create_map: 'name' must not be empty.")
    if name.startswith(("MAP_", "LAYOUT_")):
        raise ProjectError(
            f"create_map: 'name' must be the bare PascalCase form "
            f"(e.g. 'LittlerootTown'), not the {name!r} constant. "
            "The MAP_* and LAYOUT_* identifiers are derived automatically."
        )
    if not name[0].isupper():
        raise ProjectError(
            f"create_map: 'name' must start with an uppercase letter (PascalCase), got {name!r}."
        )
    if "_" in name or " " in name:
        raise ProjectError(
            f"create_map: 'name' must be PascalCase without underscores or spaces, got {name!r}."
        )
    if not name.isidentifier():
        raise ProjectError(f"create_map: 'name' must be a valid identifier, got {name!r}.")


# --- 1. paint_metatile ----------------------------------------------------


def paint_metatile(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    metatile_id: int,
    collision: int | None = None,
    elevation: int | None = None,
    return_render: bool = False,
) -> Any:
    """See ADR-0006 §1."""
    project = _load_project(project_path)
    _check_metatile_id(metatile_id)
    _check_collision(collision)
    _check_elevation(elevation)

    layout_id, layout_entry = _resolve_layout(project, map_name)
    _check_coords(x, y, layout_entry.width, layout_entry.height)

    layout = project.read_map_bin(layout_id)
    previous = layout.get(x, y)
    new_tile = _new_tile(previous, metatile_id, collision, elevation)

    response: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "x": x,
        "y": y,
        "metatile_id": metatile_id,
        "collision": new_tile.collision,
        "elevation": new_tile.elevation,
        "previous": {
            "metatile_id": previous.metatile_id,
            "collision": previous.collision,
            "elevation": previous.elevation,
        },
    }

    if new_tile == previous:
        response["summary"] = (
            f"Tile at ({x}, {y}) on {map_name} already metatile "
            f"0x{metatile_id:03X} with collision={new_tile.collision}, "
            f"elevation={new_tile.elevation}; no change."
        )
        response["files_modified"] = []
        return _maybe_attach_render(
            response, project_path=project_path, map_name=map_name, return_render=return_render
        )

    new_layout = _replace_tile(layout, x, y, new_tile)
    project.write_map_bin(layout_id, new_layout)
    preserved = []
    if collision is None:
        preserved.append(f"collision={new_tile.collision}")
    if elevation is None:
        preserved.append(f"elevation={new_tile.elevation}")
    preserved_str = f"; preserved {', '.join(preserved)}" if preserved else ""
    response["summary"] = (
        f"Painted metatile 0x{metatile_id:03X} at ({x}, {y}) on {map_name}{preserved_str}."
    )
    response["files_modified"] = _summarize_files(
        [project.resolve_path(layout_entry.blockdata_filepath)], project.root
    )
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- 2. paint_rectangle ---------------------------------------------------


def paint_rectangle(
    project_path: str,
    map_name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    metatile_id: int,
    collision: int | None = None,
    elevation: int | None = None,
    return_render: bool = False,
) -> Any:
    """See ADR-0006 §2."""
    project = _load_project(project_path)
    _check_metatile_id(metatile_id)
    _check_collision(collision)
    _check_elevation(elevation)

    layout_id, layout_entry = _resolve_layout(project, map_name)
    if x1 > x2 or y1 > y2:
        raise ProjectError(
            f"paint_rectangle: ({x1}, {y1}) > ({x2}, {y2}); "
            "provide coordinates as (top-left, bottom-right) with x1<=x2 and y1<=y2."
        )
    _check_coords(x1, y1, layout_entry.width, layout_entry.height)
    _check_coords(x2, y2, layout_entry.width, layout_entry.height)

    layout = project.read_map_bin(layout_id)
    tiles_changed = 0
    new_rows: list[tuple[Tile, ...]] = []
    for row_y, row in enumerate(layout.tiles):
        if not (y1 <= row_y <= y2):
            new_rows.append(row)
            continue
        new_row: list[Tile] = []
        for col_x, cell in enumerate(row):
            if x1 <= col_x <= x2:
                new_tile = _new_tile(cell, metatile_id, collision, elevation)
                if new_tile != cell:
                    tiles_changed += 1
                new_row.append(new_tile)
            else:
                new_row.append(cell)
        new_rows.append(tuple(new_row))
    new_layout = MapBin(width=layout.width, height=layout.height, tiles=tuple(new_rows))

    tile_count = (x2 - x1 + 1) * (y2 - y1 + 1)
    response: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "tile_count": tile_count,
        "tiles_changed": tiles_changed,
        "metatile_id": metatile_id,
        "collision": collision,
        "elevation": elevation,
    }

    if tiles_changed == 0:
        response["summary"] = (
            f"Rectangle ({x1},{y1})-({x2},{y2}) on {map_name} "
            f"already matches metatile 0x{metatile_id:03X}; no change."
        )
        response["files_modified"] = []
        return _maybe_attach_render(
            response, project_path=project_path, map_name=map_name, return_render=return_render
        )

    project.write_map_bin(layout_id, new_layout)
    response["summary"] = (
        f"Painted {tile_count} tile(s) in rectangle "
        f"({x1},{y1})-({x2},{y2}) on {map_name} to metatile "
        f"0x{metatile_id:03X}; {tiles_changed} changed."
    )
    response["files_modified"] = _summarize_files(
        [project.resolve_path(layout_entry.blockdata_filepath)], project.root
    )
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- 3. flood_fill --------------------------------------------------------


def flood_fill(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    metatile_id: int,
    collision: int | None = None,
    elevation: int | None = None,
    return_render: bool = False,
) -> Any:
    """See ADR-0006 §3. Iterative 4-connected BFS."""
    project = _load_project(project_path)
    _check_metatile_id(metatile_id)
    _check_collision(collision)
    _check_elevation(elevation)

    layout_id, layout_entry = _resolve_layout(project, map_name)
    _check_coords(x, y, layout_entry.width, layout_entry.height)

    layout = project.read_map_bin(layout_id)
    source_id = layout.get(x, y).metatile_id

    response: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "seed": {"x": x, "y": y},
        "source_metatile_id": source_id,
        "target_metatile_id": metatile_id,
    }

    if source_id == metatile_id and collision is None and elevation is None:
        # Pure no-op: seed already at target and no collision/elevation override
        # would change anything for tiles that already match.
        response["tiles_changed"] = 0
        response["summary"] = (
            f"Seed tile at ({x}, {y}) on {map_name} already metatile "
            f"0x{metatile_id:03X}; no change."
        )
        response["files_modified"] = []
        return _maybe_attach_render(
            response, project_path=project_path, map_name=map_name, return_render=return_render
        )

    # Mutable working copy as list-of-lists for in-place tile replacement.
    grid: list[list[Tile]] = [list(row) for row in layout.tiles]
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()
    queue.append((x, y))
    visited.add((x, y))
    tiles_changed = 0

    while queue:
        cx, cy = queue.popleft()
        cell = grid[cy][cx]
        if cell.metatile_id != source_id:
            continue
        new_tile = _new_tile(cell, metatile_id, collision, elevation)
        if new_tile != cell:
            grid[cy][cx] = new_tile
            tiles_changed += 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in visited:
                continue
            if not (0 <= nx < layout.width and 0 <= ny < layout.height):
                continue
            if grid[ny][nx].metatile_id != source_id:
                continue
            visited.add((nx, ny))
            queue.append((nx, ny))

    response["tiles_changed"] = tiles_changed

    if tiles_changed == 0:
        response["summary"] = f"Flood-fill from ({x}, {y}) on {map_name} produced no changes."
        response["files_modified"] = []
        return _maybe_attach_render(
            response, project_path=project_path, map_name=map_name, return_render=return_render
        )

    new_layout = MapBin(
        width=layout.width,
        height=layout.height,
        tiles=tuple(tuple(row) for row in grid),
    )
    project.write_map_bin(layout_id, new_layout)
    response["summary"] = (
        f"Flood-filled {tiles_changed} tile(s) from seed ({x}, {y}) on "
        f"{map_name}: metatile 0x{source_id:03X} -> 0x{metatile_id:03X}."
    )
    response["files_modified"] = _summarize_files(
        [project.resolve_path(layout_entry.blockdata_filepath)], project.root
    )
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- 4. set_border --------------------------------------------------------


def set_border(
    project_path: str,
    map_name: str,
    metatile_ids: Sequence[Sequence[int]],
    collision_ids: Sequence[Sequence[int]] | None = None,
    elevation_ids: Sequence[Sequence[int]] | None = None,
    return_render: bool = False,
) -> Any:
    """See ADR-0006 §4."""
    project = _load_project(project_path)
    layout_id, layout_entry = _resolve_layout(project, map_name)
    border_w, border_h = _border_dims(layout_entry)

    _validate_2d_shape(metatile_ids, border_w, border_h, "metatile_ids")
    if collision_ids is not None:
        _validate_2d_shape(collision_ids, border_w, border_h, "collision_ids")
    if elevation_ids is not None:
        _validate_2d_shape(elevation_ids, border_w, border_h, "elevation_ids")
    for row in metatile_ids:
        for v in row:
            _check_metatile_id(v)
    if collision_ids is not None:
        for row in collision_ids:
            for v in row:
                _check_collision(v)
    if elevation_ids is not None:
        for row in elevation_ids:
            for v in row:
                _check_elevation(v)

    border = project.read_border_bin(layout_id)
    cells_changed = 0
    new_rows: list[tuple[Tile, ...]] = []
    for row_y in range(border_h):
        new_row: list[Tile] = []
        for col_x in range(border_w):
            existing = border.get(col_x, row_y)
            c_override = collision_ids[row_y][col_x] if collision_ids is not None else None
            e_override = elevation_ids[row_y][col_x] if elevation_ids is not None else None
            new_tile = _new_tile(
                existing,
                metatile_ids[row_y][col_x],
                c_override,
                e_override,
            )
            if new_tile != existing:
                cells_changed += 1
            new_row.append(new_tile)
        new_rows.append(tuple(new_row))
    new_border = MapBin(width=border_w, height=border_h, tiles=tuple(new_rows))

    response: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "border_dimensions": {"width": border_w, "height": border_h},
        "cells_changed": cells_changed,
    }

    if cells_changed == 0:
        response["summary"] = (
            f"Border on {map_name} already matches the requested {border_w}x"
            f"{border_h} grid; no change."
        )
        response["files_modified"] = []
        return _maybe_attach_render(
            response, project_path=project_path, map_name=map_name, return_render=return_render
        )

    project.write_border_bin(layout_id, new_border)
    response["summary"] = (
        f"Set {border_w}x{border_h} border on {map_name}; {cells_changed} cell(s) changed."
    )
    response["files_modified"] = _summarize_files(
        [project.resolve_path(layout_entry.border_filepath)], project.root
    )
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


def _validate_2d_shape(
    grid: Sequence[Sequence[int]],
    width: int,
    height: int,
    name: str,
) -> None:
    actual_rows = len(grid)
    actual_cols = len(grid[0]) if grid else 0
    if actual_rows != height or any(len(row) != width for row in grid):
        raise ProjectError(
            f"{name}: border dimension mismatch — layout declares "
            f"{width}x{height}, got {actual_cols}x{actual_rows}. "
            "Use get_map_info to read border_dimensions."
        )


# --- 5. create_map --------------------------------------------------------


_MAP_JSON_DEFAULTS: dict[str, Any] = {
    "music": "MUS_NONE",
    "region_map_section": "MAPSEC_NONE",
    "requires_flash": False,
    "weather": "WEATHER_NONE",
    "map_type": "MAP_TYPE_TOWN",
    "allow_cycling": True,
    "allow_escaping": False,
    "allow_running": True,
    "show_map_name": True,
    "floor_number": 0,
    "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
}


def create_map(
    project_path: str,
    name: str,
    group: str,
    width: int,
    height: int,
    primary_tileset: str,
    secondary_tileset: str,
    fill_metatile_id: int = 0,
    border_metatile_ids: Sequence[Sequence[int]] | None = None,
    header_overrides: dict[str, Any] | None = None,
    return_render: bool = False,
) -> Any:
    """See ADR-0006 §5."""
    project = _load_project(project_path)
    _validate_bare_name(name)
    if width <= 0 or height <= 0:
        raise ProjectError(f"create_map: width and height must be positive (got {width}x{height}).")
    _check_metatile_id(fill_metatile_id)

    snake = _bare_to_snake(name)
    map_id = f"MAP_{snake}"
    layout_id = f"LAYOUT_{snake}"
    layout_name = f"{name}_Layout"
    map_json_path = project.maps_dir / name / "map.json"
    map_bin_path = project.root / "data" / "layouts" / name / "map.bin"
    border_bin_path = project.root / "data" / "layouts" / name / "border.bin"

    # Duplicate detection: layout id, map.json on disk, and group_groups entry.
    if layout_id in {entry.id for entry in project.layouts.layouts}:
        raise ProjectError(
            f"create_map: layout id {layout_id!r} already exists. Pick a different map name."
        )
    if map_json_path.exists():
        raise ProjectError(
            f"create_map: {map_json_path.relative_to(project.root).as_posix()!r} "
            "already exists. Pick a different map name, or use register_map "
            "to attach an existing map directory."
        )
    if project.find_bare_by_map_id(map_id) is not None:
        raise ProjectError(
            f"create_map: a map with id {map_id!r} already exists on disk. "
            "Pick a different map name."
        )

    # Border setup: default 2x2 unless the project declares a custom size.
    border_w, border_h = DEFAULT_BORDER_SIZE
    try:
        if project.config.use_custom_border_size:
            # No project-wide default in this case; pick 2x2 anyway and let
            # the user override via border_metatile_ids if they want.
            pass
    except ProjectError:
        # config absent — keep defaults; create_map can still proceed since
        # layouts.json doesn't depend on it.
        pass

    if border_metatile_ids is not None:
        _validate_2d_shape(border_metatile_ids, border_w, border_h, "border_metatile_ids")
        for row in border_metatile_ids:
            for v in row:
                _check_metatile_id(v)

    # Build the new layout (.bin) and border (.bin).
    fill_tile = Tile(metatile_id=fill_metatile_id, collision=0, elevation=0)
    new_map_bin = MapBin(
        width=width,
        height=height,
        tiles=tuple(tuple(fill_tile for _ in range(width)) for _ in range(height)),
    )
    if border_metatile_ids is None:
        border_tiles = tuple(tuple(fill_tile for _ in range(border_w)) for _ in range(border_h))
    else:
        border_tiles = tuple(
            tuple(
                Tile(metatile_id=border_metatile_ids[ry][rx], collision=0, elevation=0)
                for rx in range(border_w)
            )
            for ry in range(border_h)
        )
    new_border_bin = MapBin(width=border_w, height=border_h, tiles=border_tiles)

    # Build map.json from defaults + overrides.
    header_overrides = header_overrides or {}
    header: dict[str, Any] = dict(_MAP_JSON_DEFAULTS)
    header.update(header_overrides)
    new_map_json = MapJson(
        id=map_id,
        name=name,
        layout=layout_id,
        music=str(header["music"]),
        region_map_section=str(header["region_map_section"]),
        requires_flash=bool(header["requires_flash"]),
        weather=str(header["weather"]),
        map_type=str(header["map_type"]),
        show_map_name=bool(header["show_map_name"]),
        battle_scene=str(header["battle_scene"]),
        allow_cycling=bool(header["allow_cycling"]),
        allow_escaping=bool(header["allow_escaping"]),
        allow_running=bool(header["allow_running"]),
        floor_number=int(header["floor_number"])
        if header.get("floor_number") is not None
        else None,
        object_events=(),
        warp_events=(),
        coord_events=(),
        bg_events=(),
    )
    # Pass through unknown overrides as custom keys.
    for key, value in header_overrides.items():
        if key not in _MAP_JSON_DEFAULTS:
            new_map_json.custom[key] = value

    # Build the new LayoutEntry.
    new_layout_entry = LayoutEntry(
        id=layout_id,
        name=layout_name,
        width=width,
        height=height,
        primary_tileset=primary_tileset,
        secondary_tileset=secondary_tileset,
        border_filepath=f"data/layouts/{name}/border.bin",
        blockdata_filepath=f"data/layouts/{name}/map.bin",
        border_width=border_w if project.config.use_custom_border_size else None,
        border_height=border_h if project.config.use_custom_border_size else None,
    )
    new_layouts = LayoutsJson(
        layouts_table_label=project.layouts.layouts_table_label,
        layouts=(*project.layouts.layouts, new_layout_entry),
    )

    # Build the new MapGroups (create group if missing).
    existing_groups = project.map_groups
    group_created = group not in existing_groups.group_order
    if group_created:
        new_group_order = (*existing_groups.group_order, group)
        new_groups = dict(existing_groups.groups)
        new_groups[group] = (name,)
    else:
        new_group_order = existing_groups.group_order
        new_groups = dict(existing_groups.groups)
        new_groups[group] = (*existing_groups.groups.get(group, ()), name)
    new_map_groups = MapGroups(
        group_order=new_group_order,
        groups=new_groups,
        custom=existing_groups.custom,
    )

    # Commit in ADR-0006 §CC-7 order. Each step is individually atomic;
    # crashes between steps leave detectable orphans (see ADR).
    files_modified: list[Path] = []

    map_bin_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(map_bin_path, mapbin.write(new_map_bin))
    files_modified.append(map_bin_path)

    border_bin_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(border_bin_path, mapbin.write(new_border_bin))
    files_modified.append(border_bin_path)

    map_json_path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic_text(map_json_path, mapjson.write(new_map_json))
    files_modified.append(map_json_path)

    project.layouts = new_layouts
    project.save_layouts()
    files_modified.append(project.layouts_json_path)

    project.map_groups = new_map_groups
    project.save_map_groups()
    files_modified.append(project.map_groups_json_path)

    group_msg = " (created)" if group_created else ""
    response: dict[str, Any] = {
        "summary": (
            f"Created {map_id} ({width}x{height}) in group {group}{group_msg} "
            f"using {primary_tileset} / {secondary_tileset}."
        ),
        "project_path": _posix_str(project.root),
        "map_name": map_id,
        "layout_id": layout_id,
        "group": group,
        "group_created": group_created,
        "dimensions": {"width": width, "height": height},
        "border_dimensions": {"width": border_w, "height": border_h},
        "paths": {
            "map_json": map_json_path.relative_to(project.root).as_posix(),
            "map_bin": map_bin_path.relative_to(project.root).as_posix(),
            "border_bin": border_bin_path.relative_to(project.root).as_posix(),
        },
        "files_modified": _summarize_files(files_modified, project.root),
    }
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_id, return_render=return_render
    )


def _atomic_bytes(path: Path, data: bytes) -> None:
    """Atomic-write bytes via the shared helper (private import for clarity)."""
    from porymap_mcp._atomic import write_atomic

    write_atomic(path, data)


# --- 6. resize_map --------------------------------------------------------


def resize_map(
    project_path: str,
    map_name: str,
    new_width: int,
    new_height: int,
    anchor: str = "top-left",
    fill_metatile_id: int = 0,
    return_render: bool = False,
) -> Any:
    """See ADR-0006 §6."""
    project = _load_project(project_path)
    if anchor != "top-left":
        raise ProjectError(
            f"resize_map: anchor {anchor!r} not supported in v0.1.0; only 'top-left'."
        )
    if new_width <= 0 or new_height <= 0:
        raise ProjectError(
            f"resize_map: new_width and new_height must be positive (got {new_width}x{new_height})."
        )
    _check_metatile_id(fill_metatile_id)

    layout_id, layout_entry = _resolve_layout(project, map_name)

    response_base: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "layout_id": layout_id,
        "previous_dimensions": {"width": layout_entry.width, "height": layout_entry.height},
        "new_dimensions": {"width": new_width, "height": new_height},
    }

    if new_width == layout_entry.width and new_height == layout_entry.height:
        noop_response: dict[str, Any] = {
            **response_base,
            "summary": (
                f"Layout {layout_id} on {map_name} already {new_width}x{new_height}; no change."
            ),
            "cells_added": 0,
            "cells_removed": 0,
            "files_modified": [],
        }
        return _maybe_attach_render(
            noop_response,
            project_path=project_path,
            map_name=map_name,
            return_render=return_render,
        )

    # Shrinking: refuse if any event would fall outside the new bounds.
    orphans: list[str] = []
    if new_width < layout_entry.width or new_height < layout_entry.height:
        for _bare, _group, doc in project.iter_maps():
            if doc.layout != layout_id:
                continue
            for cls, events in (
                ("object_events", doc.object_events or ()),
                ("warp_events", doc.warp_events or ()),
                ("coord_events", doc.coord_events or ()),
                ("bg_events", doc.bg_events or ()),
            ):
                for idx, event in enumerate(events):
                    ex = event.get("x")
                    ey = event.get("y")
                    if not isinstance(ex, int) or not isinstance(ey, int):
                        continue
                    if ex >= new_width or ey >= new_height:
                        orphans.append(f"  {cls}:{idx} at ({ex}, {ey}) on {doc.id}")
    if orphans:
        raise ProjectError(
            f"resize_map: shrinking {map_name} to {new_width}x{new_height} "
            f"would orphan {len(orphans)} event(s):\n"
            + "\n".join(orphans)
            + "\nRemove these events first (use remove_event) or pick larger dimensions."
        )

    # Build the new MapBin.
    old_layout = project.read_map_bin(layout_id)
    fill_tile = Tile(metatile_id=fill_metatile_id, collision=0, elevation=0)
    new_rows: list[tuple[Tile, ...]] = []
    for y in range(new_height):
        row: list[Tile] = []
        for x in range(new_width):
            if x < old_layout.width and y < old_layout.height:
                row.append(old_layout.get(x, y))
            else:
                row.append(fill_tile)
        new_rows.append(tuple(row))
    new_map_bin = MapBin(width=new_width, height=new_height, tiles=tuple(new_rows))

    # We need to update layouts.json BEFORE write_map_bin (which enforces
    # the dimension invariant); ADR-0006 §CC-7 ordering matches because
    # the layout entry is the source of truth for dimensions.
    new_entries = tuple(
        LayoutEntry(
            id=e.id,
            name=e.name,
            width=new_width if e.id == layout_id else e.width,
            height=new_height if e.id == layout_id else e.height,
            primary_tileset=e.primary_tileset,
            secondary_tileset=e.secondary_tileset,
            border_filepath=e.border_filepath,
            blockdata_filepath=e.blockdata_filepath,
            border_width=e.border_width,
            border_height=e.border_height,
        )
        for e in project.layouts.layouts
    )
    project.layouts = LayoutsJson(
        layouts_table_label=project.layouts.layouts_table_label,
        layouts=new_entries,
    )
    project.save_layouts()
    project.write_map_bin(layout_id, new_map_bin)

    cells_added = max(0, new_width * new_height - layout_entry.width * layout_entry.height)
    cells_removed = max(0, layout_entry.width * layout_entry.height - new_width * new_height)
    resized_response: dict[str, Any] = {
        **response_base,
        "summary": (
            f"Resized {layout_id} from {layout_entry.width}x{layout_entry.height} "
            f"to {new_width}x{new_height}; {cells_added} cell(s) added, "
            f"{cells_removed} removed."
        ),
        "cells_added": cells_added,
        "cells_removed": cells_removed,
        "files_modified": _summarize_files(
            [
                project.resolve_path(layout_entry.blockdata_filepath),
                project.layouts_json_path,
            ],
            project.root,
        ),
    }
    return _maybe_attach_render(
        resized_response,
        project_path=project_path,
        map_name=map_name,
        return_render=return_render,
    )


# --- 7. paint_prefab ------------------------------------------------------


def paint_prefab(
    project_path: str,
    map_name: str,
    prefab_name: str,
    x: int,
    y: int,
    return_render: bool = False,
) -> Any:
    """See ADR-0008."""
    from porymap_mcp.prefabs import get as _get_prefab

    project = _load_project(project_path)
    prefab = _get_prefab(prefab_name)

    layout_id, layout_entry = _resolve_layout(project, map_name)
    if (
        prefab.primary_tileset is not None
        and prefab.primary_tileset != layout_entry.primary_tileset
    ):
        raise ProjectError(
            f"paint_prefab: tileset mismatch — prefab {prefab_name!r} requires "
            f"primary {prefab.primary_tileset!r}, map uses "
            f"{layout_entry.primary_tileset!r}. Pick a different prefab or "
            "change the map's tileset."
        )
    if (
        prefab.secondary_tileset is not None
        and prefab.secondary_tileset != layout_entry.secondary_tileset
    ):
        raise ProjectError(
            f"paint_prefab: tileset mismatch — prefab {prefab_name!r} requires "
            f"secondary {prefab.secondary_tileset!r}, map uses "
            f"{layout_entry.secondary_tileset!r}."
        )
    # Placement bounds: anchor + prefab dims must fit inside the layout.
    _check_coords(x, y, layout_entry.width, layout_entry.height)
    end_x = x + prefab.width - 1
    end_y = y + prefab.height - 1
    if end_x >= layout_entry.width or end_y >= layout_entry.height:
        raise CoordinatesOutOfBoundsError(end_x, end_y, layout_entry.width, layout_entry.height)

    layout = project.read_map_bin(layout_id)
    tiles_changed = 0
    new_rows: list[tuple[Tile, ...]] = []
    for row_y, row in enumerate(layout.tiles):
        if not (y <= row_y <= end_y):
            new_rows.append(row)
            continue
        new_row: list[Tile] = []
        for col_x, cell in enumerate(row):
            if x <= col_x <= end_x:
                stamp = prefab.tiles[row_y - y][col_x - x]
                new_tile = Tile(
                    metatile_id=stamp.metatile_id,
                    collision=stamp.collision,
                    elevation=stamp.elevation,
                )
                if new_tile != cell:
                    tiles_changed += 1
                new_row.append(new_tile)
            else:
                new_row.append(cell)
        new_rows.append(tuple(new_row))
    new_layout = MapBin(width=layout.width, height=layout.height, tiles=tuple(new_rows))

    response: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "prefab_name": prefab_name,
        "anchor": {"x": x, "y": y},
        "dimensions": {"width": prefab.width, "height": prefab.height},
        "tiles_changed": tiles_changed,
    }
    if tiles_changed == 0:
        response["summary"] = (
            f"Prefab {prefab_name!r} at ({x},{y}) on {map_name} already fully matches; no change."
        )
        response["files_modified"] = []
        return _maybe_attach_render(
            response, project_path=project_path, map_name=map_name, return_render=return_render
        )

    project.write_map_bin(layout_id, new_layout)
    response["summary"] = (
        f"Stamped prefab {prefab_name!r} ({prefab.width}x{prefab.height}) "
        f"at ({x},{y}) on {map_name}; {tiles_changed} tile(s) changed."
    )
    response["files_modified"] = _summarize_files(
        [project.resolve_path(layout_entry.blockdata_filepath)], project.root
    )
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- FastMCP registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Attach all map-mutation tools to ``mcp``."""
    mcp.tool(name="paint_metatile")(_tool_paint_metatile)
    mcp.tool(name="paint_rectangle")(_tool_paint_rectangle)
    mcp.tool(name="flood_fill")(_tool_flood_fill)
    mcp.tool(name="set_border")(_tool_set_border)
    mcp.tool(name="create_map")(_tool_create_map)
    mcp.tool(name="resize_map")(_tool_resize_map)
    mcp.tool(name="paint_prefab")(_tool_paint_prefab)


def _tool_paint_metatile(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    metatile_id: int,
    collision: int | None = None,
    elevation: int | None = None,
    return_render: bool = False,
) -> Any:
    """Set a single tile on a map's layout.

    The atomic paint primitive. Idempotent: re-running with identical
    args does NOT rewrite the file (mtime stable). Coordinates are
    (x, y), origin top-left.

    Args:
      project_path: project root.
      map_name: MAP_* constant. Get from list_maps.
      x, y: tile coordinates (0 <= x < width, 0 <= y < height).
      metatile_id: 0..1023. Use list_metatiles for valid ids.
      collision: 0..3, or None to preserve.
      elevation: 0..15, or None to preserve.
      return_render: if True, the response also carries a PNG render of
        the post-mutation map (default False to keep the response small).
    """
    return paint_metatile(
        project_path,
        map_name,
        x,
        y,
        metatile_id,
        collision,
        elevation,
        return_render=return_render,
    )


def _tool_paint_rectangle(
    project_path: str,
    map_name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    metatile_id: int,
    collision: int | None = None,
    elevation: int | None = None,
    return_render: bool = False,
) -> Any:
    """Fill an axis-aligned inclusive rectangle with one metatile id.

    Both corners painted. Strict order: x1<=x2 and y1<=y2 (reversed
    raises rather than auto-swapping). Idempotent.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      x1, y1: top-left inclusive corner.
      x2, y2: bottom-right inclusive corner.
      metatile_id: 0..1023.
      collision: 0..3, or None to preserve each tile's value.
      elevation: 0..15, or None to preserve.
      return_render: if True, attach a PNG render of the post-mutation
        map to the response.
    """
    return paint_rectangle(
        project_path,
        map_name,
        x1,
        y1,
        x2,
        y2,
        metatile_id,
        collision,
        elevation,
        return_render=return_render,
    )


def _tool_flood_fill(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    metatile_id: int,
    collision: int | None = None,
    elevation: int | None = None,
    return_render: bool = False,
) -> Any:
    """Replace a 4-connected region of identical metatiles with a new id.

    Matches against metatile_id only (collision/elevation not consulted
    for matching). 4-connected (N/S/E/W), iterative BFS.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      x, y: seed coordinate.
      metatile_id: replacement value.
      collision: 0..3, or None to preserve per-tile.
      elevation: 0..15, or None to preserve.
      return_render: if True, attach a PNG render of the post-mutation
        map to the response.
    """
    return flood_fill(
        project_path,
        map_name,
        x,
        y,
        metatile_id,
        collision,
        elevation,
        return_render=return_render,
    )


def _tool_set_border(
    project_path: str,
    map_name: str,
    metatile_ids: list[list[int]],
    collision_ids: list[list[int]] | None = None,
    elevation_ids: list[list[int]] | None = None,
    return_render: bool = False,
) -> Any:
    """Replace a map's repeating border tiles.

    metatile_ids is a 2-D list [row][col] of size border_height x
    border_width (read via get_map_info). Idempotent.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      metatile_ids: 2-D grid of metatile ids matching the layout's
        declared border dimensions.
      collision_ids: optional 2-D grid of 0..3, or None to preserve.
      elevation_ids: optional 2-D grid of 0..15, or None to preserve.
      return_render: if True, attach a PNG render of the post-mutation
        map to the response.
    """
    return set_border(
        project_path,
        map_name,
        metatile_ids,
        collision_ids,
        elevation_ids,
        return_render=return_render,
    )


def _tool_create_map(
    project_path: str,
    name: str,
    group: str,
    width: int,
    height: int,
    primary_tileset: str,
    secondary_tileset: str,
    fill_metatile_id: int = 0,
    border_metatile_ids: list[list[int]] | None = None,
    header_overrides: dict[str, Any] | None = None,
    return_render: bool = False,
) -> Any:
    """Create a new map: writes 5 files and registers it everywhere.

    Naming is derived from `name` (bare PascalCase, e.g. "LittlerootTown"):
      MAP_LITTLEROOT_TOWN, LAYOUT_LITTLEROOT_TOWN, data/maps/LittlerootTown/,
      data/layouts/LittlerootTown/.

    DO NOT pass MAP_* or LAYOUT_* directly. Group is created if missing.
    Duplicate names raise. include/constants/map_groups.h is NOT touched
    (pret build scripts regenerate it).

    Args:
      project_path: project root.
      name: bare PascalCase.
      group: C symbol, e.g. "gMapGroup_TownsAndRoutes".
      width, height: positive ints in tiles.
      primary_tileset, secondary_tileset: C labels.
      fill_metatile_id: initial fill for layout + border (collision=0,
        elevation=0). Default 0.
      border_metatile_ids: optional 2-D border grid (default 2x2).
      header_overrides: dict of map.json header keys to override on top
        of the minimal defaults (MUS_NONE, WEATHER_NONE, etc.).
    """
    return create_map(
        project_path,
        name,
        group,
        width,
        height,
        primary_tileset,
        secondary_tileset,
        fill_metatile_id=fill_metatile_id,
        border_metatile_ids=border_metatile_ids,
        header_overrides=header_overrides,
        return_render=return_render,
    )


def _tool_resize_map(
    project_path: str,
    map_name: str,
    new_width: int,
    new_height: int,
    anchor: str = "top-left",
    fill_metatile_id: int = 0,
    return_render: bool = False,
) -> Any:
    """Resize a map's layout, preserving overlapping content.

    Existing content anchored at (0, 0); new cells filled with
    fill_metatile_id. Shrinking that would orphan any event is REFUSED
    with an error listing the events — call remove_event first.

    Only anchor="top-left" supported in v0.1.0.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      new_width, new_height: positive ints in tiles.
      anchor: "top-left" only for now.
      fill_metatile_id: 0..1023; value for newly-exposed cells.
    """
    return resize_map(
        project_path,
        map_name,
        new_width,
        new_height,
        anchor=anchor,
        fill_metatile_id=fill_metatile_id,
        return_render=return_render,
    )


# Avoid an unused-import warning while keeping the public surface tidy.
_KEEP_IMPORTED: tuple[Any, ...] = (MapBin, layoutsjson, mapgroups, mapjson)


def _tool_paint_prefab(
    project_path: str,
    map_name: str,
    prefab_name: str,
    x: int,
    y: int,
    return_render: bool = False,
) -> Any:
    """Stamp a named prefab at (x, y) (top-left anchor).

    Lists available prefabs via list_prefabs. Tileset compatibility is
    enforced: if the prefab declares required primary/secondary tilesets,
    the target map's layout must match. No auto-import.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      prefab_name: built-in prefab name (e.g. "house_small").
      x, y: top-left anchor (must satisfy x+width<=map.width and
        y+height<=map.height).
    """
    return paint_prefab(project_path, map_name, prefab_name, x, y, return_render=return_render)


__all__ = [
    "create_map",
    "flood_fill",
    "paint_metatile",
    "paint_prefab",
    "paint_rectangle",
    "register",
    "resize_map",
    "set_border",
]
