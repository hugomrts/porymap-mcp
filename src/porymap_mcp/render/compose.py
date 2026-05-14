"""Tile + palette decoders for the L3 renderer.

This module implements the first half of ADR-0010's compose pipeline: read
``tiles.png`` into a tile bank of palette indices, and read JASC ``.pal`` files
into a palette bank of RGBA bytes with GBA hardware quantization applied.

The metatile composition pass (which combines the two banks with the
``unused_tile_*`` 3-layer rule per ADR-0010's composition table) lands in a
follow-up slice in this same module.

References:
    - ADR-0010 §"Source files read" #1 (``tiles.png``) and #2 (``.pal``).
    - Porymap reader: ``Tileset::loadTilesImage`` (src/core/tileset.cpp:558-623).
    - Porymap JASC parser: ``PaletteUtil::parseJASC`` (src/core/paletteutil.cpp:90-155).
    - GBA 5-bit hardware quantization rationale: ADR-0010 Risk 5.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
from PIL import Image, UnidentifiedImageError

from porymap_mcp.errors import (
    MetatilesBinFormatError,
    PaletteFormatError,
    TilesPngFormatError,
)
from porymap_mcp.parsers.attributes import MetatileAttributes

#: Side length of one tile, in pixels (GBA hardware constant).
TILE_SIZE: Final = 8

#: Number of colours per palette (GBA 4-bpp hardware constant).
PALETTE_SIZE: Final = 16

#: Tiles per 16x16 metatile in dual-layer mode (RSE / vanilla pokeemerald).
DUAL_LAYER_TILES_PER_METATILE: Final = 8

#: Tiles per 16x16 metatile in triple-layer mode (pokeemerald-expansion).
TRIPLE_LAYER_TILES_PER_METATILE: Final = 12

#: Top-left (y, x) of each of the 4 sub-tiles in the row-major 2x2 grid.
_QUAD_POSITIONS: Final = ((0, 0), (0, 8), (8, 0), (8, 8))


def decode_tile_bank(tiles_png_path: Path) -> np.ndarray:
    """Decode a tileset's ``tiles.png`` into a ``[num_tiles, 8, 8]`` index array.

    Porymap reads the source PNG directly rather than the compiled ``.4bpp``
    (ADR-0010 §"Source files read" #1). The PNG is conceptually 4-bpp indexed,
    but Pillow promotes it to 8-bit ``"P"`` mode on read; we mask each pixel
    with ``& 0x0F`` to keep only the low 4 bits — matching Porymap's
    ``flattenTo4bppImage`` helper (src/ui/imageproviders.cpp:174-181).

    Tiles are sliced from the image in row-major order: the top-left 8x8 block
    is tile 0, the next 8x8 along x is tile 1, and so on across rows.

    Args:
        tiles_png_path: Filesystem path to a tileset's ``tiles.png``.

    Returns:
        A ``uint8`` array of shape ``(num_tiles, TILE_SIZE, TILE_SIZE)`` where
        each entry is a palette index in ``0..15``.

    Raises:
        TilesPngFormatError: The file is missing, unreadable, has zero
            dimension, or its width/height is not a positive multiple of
            ``TILE_SIZE``.
    """
    try:
        img = Image.open(tiles_png_path)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        raise TilesPngFormatError(f"could not read tiles.png at {tiles_png_path}: {exc}") from exc

    indexed = img.convert("P")
    width, height = indexed.size
    if width == 0 or height == 0:
        raise TilesPngFormatError(f"tiles.png {tiles_png_path}: zero dimension {width}x{height}")
    if width % TILE_SIZE != 0 or height % TILE_SIZE != 0:
        raise TilesPngFormatError(
            f"tiles.png {tiles_png_path}: dimensions {width}x{height} are not "
            f"a multiple of {TILE_SIZE}"
        )

    pixels = np.asarray(indexed, dtype=np.uint8) & 0x0F
    rows = height // TILE_SIZE
    cols = width // TILE_SIZE
    # Reshape (H, W) -> (rows, TILE_SIZE, cols, TILE_SIZE) so each (row, col)
    # block is a contiguous 8x8 tile, then swap axes to bring (row, col)
    # next to each other and flatten to (num_tiles, 8, 8).
    return (
        pixels.reshape(rows, TILE_SIZE, cols, TILE_SIZE)
        .swapaxes(1, 2)
        .reshape(rows * cols, TILE_SIZE, TILE_SIZE)
        .copy()
    )


def decode_palette_bank(pal_paths: Sequence[Path]) -> np.ndarray:
    """Decode JASC ``.pal`` palettes into a ``[num_palettes, 16, 4]`` RGBA array.

    Two adjustments are applied vs the raw file content:

    1. **GBA 5-bit hardware quantization.** Each RGB component is masked with
       ``& 0xF8`` to drop the low 3 bits. Porymap's exported pixels reflect
       the same truncation; without this masking, the L3 fidelity test will
       diff on every map (ADR-0010 Risk 5).
    2. **Palette-index-0 transparency.** Index 0 of every palette is set to
       alpha 0; remaining indices are alpha 255. This is the standard GBA
       upper-layer transparency convention (Porymap applies it in
       src/ui/imageproviders.cpp:130-134). The per-metatile transparency
       *fill* colour (``transparency_color`` in ``porymap.project.cfg``) is
       NOT applied here — it belongs to the metatile composition pass.

    Args:
        pal_paths: Sequence of filesystem paths to JASC ``.pal`` files, in the
            order the renderer wants them indexed (typically primary palettes
            0..5 then secondary palettes 6..12, but this function is
            agnostic — the caller decides the ordering).

    Returns:
        A ``uint8`` array of shape ``(len(pal_paths), PALETTE_SIZE, 4)``.

    Raises:
        PaletteFormatError: Empty sequence, file unreadable, or any palette
            failed to parse as JASC-PAL.
    """
    if not pal_paths:
        raise PaletteFormatError("decode_palette_bank requires at least one palette path")

    palettes = np.zeros((len(pal_paths), PALETTE_SIZE, 4), dtype=np.uint8)
    for idx, path in enumerate(pal_paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PaletteFormatError(f"could not read palette at {path}: {exc}") from exc
        palettes[idx] = _parse_jasc(text, path)
    return palettes


def _parse_jasc(text: str, source: Path) -> np.ndarray:
    """Parse one JASC-PAL palette into a ``(16, 4)`` RGBA ``uint8`` array.

    Format (Porymap's ``parseJASC``, tolerant of CRLF or LF):

        Line 1: ``JASC-PAL``
        Line 2: ``0100``
        Line 3: declared colour count (must equal :data:`PALETTE_SIZE`)
        Lines 4..19: ``"R G B"`` decimal triples, each in ``[0, 255]``

    Applies GBA 5-bit quantization (``& 0xF8``) and sets alpha to 0 for
    index 0, 255 for indices 1..15.
    """
    lines = text.splitlines()
    if len(lines) < 3 + PALETTE_SIZE:
        raise PaletteFormatError(
            f"{source}: JASC-PAL needs at least {3 + PALETTE_SIZE} lines, got {len(lines)}"
        )
    if lines[0].strip() != "JASC-PAL":
        raise PaletteFormatError(f"{source}: first line must be 'JASC-PAL', got {lines[0]!r}")
    if lines[1].strip() != "0100":
        raise PaletteFormatError(f"{source}: second line must be '0100', got {lines[1]!r}")
    try:
        declared = int(lines[2].strip(), 10)
    except ValueError as exc:
        raise PaletteFormatError(
            f"{source}: third line must be the decimal colour count, got {lines[2]!r}"
        ) from exc
    if declared != PALETTE_SIZE:
        raise PaletteFormatError(
            f"{source}: declared colour count {declared} != expected {PALETTE_SIZE}"
        )

    out = np.zeros((PALETTE_SIZE, 4), dtype=np.uint8)
    for i in range(PALETTE_SIZE):
        line = lines[3 + i]
        parts = line.split()
        if len(parts) != 3:
            raise PaletteFormatError(
                f"{source} line {4 + i}: expected 'R G B' decimal triple, got {line!r}"
            )
        try:
            r, g, b = (int(part, 10) for part in parts)
        except ValueError as exc:
            raise PaletteFormatError(f"{source} line {4 + i}: non-decimal RGB in {line!r}") from exc
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise PaletteFormatError(
                f"{source} line {4 + i}: RGB component out of [0, 255]: {line!r}"
            )
        alpha = 0 if i == 0 else 255
        out[i] = (r, g, b, alpha)
    return out


def decode_metatile_bank(
    metatiles_bytes: bytes,
    attributes: Sequence[MetatileAttributes],
    tile_bank: np.ndarray,
    palette_bank: np.ndarray,
    *,
    layers: int,
    unused_tile_normal: int,
    unused_tile_covered: int,
    unused_tile_split: int,
    transparency_color: int | None,
) -> np.ndarray:
    """Compose every metatile into a ``[num_metatiles, 16, 16, 4]`` RGBA bank.

    Implements ADR-0010's "always 3 stacked layers" composition rule. Each
    metatile is rendered onto a 16x16 RGBA canvas pre-filled with the
    transparency colour, and three layers of four 8x8 tiles each are
    alpha-composited bottom-to-top.

    ``layers=3`` (triple-layer mode, ``enable_triple_layer_metatiles=1``):
        All three layers come from disk — file tiles 0-3 (bottom), 4-7
        (middle), 8-11 (top).

    ``layers=2`` (dual-layer mode, vanilla RSE / pokeemerald):
        Two layers come from disk; the third is filled by the project-config
        ``unused_tile_{normal,covered,split}`` tile ID (palette 0, no flips),
        selected by the metatile's ``LayerType`` attribute (ADR-0010
        composition table):

        =========================  ========  =========  ========
        ``LayerType``              bottom    middle     top
        =========================  ========  =========  ========
        ``Normal`` (0)             unused    file 0-3   file 4-7
        ``Covered`` (1)            file 0-3  file 4-7   unused
        ``Split`` (2)              file 0-3  unused     file 4-7
        =========================  ========  =========  ========

        Any other ``layer_type`` value falls back to ``Normal`` — Porymap's
        switch statement does the same (``src/ui/imageproviders.cpp``).

    Each on-disk 2-byte tile entry unpacks as: ``tile_id`` = bits 0-9,
    ``xflip`` = bit 10, ``yflip`` = bit 11, ``palette_num`` = bits 12-15.

    Args:
        metatiles_bytes: Raw bytes of ``metatiles.bin``.
        attributes: Decoded :class:`MetatileAttributes` for every metatile,
            in the same order. Length must match ``len(metatiles_bytes) /
            bytes_per_metatile``.
        tile_bank: ``uint8[num_tiles, 8, 8]`` from :func:`decode_tile_bank`
            (concatenation of primary + secondary banks is the caller's
            responsibility — typically primary tiles 0..511, secondary
            512..1023 for vanilla).
        palette_bank: ``uint8[num_palettes, 16, 4]`` from
            :func:`decode_palette_bank`, with GBA quantization and
            palette-0 alpha-0 already applied.
        layers: 2 (dual) or 3 (triple).
        unused_tile_normal: Tile ID for the bottom fill on ``Normal``
            metatiles (``ProjectConfig.unused_tile_normal``).
        unused_tile_covered: Tile ID for the top fill on ``Covered`` metatiles.
        unused_tile_split: Tile ID for the middle fill on ``Split`` metatiles.
        transparency_color: 24-bit RGB packed as ``0x00RRGGBB``, or ``None``.
            Each component is masked ``& 0xF8`` (GBA quantization). When
            ``None``, the bottom-layer fill falls back to colour 0 of
            palette 0 (which is the index Porymap takes when
            ``transparency_color`` is unset or invalid).

    Returns:
        A ``uint8`` array of shape ``(num_metatiles, 16, 16, 4)`` — RGBA
        pixels per metatile.

    Raises:
        MetatilesBinFormatError: ``layers`` not in {2, 3}, ``metatiles.bin``
            size not a positive multiple of ``8 * layers`` bytes, or
            attribute count does not match the metatile count.
        PaletteFormatError: ``palette_bank`` is empty.
    """
    if layers not in (2, 3):
        raise MetatilesBinFormatError(f"layers must be 2 (dual) or 3 (triple), got {layers}")
    if palette_bank.shape[0] == 0:
        raise PaletteFormatError("palette_bank is empty; need at least palette 0")

    tiles_per_metatile = 4 * layers
    bytes_per_metatile = 2 * tiles_per_metatile
    n_bytes = len(metatiles_bytes)
    if n_bytes == 0 or n_bytes % bytes_per_metatile != 0:
        raise MetatilesBinFormatError(
            f"metatiles.bin: size {n_bytes} bytes is not a positive multiple "
            f"of {bytes_per_metatile} ({layers}-layer mode)"
        )
    num_metatiles = n_bytes // bytes_per_metatile
    if len(attributes) != num_metatiles:
        raise MetatilesBinFormatError(
            f"metatiles.bin declares {num_metatiles} metatiles but "
            f"{len(attributes)} attributes were provided"
        )

    # Background fill: transparency_color or palette[0][0] RGB.
    if transparency_color is not None:
        r = (transparency_color >> 16) & 0xFF
        g = (transparency_color >> 8) & 0xFF
        b = transparency_color & 0xFF
        bg = np.array([r, g, b, 0xFF], dtype=np.uint8)
    else:
        p00 = palette_bank[0, 0]
        bg = np.array([p00[0], p00[1], p00[2], 0xFF], dtype=np.uint8)

    out = np.empty((num_metatiles, 16, 16, 4), dtype=np.uint8)
    out[...] = bg

    # Vectorized tile-entry unpacking. Little-endian uint16; bit-fields per
    # ADR-0010 §"Metatile composition".
    entries = np.frombuffer(metatiles_bytes, dtype="<u2").reshape(num_metatiles, tiles_per_metatile)
    tile_ids = (entries & 0x03FF).astype(np.uint16)
    xflips = ((entries >> 10) & 0x1).astype(bool)
    yflips = ((entries >> 11) & 0x1).astype(bool)
    palette_nums = ((entries >> 12) & 0x0F).astype(np.uint8)

    num_tiles = int(tile_bank.shape[0])
    num_palettes = int(palette_bank.shape[0])

    # The "unused" entry: tile_id only; palette 0, no flips (Porymap's bare
    # ``Tile(id)`` constructor defaults — see ``src/ui/imageproviders.cpp``).
    fill_normal = (unused_tile_normal, False, False, 0)
    fill_covered = (unused_tile_covered, False, False, 0)
    fill_split = (unused_tile_split, False, False, 0)

    for m in range(num_metatiles):
        layer_a = _entries_at(tile_ids, xflips, yflips, palette_nums, m, 0, 4)
        layer_b = _entries_at(tile_ids, xflips, yflips, palette_nums, m, 4, 8)
        if layers == 3:
            layer_c = _entries_at(tile_ids, xflips, yflips, palette_nums, m, 8, 12)
            stack = (layer_a, layer_b, layer_c)
        else:
            lt = attributes[m].layer_type
            if lt == 1:  # Covered
                stack = (layer_a, layer_b, (fill_covered,) * 4)
            elif lt == 2:  # Split
                stack = (layer_a, (fill_split,) * 4, layer_b)
            else:  # Normal (0) — also the fallback for unknown values.
                stack = ((fill_normal,) * 4, layer_a, layer_b)

        canvas = out[m]
        for layer in stack:
            for (ty, tx), (tid, xf, yf, pal) in zip(_QUAD_POSITIONS, layer, strict=True):
                if tid >= num_tiles or pal >= num_palettes:
                    continue
                tile = tile_bank[int(tid)]
                if xf:
                    tile = tile[:, ::-1]
                if yf:
                    tile = tile[::-1, :]
                colours = palette_bank[int(pal)][tile]
                mask = colours[..., 3] > 0
                region = canvas[ty : ty + TILE_SIZE, tx : tx + TILE_SIZE]
                region[mask] = colours[mask]

    return out


def _entries_at(
    tile_ids: np.ndarray,
    xflips: np.ndarray,
    yflips: np.ndarray,
    palette_nums: np.ndarray,
    m: int,
    start: int,
    stop: int,
) -> tuple[tuple[int, bool, bool, int], ...]:
    """Pluck a slice of tile entries for metatile ``m`` into Python tuples.

    Returning plain ints/bools keeps the composition loop's inner branch
    simple — numpy scalar arithmetic in a hot path is measurably slower
    than ``int(...)``-cast scalars.
    """
    return tuple(
        (
            int(tile_ids[m, i]),
            bool(xflips[m, i]),
            bool(yflips[m, i]),
            int(palette_nums[m, i]),
        )
        for i in range(start, stop)
    )
