"""Deterministically build the case 05 synthetic project and reference render.

This script is reproducible: running it from a clean tree produces the exact
same ``project/`` directory tree and the exact same ``reference.png`` byte-for-
byte (every byte is determined by constants in this file).

Run from the repo root:

    python tests/fixtures/renders/case_05_synthetic_edge/build_project.py

What it builds:

- A complete pokeemerald-shape project under ``project/`` exercising
  triple-layer metatiles, a custom 4x4 border, multiple elevation values,
  cross-tileset palette references, and the bank-padding code path
  (primary tileset has < 512 metatile slots).
- A render of ``MAP_EDGECASETOWN`` (with border) saved to ``reference.png``.

The regression test in ``tests/integration/test_fidelity.py`` then loads
``reference.png``, re-renders the project, and asserts pixel equality.
"""

from __future__ import annotations

import base64
import json
import shutil
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from porymap_mcp.render.compose import PALETTE_SIZE
from porymap_mcp.tools import rendering as render_tools

# --------------------------------------------------------------------------
# Output paths
# --------------------------------------------------------------------------

CASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CASE_DIR / "project"
REFERENCE_PNG = CASE_DIR / "reference.png"

# --------------------------------------------------------------------------
# Project shape — names and dimensions
# --------------------------------------------------------------------------

MAP_BARE = "EdgeCaseTown"
MAP_ID = "MAP_EDGECASETOWN"
LAYOUT_ID = "LAYOUT_EDGECASETOWN"

MAP_WIDTH = 30
MAP_HEIGHT = 20

# Custom 4x4 border — exercises use_custom_border_size=1.
BORDER_WIDTH = 4
BORDER_HEIGHT = 4

PRIMARY_TILESET_NAME = "edge_primary"
SECONDARY_TILESET_NAME = "edge_secondary"
PRIMARY_LABEL = "gTileset_EdgePrimary"
SECONDARY_LABEL = "gTileset_EdgeSecondary"

# --------------------------------------------------------------------------
# Tileset shape — slot counts. Primary < 512 metatile slots forces the
# bank-padding code path in _build_combined_metatile_bank.
# --------------------------------------------------------------------------

NUM_PRIMARY_METATILES = 64  # well under the 512 cap
NUM_SECONDARY_METATILES = 8

NUM_PRIMARY_TILES = 16
NUM_SECONDARY_TILES = 16

# --------------------------------------------------------------------------
# Palette colours (all multiples of 8 so GBA 5-bit quantization is a no-op)
# --------------------------------------------------------------------------

# Each palette slot is a single solid colour. Slots 0..5 belong to the
# primary tileset's palettes/; slots 6..12 belong to the secondary
# tileset's palettes/. The combined palette bank has 13 entries.
PALETTE_RGBS: dict[int, tuple[int, int, int]] = {
    0: (16, 80, 16),  # 0 — dark green (tree top)
    1: (48, 152, 48),  # 1 — grass green
    2: (224, 200, 144),  # 2 — sand / dirt
    3: (192, 160, 96),  # 3 — path / wood
    4: (160, 56, 56),  # 4 — brick red
    5: (88, 56, 24),  # 5 — dark brown (tree trunk)
    6: (24, 56, 168),  # 6 — water blue (secondary palette)
    7: (240, 240, 224),  # 7 — bone white (secondary palette)
    8: (128, 128, 128),  # 8 — neutral grey
    9: (0, 0, 0),  # 9..12 unused — black
    10: (0, 0, 0),
    11: (0, 0, 0),
    12: (0, 0, 0),
}

# --------------------------------------------------------------------------
# Metatile design.
#
# Naming convention: each named constant is a metatile id (combined bank
# index — primary slot ids are 0..NUM_PRIMARY_METATILES-1, secondary slot
# ids are 512..512+NUM_SECONDARY_METATILES-1).
#
# Slots 0..(NUM_PRIMARY_METATILES-1) are built below in `_primary_metatiles`.
# Slots 512..(512+NUM_SECONDARY_METATILES-1) are built in `_secondary_metatiles`.
# --------------------------------------------------------------------------

# Primary metatiles — solid colour, palette varies by id. Each metatile has
# a LayerType chosen to exercise one of {Normal, Covered, Split}.
GRASS = 0  # palette 1, LayerType=Normal
SAND = 1  # palette 2, LayerType=Normal
PATH = 2  # palette 3, LayerType=Normal
TREE_BOTTOM = 3  # palette 5, LayerType=Normal (trunk)
TREE_TOP = 4  # palette 0, LayerType=Covered (canopy: top layer non-trivial)
BRICK = 5  # palette 4, LayerType=Normal
GREY = 6  # palette 8, LayerType=Split (middle layer non-trivial)
TRIPLE = 7  # palette 0+1+3, LayerType ignored (all three layers in file)

# Secondary metatiles — referenced by combined indices 512+i.
WATER = 512  # palette 6 (secondary slot)
SIGN = 513  # palette 7 (secondary slot)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _tile_word(tile_id: int, palette_num: int, *, xflip: bool = False, yflip: bool = False) -> int:
    return (
        (tile_id & 0x03FF)
        | ((1 if xflip else 0) << 10)
        | ((1 if yflip else 0) << 11)
        | ((palette_num & 0x0F) << 12)
    )


def _solid_tile_words(palette_num: int, count: int) -> list[int]:
    """``count`` tile entries, all pointing at tile 0 with the given palette."""
    return [_tile_word(0, palette_num) for _ in range(count)]


def _pack_words(words: list[int]) -> bytes:
    return b"".join(struct.pack("<H", w) for w in words)


def _layer_type_byte(layer_type: int) -> int:
    """LayerType lives in attribute bits 13-14 (mask 0x6000 in pokeemerald cfg)."""
    return (layer_type & 0x03) << 13


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_indexed_png(path: Path, indices: np.ndarray) -> None:
    img = Image.fromarray(indices.astype(np.uint8), mode="P")
    img.putpalette([v for i in range(256) for v in (i, i, i)])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _make_jasc(rgb: tuple[int, int, int]) -> str:
    # All 16 entries are the same solid RGB, including index 0. This makes
    # palette-index choice in tiles irrelevant to the pixel colour.
    body = "\n".join(f"{rgb[0]} {rgb[1]} {rgb[2]}" for _ in range(PALETTE_SIZE))
    return f"JASC-PAL\n0100\n{PALETTE_SIZE}\n{body}\n"


# --------------------------------------------------------------------------
# Build the primary + secondary metatiles in triple-layer mode (24 bytes per
# metatile = 12 tile entries x 2 bytes; LayerType controls which layers are
# "real" vs filled from unused_tile_*).
# --------------------------------------------------------------------------


def _triple_layer_metatile(layer0: list[int], layer1: list[int], layer2: list[int]) -> bytes:
    """A triple-layer metatile is 12 tile entries: 4 for bottom, middle, top."""
    assert len(layer0) == 4
    assert len(layer1) == 4
    assert len(layer2) == 4
    return _pack_words(layer0 + layer1 + layer2)


# 4 tile entries per layer, all pointing at tile 0 of the bank with a chosen palette.
def _layer_solid(palette_num: int) -> list[int]:
    return _solid_tile_words(palette_num, 4)


def _empty_layer() -> list[int]:
    # Palette 0 of tile 0 — but in our palettes index-0 is the same as any
    # other index (solid fill). For "empty" semantics we'd want tile that
    # is transparent on upper layers — palette-0 index-0 IS alpha-0 from
    # decode_palette_bank's index-0 mask. So upper layers using this read
    # as fully transparent.
    return _solid_tile_words(0, 4)


def _primary_metatiles_bin() -> tuple[bytes, bytes]:
    """Return (metatiles.bin bytes, metatile_attributes.bin bytes)."""
    metas: list[bytes] = []
    attrs: list[int] = []

    # Layout of each primary metatile is chosen to make the rendered cell
    # a single solid colour (so visual inspection of the corpus is easy),
    # while still exercising every LayerType branch.

    # GRASS — palette 1, all 3 layers same colour, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(1), _layer_solid(1), _layer_solid(1)))
    attrs.append(_layer_type_byte(0))  # Normal

    # SAND — palette 2, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(2), _layer_solid(2), _layer_solid(2)))
    attrs.append(_layer_type_byte(0))

    # PATH — palette 3, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(3), _layer_solid(3), _layer_solid(3)))
    attrs.append(_layer_type_byte(0))

    # TREE_BOTTOM — palette 5 trunk, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(5), _layer_solid(5), _layer_solid(5)))
    attrs.append(_layer_type_byte(0))

    # TREE_TOP — palette 0 canopy, LayerType=Covered (top layer over bottom)
    metas.append(_triple_layer_metatile(_layer_solid(0), _layer_solid(0), _layer_solid(0)))
    attrs.append(_layer_type_byte(1))  # Covered

    # BRICK — palette 4, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(4), _layer_solid(4), _layer_solid(4)))
    attrs.append(_layer_type_byte(0))

    # GREY — palette 8, LayerType=Split (middle non-trivial)
    metas.append(_triple_layer_metatile(_layer_solid(8), _layer_solid(8), _layer_solid(8)))
    attrs.append(_layer_type_byte(2))  # Split

    # TRIPLE — all 3 layers same colour palette 1 (visually grass), LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(1), _layer_solid(1), _layer_solid(1)))
    attrs.append(_layer_type_byte(0))

    # Pad with empty grey metatiles to reach NUM_PRIMARY_METATILES (forces
    # bank-padding path on the combined bank).
    while len(metas) < NUM_PRIMARY_METATILES:
        metas.append(_triple_layer_metatile(_layer_solid(8), _layer_solid(8), _layer_solid(8)))
        attrs.append(_layer_type_byte(0))

    return b"".join(metas), b"".join(struct.pack("<H", a) for a in attrs)


def _secondary_metatiles_bin() -> tuple[bytes, bytes]:
    metas: list[bytes] = []
    attrs: list[int] = []

    # WATER — palette 6, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(6), _layer_solid(6), _layer_solid(6)))
    attrs.append(_layer_type_byte(0))

    # SIGN — palette 7, LayerType=Normal
    metas.append(_triple_layer_metatile(_layer_solid(7), _layer_solid(7), _layer_solid(7)))
    attrs.append(_layer_type_byte(0))

    # Pad to NUM_SECONDARY_METATILES with neutral grey
    while len(metas) < NUM_SECONDARY_METATILES:
        metas.append(_triple_layer_metatile(_layer_solid(8), _layer_solid(8), _layer_solid(8)))
        attrs.append(_layer_type_byte(0))

    return b"".join(metas), b"".join(struct.pack("<H", a) for a in attrs)


# --------------------------------------------------------------------------
# Build the layout grid + elevations + collision
# --------------------------------------------------------------------------


def _build_grid() -> list[list[tuple[int, int, int]]]:
    """Returns a (height x width) grid of (metatile_id, collision, elevation)."""
    grid: list[list[tuple[int, int, int]]] = [
        [(GRASS, 0, 0) for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)
    ]

    # Trees along the north edge (top row of trunks + row above of canopy)
    for x in range(MAP_WIDTH):
        grid[0][x] = (TREE_TOP, 1, 0)
        grid[1][x] = (TREE_BOTTOM, 1, 0)

    # Sand band on rows 17-18, water on row 19
    for x in range(MAP_WIDTH):
        grid[17][x] = (SAND, 0, 1)
        grid[18][x] = (SAND, 0, 1)
        grid[19][x] = (WATER, 1, 1)

    # Vertical path running N-S at x=15, from row 2 down to row 16, elev=2
    for y in range(2, 17):
        grid[y][15] = (PATH, 0, 2)

    # Triangular cluster of bricks (a "building") around (5, 10)..(8, 13)
    for y in range(10, 14):
        for x in range(5, 9):
            grid[y][x] = (BRICK, 1, 3)

    # Grey "platform" at higher elevation around (20, 8)..(25, 11)
    for y in range(8, 12):
        for x in range(20, 26):
            grid[y][x] = (GREY, 0, 5)

    # Sign at (16, 16) and (14, 8) — exercises secondary-tileset reference
    grid[16][16] = (SIGN, 1, 2)
    grid[8][14] = (SIGN, 1, 2)

    # Single triple-marker cell to ensure TRIPLE is in the corpus
    grid[5][5] = (TRIPLE, 0, 4)

    return grid


def _pack_map_bin(grid: list[list[tuple[int, int, int]]]) -> bytes:
    """Pack a grid into the dual-coded map.bin format (uint16 LE per cell)."""
    out = bytearray()
    for row in grid:
        for metatile_id, collision, elevation in row:
            # Layout per ADR-0006 §"Tile coding": bits 0-9 = metatile_id,
            # 10-11 = collision, 12-15 = elevation.
            packed = (
                (metatile_id & 0x03FF) | ((collision & 0x03) << 10) | ((elevation & 0x0F) << 12)
            )
            out.extend(struct.pack("<H", packed))
    return bytes(out)


def _build_border_grid() -> list[list[tuple[int, int, int]]]:
    """4x4 custom border: alternating tree-top / tree-bottom checker pattern."""
    border: list[list[tuple[int, int, int]]] = []
    for y in range(BORDER_HEIGHT):
        row: list[tuple[int, int, int]] = []
        for x in range(BORDER_WIDTH):
            mid = TREE_TOP if (x + y) % 2 == 0 else TREE_BOTTOM
            row.append((mid, 1, 0))
        border.append(row)
    return border


# --------------------------------------------------------------------------
# Project skeleton — JSON + .cfg
# --------------------------------------------------------------------------


PROJECT_CFG = (
    "base_game_version=pokeemerald\n"
    "use_poryscript=0\n"
    "use_custom_border_size=1\n"
    "enable_triple_layer_metatiles=1\n"
    "metatile_attributes_size=2\n"
    "metatile_behavior_mask=0x00FF\n"
    "metatile_terrain_type_mask=0x3E00\n"
    "metatile_encounter_type_mask=0xC000\n"
    "metatile_layer_type_mask=0x6000\n"
    "unused_tile_normal=0x0000\n"
    "unused_tile_covered=0x0000\n"
    "unused_tile_split=0x0000\n"
)


def _layouts_json() -> str:
    return (
        json.dumps(
            {
                "layouts_table_label": "gMapLayouts",
                "layouts": [
                    {
                        "id": LAYOUT_ID,
                        "name": f"{MAP_BARE}_Layout",
                        "width": MAP_WIDTH,
                        "height": MAP_HEIGHT,
                        "primary_tileset": PRIMARY_LABEL,
                        "secondary_tileset": SECONDARY_LABEL,
                        "border_filepath": f"data/layouts/{MAP_BARE}/border.bin",
                        "blockdata_filepath": f"data/layouts/{MAP_BARE}/map.bin",
                        "border_width": BORDER_WIDTH,
                        "border_height": BORDER_HEIGHT,
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )


def _map_groups_json() -> str:
    return (
        json.dumps(
            {
                "group_order": ["gMapGroup_Synth"],
                "gMapGroup_Synth": [MAP_BARE],
            },
            indent=2,
        )
        + "\n"
    )


def _map_json() -> str:
    obj: dict[str, Any] = {
        "id": MAP_ID,
        "name": MAP_BARE,
        "layout": LAYOUT_ID,
        "music": "MUS_NONE",
        "region_map_section": "MAPSEC_NONE",
        "requires_flash": False,
        "weather": "WEATHER_NONE",
        "map_type": "MAP_TYPE_TOWN",
        "allow_cycling": True,
        "allow_escaping": False,
        "allow_running": True,
        "show_map_name": True,
        "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
        "object_events": [],
        "warp_events": [],
        "coord_events": [],
        "bg_events": [],
        "connections": [],
    }
    return json.dumps(obj, indent=2) + "\n"


# --------------------------------------------------------------------------
# Write everything
# --------------------------------------------------------------------------


def _write_tileset(
    project_root: Path,
    *,
    kind: str,
    name: str,
    metatiles_bin: bytes,
    attributes_bin: bytes,
    tile_count: int,
) -> None:
    base = project_root / "data" / "tilesets" / kind / name

    # tiles.png: tile_count tiles laid out horizontally, each 8x8. Every
    # tile is filled with palette index 1 (always opaque); since every
    # palette slot's index 1 is the same colour as the slot's index 0
    # (all 16 entries identical), this doesn't matter for pixel content.
    indices = np.ones((8, tile_count * 8), dtype=np.uint8)
    _write_indexed_png(base / "tiles.png", indices)

    # palettes/00..12.pal
    for slot in range(13):
        rgb = PALETTE_RGBS[slot]
        _write(base / "palettes" / f"{slot:02d}.pal", _make_jasc(rgb))

    _write_bytes(base / "metatiles.bin", metatiles_bin)
    _write_bytes(base / "metatile_attributes.bin", attributes_bin)


def build_project() -> None:
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)
    PROJECT_DIR.mkdir(parents=True)

    _write(PROJECT_DIR / "porymap.project.cfg", PROJECT_CFG)
    _write(PROJECT_DIR / "data" / "layouts" / "layouts.json", _layouts_json())
    _write(PROJECT_DIR / "data" / "maps" / "map_groups.json", _map_groups_json())
    _write(PROJECT_DIR / "data" / "maps" / MAP_BARE / "map.json", _map_json())

    primary_bin, primary_attrs = _primary_metatiles_bin()
    _write_tileset(
        PROJECT_DIR,
        kind="primary",
        name=PRIMARY_TILESET_NAME,
        metatiles_bin=primary_bin,
        attributes_bin=primary_attrs,
        tile_count=NUM_PRIMARY_TILES,
    )

    secondary_bin, secondary_attrs = _secondary_metatiles_bin()
    _write_tileset(
        PROJECT_DIR,
        kind="secondary",
        name=SECONDARY_TILESET_NAME,
        metatiles_bin=secondary_bin,
        attributes_bin=secondary_attrs,
        tile_count=NUM_SECONDARY_TILES,
    )

    grid = _build_grid()
    _write_bytes(
        PROJECT_DIR / "data" / "layouts" / MAP_BARE / "map.bin",
        _pack_map_bin(grid),
    )

    border_grid = _build_border_grid()
    _write_bytes(
        PROJECT_DIR / "data" / "layouts" / MAP_BARE / "border.bin",
        _pack_map_bin(border_grid),
    )


def render_reference() -> None:
    """Render the synthetic project and save the PNG bytes as reference.png."""
    result = render_tools.render_map(str(PROJECT_DIR), MAP_ID, include_border=True)
    block = result.content[0]
    assert block.type == "image"
    assert block.mimeType == "image/png"
    png_bytes = base64.b64decode(block.data)
    REFERENCE_PNG.write_bytes(png_bytes)
    rel = REFERENCE_PNG.relative_to(Path.cwd()) if REFERENCE_PNG.is_absolute() else REFERENCE_PNG
    print(f"  wrote {rel} ({len(png_bytes)} bytes)")


def main() -> int:
    print(f"Building synthetic project at {PROJECT_DIR}")
    build_project()
    print("Rendering reference image")
    render_reference()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
