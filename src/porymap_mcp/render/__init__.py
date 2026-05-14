"""L3 rendering pipeline (ADR-0010).

Decodes tileset graphics (``tiles.png`` + JASC ``.pal`` + ``metatiles.bin``) into
in-memory numpy banks, then composes them into a PNG that pixel-matches Porymap's
own Export Map Image output.

This package requires the ``render`` extra (numpy + Pillow). Importing it without
those installed raises a clear ``ImportError`` from numpy/PIL.
"""

from __future__ import annotations

from porymap_mcp.render.compose import (
    DUAL_LAYER_TILES_PER_METATILE,
    PALETTE_SIZE,
    TILE_SIZE,
    TRIPLE_LAYER_TILES_PER_METATILE,
    decode_metatile_bank,
    decode_palette_bank,
    decode_tile_bank,
)
from porymap_mcp.render.encode import (
    PALETTE_MODE_MAX_METATILES,
    EncodingName,
    encode_png,
    package_render_result,
)
from porymap_mcp.render.layout import (
    METATILE_SIZE,
    assemble,
    assemble_region,
    clip_region,
    mapbin_to_metatile_grid,
    tile_border_around,
)

__all__ = [
    "DUAL_LAYER_TILES_PER_METATILE",
    "METATILE_SIZE",
    "PALETTE_MODE_MAX_METATILES",
    "PALETTE_SIZE",
    "TILE_SIZE",
    "TRIPLE_LAYER_TILES_PER_METATILE",
    "EncodingName",
    "assemble",
    "assemble_region",
    "clip_region",
    "decode_metatile_bank",
    "decode_palette_bank",
    "decode_tile_bank",
    "encode_png",
    "mapbin_to_metatile_grid",
    "package_render_result",
    "tile_border_around",
]
