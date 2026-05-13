"""Tests for ``porymap_mcp.parsers.mapbin``.

The 3x2 reference fixture is duplicated here as a Python constant for
hermetic, transparent assertions — the bytes are also documented in
``tests/fixtures/README.md`` and must stay in sync.
"""

from __future__ import annotations

import pytest

from porymap_mcp.errors import MapBinFormatError
from porymap_mcp.parsers import mapbin
from porymap_mcp.parsers.mapbin import (
    MAX_COLLISION,
    MAX_ELEVATION,
    MAX_METATILE_ID,
    MapBin,
    Tile,
    decode_tile,
    encode_tile,
)

# --- Reference 3x2 fixture (matches tests/fixtures/README.md) ---

REF_3X2_BYTES = bytes.fromhex("01 00 02 04 03 20 04 08 FF FF 00 00".replace(" ", ""))
REF_3X2_TILES = (
    (Tile(0x001, 0, 0), Tile(0x002, 1, 0), Tile(0x003, 0, 2)),
    (Tile(0x004, 2, 0), Tile(0x3FF, 3, 0xF), Tile(0x000, 0, 0)),
)


# --- decode_tile / encode_tile ---


class TestDecodeTile:
    def test_zero(self) -> None:
        assert decode_tile(0x0000) == Tile(0, 0, 0)

    def test_metatile_id_only(self) -> None:
        assert decode_tile(0x0042) == Tile(0x042, 0, 0)

    def test_max_metatile_id(self) -> None:
        assert decode_tile(0x03FF) == Tile(MAX_METATILE_ID, 0, 0)

    def test_collision_field_isolation(self) -> None:
        # Collision 1 alone is bit 10 → 0x0400.
        assert decode_tile(0x0400) == Tile(0, 1, 0)
        # Collision 3 → bits 10..11 set → 0x0C00.
        assert decode_tile(0x0C00) == Tile(0, MAX_COLLISION, 0)

    def test_elevation_field_isolation(self) -> None:
        assert decode_tile(0x1000) == Tile(0, 0, 1)
        assert decode_tile(0xF000) == Tile(0, 0, MAX_ELEVATION)

    def test_all_fields_combined(self) -> None:
        # 0xFFFF == metatile_id 0x3FF, collision 3, elevation 0xF
        assert decode_tile(0xFFFF) == Tile(MAX_METATILE_ID, MAX_COLLISION, MAX_ELEVATION)

    def test_rejects_out_of_uint16(self) -> None:
        with pytest.raises(ValueError, match="uint16"):
            decode_tile(0x10000)
        with pytest.raises(ValueError, match="uint16"):
            decode_tile(-1)


class TestEncodeTile:
    def test_round_trip_all_combinations_compact(self) -> None:
        # Spot-check a few representative tiles round-trip cleanly.
        cases = [
            Tile(0, 0, 0),
            Tile(0x001, 0, 0),
            Tile(0x3FF, 3, 0xF),
            Tile(0x100, 2, 8),
        ]
        for tile in cases:
            assert decode_tile(encode_tile(tile)) == tile

    def test_max_packing_matches_0xFFFF(self) -> None:
        assert encode_tile(Tile(MAX_METATILE_ID, MAX_COLLISION, MAX_ELEVATION)) == 0xFFFF

    def test_only_metatile_id(self) -> None:
        assert encode_tile(Tile(0x123, 0, 0)) == 0x0123


# --- Tile validation ---


class TestTileValidation:
    def test_rejects_negative_metatile_id(self) -> None:
        with pytest.raises(ValueError, match="metatile_id"):
            Tile(-1, 0, 0)

    def test_rejects_overflowing_metatile_id(self) -> None:
        with pytest.raises(ValueError, match="metatile_id"):
            Tile(MAX_METATILE_ID + 1, 0, 0)

    def test_rejects_overflowing_collision(self) -> None:
        with pytest.raises(ValueError, match="collision"):
            Tile(0, MAX_COLLISION + 1, 0)

    def test_rejects_overflowing_elevation(self) -> None:
        with pytest.raises(ValueError, match="elevation"):
            Tile(0, 0, MAX_ELEVATION + 1)


# --- read() ---


class TestRead:
    def test_reads_reference_3x2(self) -> None:
        layout = mapbin.read(REF_3X2_BYTES, width=3, height=2)
        assert layout.width == 3
        assert layout.height == 2
        assert layout.tiles == REF_3X2_TILES

    def test_get_returns_correct_tile(self) -> None:
        layout = mapbin.read(REF_3X2_BYTES, width=3, height=2)
        assert layout.get(2, 1) == Tile(0x000, 0, 0)
        assert layout.get(1, 1) == Tile(0x3FF, 3, 0xF)

    def test_get_rejects_out_of_bounds(self) -> None:
        layout = mapbin.read(REF_3X2_BYTES, width=3, height=2)
        with pytest.raises(IndexError):
            layout.get(3, 0)
        with pytest.raises(IndexError):
            layout.get(0, 2)
        with pytest.raises(IndexError):
            layout.get(-1, 0)

    def test_rejects_short_buffer(self) -> None:
        with pytest.raises(MapBinFormatError, match="size mismatch"):
            mapbin.read(REF_3X2_BYTES[:-1], width=3, height=2)

    def test_rejects_long_buffer(self) -> None:
        with pytest.raises(MapBinFormatError, match="size mismatch"):
            mapbin.read(REF_3X2_BYTES + b"\x00", width=3, height=2)

    def test_rejects_zero_dimensions(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            mapbin.read(b"", width=0, height=1)
        with pytest.raises(ValueError, match="positive"):
            mapbin.read(b"", width=1, height=0)

    def test_minimal_1x1(self) -> None:
        layout = mapbin.read(b"\x42\x10", width=1, height=1)
        # 0x1042 → metatile_id 0x042, collision 1, elevation 1
        assert layout.get(0, 0) == Tile(0x042, 1, 1)


# --- write() ---


class TestWrite:
    def test_writes_reference_3x2(self) -> None:
        layout = MapBin(width=3, height=2, tiles=REF_3X2_TILES)
        assert mapbin.write(layout) == REF_3X2_BYTES

    def test_round_trip_reference(self) -> None:
        layout = mapbin.read(REF_3X2_BYTES, width=3, height=2)
        assert mapbin.write(layout) == REF_3X2_BYTES

    def test_round_trip_arbitrary(self) -> None:
        # Two rows, three cols, mixed values.
        tiles = (
            (Tile(0x100, 0, 0), Tile(0x200, 1, 1), Tile(0x300, 2, 2)),
            (Tile(0x0FF, 3, 3), Tile(0x1FF, 0, 4), Tile(0x2FF, 1, 5)),
        )
        layout = MapBin(width=3, height=2, tiles=tiles)
        round_tripped = mapbin.read(mapbin.write(layout), width=3, height=2)
        assert round_tripped == layout


# --- MapBin construction ---


class TestMapBinConstruction:
    def test_rejects_row_count_mismatch(self) -> None:
        with pytest.raises(ValueError, match="rows"):
            MapBin(width=1, height=2, tiles=((Tile(0, 0, 0),),))

    def test_rejects_column_count_mismatch(self) -> None:
        with pytest.raises(ValueError, match="cols"):
            MapBin(
                width=2,
                height=1,
                tiles=((Tile(0, 0, 0),),),  # only 1 col where 2 expected
            )

    def test_rejects_non_positive_dimensions(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            MapBin(width=0, height=1, tiles=())
        with pytest.raises(ValueError, match="positive"):
            MapBin(width=1, height=-1, tiles=())
