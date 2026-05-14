"""L3 rendering tools — wires :mod:`porymap_mcp.render` end-to-end.

Implements the three render tools listed in phase-4 §4 of the L3 plan:

  - ``render_map``        — full-map PNG render.
  - ``render_map_region`` — partial render of a half-open ``[x1,x2) x [y1,y2)`` rect.
  - ``render_metatile``   — single 16x16 metatile preview, optionally up-scaled.

Each tool returns a FastMCP :class:`fastmcp.tools.base.ToolResult` whose
``content[0]`` is the encoded PNG image and whose ``structured_content``
mirrors the L1 tools' summary-dict shape (ADR-0006 §"Convention shared by
all seven").

Numpy + Pillow live behind the ``render`` optional extra (ADR-0010). To
avoid breaking ``pip install porymap-mcp`` without that extra, every
heavy-weight import (numpy, PIL, the ``porymap_mcp.render`` submodules)
is **deferred inside the tool body**. Module import succeeds with only
the base dependencies; only invoking a tool requires the extra.

Hard-coded slot counts:
    Porymap's vanilla-pokeemerald defaults (``num_tiles_primary=512``,
    ``num_pals_primary=6``, ``num_pals_total=13``, implicit
    ``num_metatiles_primary=512``) live as module constants below. They
    are not yet surfaced as :class:`ProjectConfig` keys; a future ADR
    can expose them when a fork legitimately overrides one.

References:
    - Phase-4 doc §4 (signatures).
    - ADR-0010 §"MCP return shape".
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from porymap_mcp.errors import FormatError, PaletteFormatError, ProjectError
from porymap_mcp.parsers import attributes as attributes_parser
from porymap_mcp.parsers import metatiles as metatiles_parser
from porymap_mcp.parsers.attributes import AttributeMasks, MetatileAttributes
from porymap_mcp.parsers.layoutsjson import LayoutEntry
from porymap_mcp.parsers.mapbin import MAX_METATILE_ID, MapBin
from porymap_mcp.parsers.tileset import TilesetEntry
from porymap_mcp.project import Project
from porymap_mcp.tools._common import load_project as _load_project
from porymap_mcp.tools._common import posix_str as _posix_str

if TYPE_CHECKING:
    import numpy as np
    from fastmcp import FastMCP


# --- Vanilla pokeemerald slot counts --------------------------------------
#
# These mirror Porymap's defaults (``Project::num_tiles_primary`` etc. in
# ``porymap/src/project.cpp``). Forks override them via project.cfg keys
# we do not yet parse; a future ADR can surface them on :class:`ProjectConfig`.

NUM_TILES_PRIMARY: Final = 512
NUM_TILES_TOTAL: Final = 1024
NUM_METATILES_PRIMARY: Final = 512
NUM_METATILES_TOTAL: Final = 1024
NUM_PALETTES_PRIMARY: Final = 6
NUM_PALETTES_TOTAL: Final = 13

#: Largest ``scale`` accepted by the render tools — keeps a typo from
#: producing a 50k-pixel-square PNG. ``8x`` is comfortably above the
#: "preview at a glance" range these tools target.
MAX_RENDER_SCALE: Final = 8

#: Default frame thickness, in metatile units, applied per side when
#: ``include_border=True``. **Asymmetric** to mirror Porymap's
#: ``Metatile::pixelsPerMetatile`` view-distance computation: 7 metatiles
#: of horizontal margin (left and right), 5 of vertical (top and bottom).
#: These correspond to half of the GBA visible screen area (15x10
#: metatiles → 7.5x5 → rounded to 7x5).
DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL: Final = 7
DEFAULT_BORDER_FRAME_METATILES_VERTICAL: Final = 5


# --- Internal helpers -----------------------------------------------------


def _resolve_layout(project: Project, map_name: str) -> tuple[str, LayoutEntry]:
    _bare, _group, doc = project.get_map_entry(map_name)
    return doc.layout, project.get_layout(doc.layout)


def _load_tileset_pair(
    project: Project, layout_entry: LayoutEntry
) -> tuple[TilesetEntry, TilesetEntry]:
    """Resolve a layout's primary + secondary tileset C labels to disk entries."""
    primary = project.get_tileset_by_label(layout_entry.primary_tileset)
    secondary = project.get_tileset_by_label(layout_entry.secondary_tileset)
    if primary.kind != "primary":
        raise ProjectError(
            f"layout {layout_entry.id!r}: declared primary tileset "
            f"{layout_entry.primary_tileset!r} resolves to a {primary.kind} tileset entry."
        )
    if secondary.kind != "secondary":
        raise ProjectError(
            f"layout {layout_entry.id!r}: declared secondary tileset "
            f"{layout_entry.secondary_tileset!r} resolves to a {secondary.kind} tileset entry."
        )
    return primary, secondary


def _build_combined_tile_bank(
    project: Project, primary: TilesetEntry, secondary: TilesetEntry
) -> np.ndarray:
    """Decode primary + secondary ``tiles.png`` into one ``[1024, 8, 8]`` bank.

    Primary tiles populate slots ``0..NUM_TILES_PRIMARY-1``; secondary tiles
    populate ``NUM_TILES_PRIMARY..NUM_TILES_TOTAL-1``. Any slot a tileset does
    not fill stays zero — metatile composition silently skips out-of-range
    or all-zero tile references (matches Porymap's behaviour).
    """
    import numpy as np

    from porymap_mcp.render.compose import TILE_SIZE, decode_tile_bank

    primary_tiles = decode_tile_bank(project.resolve_path(primary.tiles_path))
    secondary_tiles = decode_tile_bank(project.resolve_path(secondary.tiles_path))

    bank = np.zeros((NUM_TILES_TOTAL, TILE_SIZE, TILE_SIZE), dtype=np.uint8)
    p_n = min(int(primary_tiles.shape[0]), NUM_TILES_PRIMARY)
    bank[:p_n] = primary_tiles[:p_n]
    s_cap = NUM_TILES_TOTAL - NUM_TILES_PRIMARY
    s_n = min(int(secondary_tiles.shape[0]), s_cap)
    bank[NUM_TILES_PRIMARY : NUM_TILES_PRIMARY + s_n] = secondary_tiles[:s_n]
    return bank


def _build_combined_palette_bank(
    project: Project, primary: TilesetEntry, secondary: TilesetEntry
) -> np.ndarray:
    """Decode 13 palettes — 6 from primary, 7 from secondary — into one bank.

    Returns ``uint8[NUM_PALETTES_TOTAL, 16, 4]``. Files are
    ``palettes/{i:02d}.pal``; primary supplies slots 0..5 and secondary
    supplies 6..12. Missing files surface as :class:`PaletteFormatError`
    — every vanilla pokeemerald tileset ships all 13 .pal files.
    """
    import numpy as np

    from porymap_mcp.render.compose import PALETTE_SIZE, decode_palette_bank

    primary_palettes_dir = project.resolve_path(primary.palettes_dir)
    secondary_palettes_dir = project.resolve_path(secondary.palettes_dir)

    primary_paths = [primary_palettes_dir / f"{i:02d}.pal" for i in range(NUM_PALETTES_PRIMARY)]
    secondary_paths = [
        secondary_palettes_dir / f"{i:02d}.pal"
        for i in range(NUM_PALETTES_PRIMARY, NUM_PALETTES_TOTAL)
    ]
    for path in (*primary_paths, *secondary_paths):
        if not path.is_file():
            raise PaletteFormatError(
                f"palette file missing: {path}. "
                f"L3 rendering requires {NUM_PALETTES_TOTAL} palettes "
                f"({NUM_PALETTES_PRIMARY} from the primary tileset, "
                f"{NUM_PALETTES_TOTAL - NUM_PALETTES_PRIMARY} from the secondary)."
            )
    primary_bank = decode_palette_bank(primary_paths)
    secondary_bank = decode_palette_bank(secondary_paths)

    bank = np.zeros((NUM_PALETTES_TOTAL, PALETTE_SIZE, 4), dtype=np.uint8)
    bank[:NUM_PALETTES_PRIMARY] = primary_bank
    bank[NUM_PALETTES_PRIMARY:NUM_PALETTES_TOTAL] = secondary_bank
    return bank


def _read_metatile_attributes(
    project: Project,
    tileset: TilesetEntry,
    metatile_count: int,
) -> tuple[MetatileAttributes, ...]:
    """Decode ``metatile_attributes.bin`` for ``tileset``.

    Falls back to all-zero attributes (``LayerType=Normal``) when the file
    is absent or fails to parse — matches Porymap's tolerance for missing
    attributes (the renderer keeps working; behaviours are simply unset).
    """
    cfg = project.config
    attr_path = project.resolve_path(tileset.attributes_path)
    masks = AttributeMasks(
        behavior=cfg.metatile_behavior_mask,
        terrain_type=cfg.metatile_terrain_type_mask,
        encounter_type=cfg.metatile_encounter_type_mask,
        layer_type=cfg.metatile_layer_type_mask,
    )
    if not attr_path.is_file():
        return tuple(
            MetatileAttributes(behavior=0, terrain_type=0, encounter_type=0, layer_type=0, raw=0)
            for _ in range(metatile_count)
        )
    try:
        return attributes_parser.read(
            attr_path.read_bytes(),
            attribute_size=cfg.metatile_attributes_size,
            masks=masks,
            expected_count=metatile_count,
        )
    except FormatError:
        return tuple(
            MetatileAttributes(behavior=0, terrain_type=0, encounter_type=0, layer_type=0, raw=0)
            for _ in range(metatile_count)
        )


def _build_combined_metatile_bank(
    project: Project,
    primary: TilesetEntry,
    secondary: TilesetEntry,
    tile_bank: np.ndarray,
    palette_bank: np.ndarray,
) -> np.ndarray:
    """Decode + concatenate primary and secondary metatile banks.

    Returns ``uint8[N, 16, 16, 4]`` where ``N`` is ``NUM_METATILES_PRIMARY +
    secondary_count``. Primary metatiles occupy slots ``0..511``; secondary
    metatiles occupy ``512..512+secondary_count-1``. Any short primary is
    zero-padded so secondary metatiles always land at index 512.
    """
    import numpy as np

    from porymap_mcp.render.compose import decode_metatile_bank

    cfg = project.config
    triple = cfg.enable_triple_layer_metatiles
    layers = 3 if triple else 2

    def _decode(entry: TilesetEntry) -> np.ndarray:
        bin_path = project.resolve_path(entry.metatiles_path)
        if not bin_path.is_file():
            raise FormatError(f"metatiles.bin missing for tileset {entry.name!r}: {bin_path}")
        raw = bin_path.read_bytes()
        count = metatiles_parser.count_metatiles(raw, triple_layer=triple)
        attrs = _read_metatile_attributes(project, entry, count)
        return decode_metatile_bank(
            raw,
            attrs,
            tile_bank,
            palette_bank,
            layers=layers,
            unused_tile_normal=cfg.unused_tile_normal,
            unused_tile_covered=cfg.unused_tile_covered,
            unused_tile_split=cfg.unused_tile_split,
            transparency_color=cfg.transparency_color,
        )

    primary_bank = _decode(primary)
    secondary_bank = _decode(secondary)

    if int(primary_bank.shape[0]) > NUM_METATILES_PRIMARY:
        raise FormatError(
            f"primary tileset {primary.name!r} has "
            f"{int(primary_bank.shape[0])} metatiles, exceeding the "
            f"{NUM_METATILES_PRIMARY}-slot primary range. Resize the tileset "
            "or split it across primary/secondary."
        )
    s_cap = NUM_METATILES_TOTAL - NUM_METATILES_PRIMARY
    if int(secondary_bank.shape[0]) > s_cap:
        raise FormatError(
            f"secondary tileset {secondary.name!r} has "
            f"{int(secondary_bank.shape[0])} metatiles, exceeding the "
            f"{s_cap}-slot secondary range."
        )

    pad_n = NUM_METATILES_PRIMARY - int(primary_bank.shape[0])
    if pad_n > 0:
        pad = np.zeros((pad_n, *primary_bank.shape[1:]), dtype=primary_bank.dtype)
        primary_bank = np.concatenate([primary_bank, pad], axis=0)
    return np.concatenate([primary_bank, secondary_bank], axis=0)


def _scale_nearest(rgba: np.ndarray, scale: int) -> np.ndarray:
    """Up-scale an RGBA buffer with nearest-neighbor (no smoothing).

    Implemented as a numpy repeat to avoid a Pillow round-trip. A scale of
    1 is a no-op (returns the input unchanged so callers can skip the copy).
    """
    if scale == 1:
        return rgba
    return rgba.repeat(scale, axis=0).repeat(scale, axis=1)


def _check_scale(scale: int) -> None:
    if not 1 <= scale <= MAX_RENDER_SCALE:
        raise ProjectError(f"scale must be an integer in 1..{MAX_RENDER_SCALE}, got {scale}.")


def _check_overlays_supported(overlays: list[str]) -> None:
    """Validate every requested overlay against the supported menu.

    The actual dispatch happens inside :func:`render_map` /
    :func:`render_map_region`; this helper exists so callers fail fast
    on a typo *before* the (more expensive) tile/palette/metatile bank
    decode runs.
    """
    if not overlays:
        return
    from porymap_mcp.render.overlays import SUPPORTED_OVERLAYS

    for name in overlays:
        if name not in SUPPORTED_OVERLAYS:
            raise ProjectError(f"unknown overlay {name!r}. Supported: {SUPPORTED_OVERLAYS}.")


# --- 1. render_map --------------------------------------------------------


def render_map(
    project_path: str,
    map_name: str,
    overlays: list[str] | None = None,
    include_border: bool = False,
    scale: int = 1,
) -> Any:
    """Render a full map to PNG.

    See phase-4 §4 for the signature. Returns a :class:`fastmcp.tools.base.ToolResult`.
    """
    overlays_list = list(overlays) if overlays is not None else []
    _check_overlays_supported(overlays_list)
    _check_scale(scale)

    project = _load_project(project_path)
    layout_id, layout_entry = _resolve_layout(project, map_name)
    primary, secondary = _load_tileset_pair(project, layout_entry)

    from porymap_mcp.render.encode import encode_png, package_render_result
    from porymap_mcp.render.layout import (
        assemble,
        mapbin_to_metatile_grid,
        tile_border_around,
    )
    from porymap_mcp.render.overlays import apply_overlays

    tile_bank = _build_combined_tile_bank(project, primary, secondary)
    palette_bank = _build_combined_palette_bank(project, primary, secondary)
    metatile_bank = _build_combined_metatile_bank(
        project, primary, secondary, tile_bank, palette_bank
    )

    map_bin = project.read_map_bin(layout_id)
    grid = mapbin_to_metatile_grid(map_bin)
    rgba = assemble(metatile_bank, grid)

    border_extra: dict[str, Any] = {}
    frame_offset_px = (0, 0)
    if include_border:
        border_bin = project.read_border_bin(layout_id)
        border_grid = mapbin_to_metatile_grid(border_bin)
        border_rgba = assemble(metatile_bank, border_grid)
        rgba = tile_border_around(
            rgba,
            border_rgba,
            frame_width_metatiles=DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL,
            frame_height_metatiles=DEFAULT_BORDER_FRAME_METATILES_VERTICAL,
        )
        frame_offset_px = (
            DEFAULT_BORDER_FRAME_METATILES_VERTICAL * 16,
            DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL * 16,
        )
        border_extra = {
            "border_dimensions": {"width": border_bin.width, "height": border_bin.height},
            "border_frame_metatiles": {
                "horizontal": DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL,
                "vertical": DEFAULT_BORDER_FRAME_METATILES_VERTICAL,
            },
        }

    if overlays_list:
        # Need the map's events for the "events" overlay; the L1 layer
        # already cached the parsed map.json once via _resolve_layout above.
        map_json = project.get_map_json(map_name)
        apply_overlays(
            rgba,
            tuple(overlays_list),
            map_bin=map_bin,
            map_json=map_json,
            frame_offset_px=frame_offset_px,
        )

    rgba = _scale_nearest(rgba, scale)

    # area_metatiles is the threshold for palette-vs-RGBA mode. With border
    # included the rendered image grows by the frame; encode_png compares
    # *metatiles*, so reflect the full output extent here.
    horiz_pad = 2 * DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL if include_border else 0
    vert_pad = 2 * DEFAULT_BORDER_FRAME_METATILES_VERTICAL if include_border else 0
    metatiles_w = layout_entry.width + horiz_pad
    metatiles_h = layout_entry.height + vert_pad
    area = metatiles_w * metatiles_h
    # Overlays alpha-blend many intermediate RGB values; palette mode
    # would lose to the > 256 colour cap, so force RGBA when any overlay
    # was applied (ADR-0010 §"PNG encoding").
    png_bytes, encoding = encode_png(rgba, area_metatiles=area, force_rgba=bool(overlays_list))

    summary = (
        f"Rendered {map_name} ({layout_entry.width}x{layout_entry.height} metatiles, "
        f"scale={scale}x{', border included' if include_border else ''}) -> "
        f"{len(png_bytes)} byte PNG ({encoding})."
    )
    extra: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "layout_id": layout_id,
        "dimensions": {"width": layout_entry.width, "height": layout_entry.height},
        "pixel_dimensions": {"width": int(rgba.shape[1]), "height": int(rgba.shape[0])},
        "scale": scale,
        "encoding": encoding,
        "byte_size": len(png_bytes),
        "tilesets": {"primary": primary.name, "secondary": secondary.name},
        "include_border": include_border,
        "overlays": overlays_list,
        **border_extra,
    }
    return package_render_result(png_bytes, summary=summary, extra=extra)


# --- 2. render_map_region -------------------------------------------------


def render_map_region(
    project_path: str,
    map_name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    overlays: list[str] | None = None,
    scale: int = 1,
) -> Any:
    """Render a half-open ``[x1, x2) x [y1, y2)`` slice of a map to PNG.

    Coordinates are in metatile units, top-left origin. Strict bounds: any
    region that escapes the layout grid raises :class:`ProjectError` —
    callers should clip via ``get_map_info`` first.
    """
    overlays_list = list(overlays) if overlays is not None else []
    _check_overlays_supported(overlays_list)
    _check_scale(scale)

    project = _load_project(project_path)
    layout_id, layout_entry = _resolve_layout(project, map_name)

    width, height = layout_entry.width, layout_entry.height
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ProjectError(
            f"render_map_region: region (x1={x1}, y1={y1}, x2={x2}, y2={y2}) "
            f"is invalid for the {width}x{height} {map_name} layout "
            "(expected 0 <= x1 < x2 <= width, 0 <= y1 < y2 <= height)."
        )

    primary, secondary = _load_tileset_pair(project, layout_entry)

    from porymap_mcp.render.encode import encode_png, package_render_result
    from porymap_mcp.render.layout import assemble_region, mapbin_to_metatile_grid
    from porymap_mcp.render.overlays import apply_overlays

    tile_bank = _build_combined_tile_bank(project, primary, secondary)
    palette_bank = _build_combined_palette_bank(project, primary, secondary)
    metatile_bank = _build_combined_metatile_bank(
        project, primary, secondary, tile_bank, palette_bank
    )

    map_bin = project.read_map_bin(layout_id)
    grid = mapbin_to_metatile_grid(map_bin)
    rgba = assemble_region(metatile_bank, grid, x1=x1, y1=y1, x2=x2, y2=y2)

    if overlays_list:
        # Region overlays operate on a sub-buffer of the layout. We build a
        # MapBin for the region (so collision/elevation/grid cover the
        # right cells) and pass the full map_json — events outside the
        # region get clipped silently by the overlay's bounds check, and
        # the offset is the region's top-left in source coordinates,
        # mirrored back to the sub-buffer's (0, 0).
        region_mapbin = MapBin(
            width=x2 - x1,
            height=y2 - y1,
            tiles=tuple(row[x1:x2] for row in map_bin.tiles[y1:y2]),
        )
        # Shift event coords back into the sub-buffer's frame by passing a
        # negative offset (events.x*16 + offset_x → relative-to-region).
        events_offset_px = (-y1 * 16, -x1 * 16)
        map_json = project.get_map_json(map_name)
        # collision/elevation/grid get the region-clipped map_bin so they
        # paint inside the sub-buffer; events get the unclipped map_json
        # with a negative offset so out-of-region events naturally clip.
        apply_overlays(
            rgba,
            tuple(o for o in overlays_list if o != "events"),
            map_bin=region_mapbin,
            map_json=map_json,
            frame_offset_px=(0, 0),
        )
        if "events" in overlays_list:
            apply_overlays(
                rgba,
                ("events",),
                map_bin=region_mapbin,
                map_json=map_json,
                frame_offset_px=events_offset_px,
            )

    rgba = _scale_nearest(rgba, scale)

    region_w = x2 - x1
    region_h = y2 - y1
    area = region_w * region_h
    png_bytes, encoding = encode_png(rgba, area_metatiles=area, force_rgba=bool(overlays_list))

    summary = (
        f"Rendered {map_name} region ({x1},{y1})-({x2},{y2}) "
        f"[{region_w}x{region_h} metatiles, scale={scale}x] -> "
        f"{len(png_bytes)} byte PNG ({encoding})."
    )
    extra: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "layout_id": layout_id,
        "region": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "dimensions": {"width": region_w, "height": region_h},
        "pixel_dimensions": {"width": int(rgba.shape[1]), "height": int(rgba.shape[0])},
        "scale": scale,
        "encoding": encoding,
        "byte_size": len(png_bytes),
        "tilesets": {"primary": primary.name, "secondary": secondary.name},
        "overlays": overlays_list,
    }
    return package_render_result(png_bytes, summary=summary, extra=extra)


# --- 3. render_metatile ---------------------------------------------------


def render_metatile(
    project_path: str,
    tileset_name: str,
    metatile_id: int,
    scale: int = 4,
) -> Any:
    """Render one metatile from one tileset to PNG.

    The companion tileset (other half of the primary/secondary pair) is
    required for metatile composition because ``Tile`` entries can
    reference the other half's tiles and palettes. For a primary tileset
    we pair with any secondary that exists in the project (the first one
    in discovery order); for a secondary, the converse. The pairing only
    matters for cross-tileset tile/palette references; metatiles that only
    reference their own tileset render identically regardless of pairing.
    """
    _check_scale(scale)
    if not 0 <= metatile_id <= MAX_METATILE_ID:
        raise ProjectError(f"metatile_id 0x{metatile_id:X} out of range 0..0x{MAX_METATILE_ID:X}.")

    project = _load_project(project_path)
    entry = project.get_tileset_by_name(tileset_name)
    companion = _pick_companion(project, entry)
    if entry.kind == "primary":
        primary, secondary = entry, companion
    else:
        primary, secondary = companion, entry

    from porymap_mcp.render.encode import encode_png, package_render_result
    from porymap_mcp.render.layout import METATILE_SIZE

    tile_bank = _build_combined_tile_bank(project, primary, secondary)
    palette_bank = _build_combined_palette_bank(project, primary, secondary)
    metatile_bank = _build_combined_metatile_bank(
        project, primary, secondary, tile_bank, palette_bank
    )

    if metatile_id >= int(metatile_bank.shape[0]):
        raise ProjectError(
            f"metatile_id {metatile_id} not present in the "
            f"{primary.name!r}+{secondary.name!r} pair "
            f"(only {int(metatile_bank.shape[0])} metatile slots available)."
        )

    rgba = metatile_bank[metatile_id].copy()
    rgba = _scale_nearest(rgba, scale)
    png_bytes, encoding = encode_png(rgba, area_metatiles=1)

    summary = (
        f"Rendered metatile 0x{metatile_id:03X} of tileset {tileset_name!r} "
        f"(scale={scale}x) -> {len(png_bytes)} byte PNG ({encoding})."
    )
    extra: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "tileset_name": tileset_name,
        "tileset_kind": entry.kind,
        "companion_tileset": companion.name,
        "metatile_id": metatile_id,
        "pixel_dimensions": {
            "width": METATILE_SIZE * scale,
            "height": METATILE_SIZE * scale,
        },
        "scale": scale,
        "encoding": encoding,
        "byte_size": len(png_bytes),
    }
    return package_render_result(png_bytes, summary=summary, extra=extra)


def _pick_companion(project: Project, entry: TilesetEntry) -> TilesetEntry:
    """Pick a companion tileset of the opposite ``kind`` for metatile composition.

    Returns the first tileset in discovery order whose ``kind`` is the
    opposite of ``entry.kind``. Raises if no companion exists — a project
    with zero primaries or zero secondaries cannot render anything.
    """
    target_kind = "secondary" if entry.kind == "primary" else "primary"
    for candidate in project.tilesets:
        if candidate.kind == target_kind:
            return candidate
    raise ProjectError(
        f"no {target_kind} tileset available to pair with {entry.name!r} "
        f"({entry.kind}). render_metatile requires both a primary and a "
        "secondary tileset to compose a complete bank."
    )


# --- FastMCP registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Attach all rendering tools to ``mcp``."""
    mcp.tool(name="render_map")(_tool_render_map)
    mcp.tool(name="render_map_region")(_tool_render_map_region)
    mcp.tool(name="render_metatile")(_tool_render_metatile)


def _tool_render_map(
    project_path: str,
    map_name: str,
    overlays: list[str] | None = None,
    include_border: bool = False,
    scale: int = 1,
) -> Any:
    """Render a map's full layout as a PNG image.

    Returns the rendered PNG as an MCP image content block plus a
    structured metadata dict (dimensions, encoding, byte size). Use this
    as the canonical "let me see what I just painted" tool after any
    layout mutation.

    Args:
      project_path: project root.
      map_name: MAP_* constant. Get from list_maps.
      overlays: subset of {"collision", "elevation", "grid", "events"}.
        Drawn alpha-blended on top of the base render, in order. Forces
        RGBA PNG output. Default [] (none).
      include_border: render the wrap-around border frame (7 metatiles
        per side, Porymap default). Default False.
      scale: integer up-scale factor (1..8), nearest-neighbor. Default 1.
    """
    return render_map(
        project_path,
        map_name,
        overlays=overlays,
        include_border=include_border,
        scale=scale,
    )


def _tool_render_map_region(
    project_path: str,
    map_name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    overlays: list[str] | None = None,
    scale: int = 1,
) -> Any:
    """Render a half-open rectangular slice of a map to PNG.

    Coordinates are in metatile units with the top-left origin Porymap
    uses; the rectangle is half-open [x1, x2) x [y1, y2). Useful for
    inspecting a single town inside a large region map, or the patch you
    just edited inside a 60x120 layout without spending the full render.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      x1, y1: top-left (inclusive) corner of the region.
      x2, y2: bottom-right (exclusive) corner.
      overlays: subset of {"collision", "elevation", "grid", "events"}.
        Same semantics as render_map; clipped to the region. Events
        outside the region are silently dropped. Forces RGBA output.
      scale: integer up-scale factor (1..8).
    """
    return render_map_region(
        project_path,
        map_name,
        x1,
        y1,
        x2,
        y2,
        overlays=overlays,
        scale=scale,
    )


def _tool_render_metatile(
    project_path: str,
    tileset_name: str,
    metatile_id: int,
    scale: int = 4,
) -> Any:
    """Render a single metatile from a tileset as a PNG.

    The metatile is composed using the requested tileset paired with the
    first opposite-kind tileset in the project (primary <-> secondary).
    This matters only for metatiles that reference the companion's tiles
    or palettes; same-tileset references render identically regardless of
    pairing.

    Args:
      project_path: project root.
      tileset_name: directory basename (NOT C label). Get from list_tilesets.
      metatile_id: 0..1023.
      scale: integer up-scale factor (1..8). Default 4 (yields a 64x64
        preview, comfortable to inspect visually).
    """
    return render_metatile(project_path, tileset_name, metatile_id, scale=scale)


# Keep the imported helpers referenced so ruff doesn't strip them when an
# editor reorders imports.
_KEEP_IMPORTED: tuple[Any, ...] = (Path, _resolve_layout)


__all__ = [
    "MAX_RENDER_SCALE",
    "NUM_METATILES_PRIMARY",
    "NUM_METATILES_TOTAL",
    "NUM_PALETTES_PRIMARY",
    "NUM_PALETTES_TOTAL",
    "NUM_TILES_PRIMARY",
    "NUM_TILES_TOTAL",
    "register",
    "render_map",
    "render_map_region",
    "render_metatile",
]
