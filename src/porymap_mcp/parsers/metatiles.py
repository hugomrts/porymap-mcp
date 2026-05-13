"""Parser for ``data/tilesets/<kind>/<name>/metatiles.bin``.

A metatile is a 16x16-pixel block composed of either 8 (two-layer) or
12 (triple-layer) sub-tile uint16 words. Each sub-tile carries an 8x8
tile index plus palette/flip/layer bits. For v0.1.0 we expose only
``count_metatiles`` — the L3 renderer (Phase 4) will need full
sub-tile decoding; we ship the count-only helper here so
``list_metatiles`` can report accurate metatile counts (ADR-0005 §4
"file-size-derived" → upgraded here to "config-aware").

References:
  - Porymap source: ``src/core/metatile.h``.
  - Vanilla layout: ``include/global.fieldmap.h``.
  - Triple-layer (pokeemerald-expansion): controlled by
    ``enable_triple_layer_metatiles=1`` in ``porymap.project.cfg``.
"""

from __future__ import annotations

from typing import Final

from porymap_mcp.errors import FormatError

#: Bytes per metatile in the standard two-layer layout (8 sub-tiles * 2 bytes).
METATILE_BYTES_TWO_LAYER: Final = 16
#: Bytes per metatile in the triple-layer layout (12 sub-tiles * 2 bytes).
METATILE_BYTES_TRIPLE_LAYER: Final = 24


def bytes_per_metatile(*, triple_layer: bool) -> int:
    """Return the on-disk byte size of a single metatile."""
    return METATILE_BYTES_TRIPLE_LAYER if triple_layer else METATILE_BYTES_TWO_LAYER


def count_metatiles(data: bytes, *, triple_layer: bool) -> int:
    """Return the number of metatiles in ``data``.

    Raises :class:`FormatError` when the file size is not a clean
    multiple of the expected bytes-per-metatile — that signals a
    truncated or misconfigured file.
    """
    size = bytes_per_metatile(triple_layer=triple_layer)
    if len(data) % size != 0:
        raise FormatError(
            f"metatiles.bin: size {len(data)} bytes is not a multiple of "
            f"{size} (the per-metatile size for "
            f"{'triple-layer' if triple_layer else 'two-layer'} projects)."
        )
    return len(data) // size
