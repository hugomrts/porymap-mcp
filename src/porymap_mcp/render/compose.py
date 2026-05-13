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

from porymap_mcp.errors import PaletteFormatError, TilesPngFormatError

#: Side length of one tile, in pixels (GBA hardware constant).
TILE_SIZE: Final = 8

#: Number of colours per palette (GBA 4-bpp hardware constant).
PALETTE_SIZE: Final = 16


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
        out[i] = (r & 0xF8, g & 0xF8, b & 0xF8, alpha)
    return out
