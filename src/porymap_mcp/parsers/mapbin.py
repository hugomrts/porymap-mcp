"""Parser/serializer for ``map.bin`` and ``border.bin`` layout files.

Format (per Porymap source: ``src/core/maplayout.cpp``, ``src/core/metatile.h``;
pokeemerald: ``include/global.fieldmap.h``):

Each tile is a little-endian ``uint16`` with the following bit-packing:

    bits 0..9   (mask 0x03FF) — metatile ID         (range 0..1023)
    bits 10..11 (mask 0x0C00) — collision           (range 0..3)
    bits 12..15 (mask 0xF000) — elevation           (range 0..15)

A layout file is exactly ``width * height * 2`` bytes; there is no header.
``border.bin`` uses the same encoding (typically 2x2 in Gen-3 vanilla, but
Porymap allows any user-configured border size).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from porymap_mcp.errors import MapBinFormatError

# --- Bit masks (canonical, do not change without an ADR) ---

_METATILE_ID_MASK: Final = 0x03FF
_COLLISION_MASK: Final = 0x0C00
_COLLISION_SHIFT: Final = 10
_ELEVATION_MASK: Final = 0xF000
_ELEVATION_SHIFT: Final = 12

MAX_METATILE_ID: Final = 0x03FF  # 1023
MAX_COLLISION: Final = 0x3  # 3
MAX_ELEVATION: Final = 0xF  # 15


@dataclass(frozen=True, slots=True)
class Tile:
    """A single tile entry on a map layout grid.

    Fields map 1:1 to the bit-packed uint16 on disk. Construction validates
    ranges; out-of-range values raise :class:`ValueError` (a programmer error,
    not a file-format error — file-loaded values are validated by
    :func:`decode_tile`).
    """

    metatile_id: int
    collision: int
    elevation: int

    def __post_init__(self) -> None:
        if not 0 <= self.metatile_id <= MAX_METATILE_ID:
            raise ValueError(
                f"metatile_id={self.metatile_id} out of range (0..{MAX_METATILE_ID})"
            )
        if not 0 <= self.collision <= MAX_COLLISION:
            raise ValueError(
                f"collision={self.collision} out of range (0..{MAX_COLLISION})"
            )
        if not 0 <= self.elevation <= MAX_ELEVATION:
            raise ValueError(
                f"elevation={self.elevation} out of range (0..{MAX_ELEVATION})"
            )


@dataclass(frozen=True, slots=True)
class MapBin:
    """A decoded ``map.bin`` / ``border.bin`` layout.

    ``tiles`` is a row-major 2-D list, ``tiles[y][x]``, of length ``height``
    with each row of length ``width``. Origin is top-left (matches Porymap).
    """

    width: int
    height: int
    tiles: tuple[tuple[Tile, ...], ...]

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"width and height must be positive (got {self.width}x{self.height})"
            )
        if len(self.tiles) != self.height:
            raise ValueError(
                f"tiles has {len(self.tiles)} rows, expected height={self.height}"
            )
        for y, row in enumerate(self.tiles):
            if len(row) != self.width:
                raise ValueError(
                    f"tiles[{y}] has {len(row)} cols, expected width={self.width}"
                )

    def get(self, x: int, y: int) -> Tile:
        """Return the tile at ``(x, y)``. Raises ``IndexError`` if out of bounds."""
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError(
                f"({x}, {y}) is out of bounds for a {self.width}x{self.height} layout"
            )
        return self.tiles[y][x]


# --- Pure encode/decode of a single tile (16 bits) ---


def decode_tile(packed: int) -> Tile:
    """Decode a single 16-bit packed tile value."""
    if not 0 <= packed <= 0xFFFF:
        raise ValueError(f"packed tile must fit in uint16 (got 0x{packed:X})")
    return Tile(
        metatile_id=packed & _METATILE_ID_MASK,
        collision=(packed & _COLLISION_MASK) >> _COLLISION_SHIFT,
        elevation=(packed & _ELEVATION_MASK) >> _ELEVATION_SHIFT,
    )


def encode_tile(tile: Tile) -> int:
    """Encode a :class:`Tile` to its 16-bit packed value."""
    return (
        (tile.metatile_id & _METATILE_ID_MASK)
        | ((tile.collision << _COLLISION_SHIFT) & _COLLISION_MASK)
        | ((tile.elevation << _ELEVATION_SHIFT) & _ELEVATION_MASK)
    )


# --- File-level read/write ---


def read(data: bytes, width: int, height: int) -> MapBin:
    """Parse a layout from raw bytes given its dimensions.

    Dimensions come from the project's ``layouts.json``; they cannot be
    derived from the file itself (no header).

    Raises:
        MapBinFormatError: if ``len(data)`` does not match ``width * height * 2``.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive (got {width}x{height})")

    expected_size = width * height * 2
    if len(data) != expected_size:
        raise MapBinFormatError(
            f"map.bin size mismatch: expected {expected_size} bytes "
            f"({width}x{height} tiles * 2 bytes/tile), got {len(data)} bytes."
        )

    rows: list[tuple[Tile, ...]] = []
    for y in range(height):
        row: list[Tile] = []
        for x in range(width):
            offset = (y * width + x) * 2
            packed = int.from_bytes(data[offset : offset + 2], "little")
            row.append(decode_tile(packed))
        rows.append(tuple(row))

    return MapBin(width=width, height=height, tiles=tuple(rows))


def write(layout: MapBin) -> bytes:
    """Serialize a :class:`MapBin` back to its on-disk byte representation."""
    out = bytearray(layout.width * layout.height * 2)
    for y in range(layout.height):
        for x in range(layout.width):
            offset = (y * layout.width + x) * 2
            packed = encode_tile(layout.tiles[y][x])
            out[offset : offset + 2] = packed.to_bytes(2, "little")
    return bytes(out)
