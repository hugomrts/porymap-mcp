"""Tests for ``porymap_mcp.render.layout``.

Pure-numpy primitive — no on-disk fixtures. Each test builds a tiny metatile
bank with distinct-colour cells, then verifies the assembled image's pixels
at known offsets. Region tests check half-open ``[x1, x2) x [y1, y2)``
slicing and the clipping helper.
"""

from __future__ import annotations

import numpy as np
import pytest

from porymap_mcp.errors import LayoutAssemblyError
from porymap_mcp.parsers.mapbin import MapBin, Tile
from porymap_mcp.render.layout import (
    METATILE_SIZE,
    assemble,
    assemble_region,
    clip_region,
    mapbin_to_metatile_grid,
    tile_border_around,
)


def _colour_bank(num: int) -> np.ndarray:
    """``num`` metatiles, each a solid RGBA fill. Metatile ``i`` has colour
    ``(i*10, i*20, i*30, 255)`` — distinct, easy to read back at any pixel."""
    bank = np.zeros((num, METATILE_SIZE, METATILE_SIZE, 4), dtype=np.uint8)
    for i in range(num):
        bank[i, :, :] = (i * 10, i * 20, i * 30, 255)
    return bank


def _expected_pixel(metatile_id: int) -> tuple[int, int, int, int]:
    return (metatile_id * 10, metatile_id * 20, metatile_id * 30, 255)


# --- assemble ---------------------------------------------------------------


class TestAssemble:
    def test_single_metatile_grid(self) -> None:
        bank = _colour_bank(3)
        grid = np.array([[1]], dtype=np.uint16)
        out = assemble(bank, grid)
        assert out.shape == (16, 16, 4)
        assert out.dtype == np.uint8
        assert tuple(out[0, 0]) == _expected_pixel(1)
        assert tuple(out[15, 15]) == _expected_pixel(1)

    def test_row_major_layout_origin_top_left(self) -> None:
        # 2x3 grid (H=2, W=3); origin top-left matches Porymap.
        bank = _colour_bank(4)
        grid = np.array([[0, 1, 2], [2, 1, 0]], dtype=np.uint16)
        out = assemble(bank, grid)
        # (rows * 16, cols * 16, 4) — H=2 → 32 px tall, W=3 → 48 px wide.
        assert out.shape == (32, 48, 4)
        # Top row.
        assert tuple(out[0, 0]) == _expected_pixel(0)
        assert tuple(out[0, 16]) == _expected_pixel(1)
        assert tuple(out[0, 32]) == _expected_pixel(2)
        # Bottom row.
        assert tuple(out[16, 0]) == _expected_pixel(2)
        assert tuple(out[16, 16]) == _expected_pixel(1)
        assert tuple(out[16, 32]) == _expected_pixel(0)

    def test_metatile_repetition_handled(self) -> None:
        # Same ID at multiple cells must produce identical 16x16 blocks.
        bank = _colour_bank(2)
        grid = np.array([[1, 1], [1, 1]], dtype=np.uint16)
        out = assemble(bank, grid)
        expected = np.tile(np.array(_expected_pixel(1), dtype=np.uint8), (32, 32, 1))
        assert np.array_equal(out, expected)

    def test_full_metatile_pasted_at_correct_pixel_offset(self) -> None:
        # Use an asymmetric metatile (different top vs bottom half) to verify
        # that within-tile pixel order is preserved, not flipped.
        bank = np.zeros((1, METATILE_SIZE, METATILE_SIZE, 4), dtype=np.uint8)
        bank[0, 0:8, :] = (100, 0, 0, 255)
        bank[0, 8:16, :] = (0, 100, 0, 255)
        grid = np.array([[0, 0]], dtype=np.uint16)
        out = assemble(bank, grid)
        # Top half of both pasted metatiles = red.
        assert tuple(out[0, 0]) == (100, 0, 0, 255)
        assert tuple(out[0, 16]) == (100, 0, 0, 255)
        # Bottom half = green.
        assert tuple(out[8, 0]) == (0, 100, 0, 255)
        assert tuple(out[8, 16]) == (0, 100, 0, 255)

    def test_output_is_contiguous(self) -> None:
        bank = _colour_bank(2)
        grid = np.array([[0, 1], [1, 0]], dtype=np.uint16)
        out = assemble(bank, grid)
        # Downstream Pillow encoders want a C-contiguous buffer.
        assert out.flags["C_CONTIGUOUS"]

    def test_accepts_other_integer_grid_dtypes(self) -> None:
        # Real callers may hand in int32 (from raw mapbin decode) or int64
        # (default numpy literal); both should work.
        bank = _colour_bank(2)
        for dtype in (np.int32, np.int64, np.uint8, np.uint16):
            grid = np.array([[0, 1]], dtype=dtype)
            out = assemble(bank, grid)
            assert out.shape == (16, 32, 4)


# --- assemble validation ---------------------------------------------------


class TestAssembleValidation:
    def test_rejects_out_of_range_metatile_id(self) -> None:
        bank = _colour_bank(2)
        grid = np.array([[0, 5]], dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match=r"outside \[0, 2\)"):
            assemble(bank, grid)

    def test_rejects_negative_metatile_id(self) -> None:
        bank = _colour_bank(2)
        grid = np.array([[0, -1]], dtype=np.int32)
        with pytest.raises(LayoutAssemblyError, match="min=-1"):
            assemble(bank, grid)

    def test_rejects_non_integer_grid_dtype(self) -> None:
        bank = _colour_bank(2)
        grid = np.array([[0.0, 1.0]], dtype=np.float32)
        with pytest.raises(LayoutAssemblyError, match="dtype must be integer"):
            assemble(bank, grid)

    def test_rejects_1d_grid(self) -> None:
        bank = _colour_bank(2)
        grid = np.array([0, 1], dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match="must be 2D"):
            assemble(bank, grid)

    def test_rejects_empty_grid(self) -> None:
        bank = _colour_bank(2)
        grid = np.zeros((0, 0), dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match="zero dimension"):
            assemble(bank, grid)

    def test_rejects_bank_with_wrong_shape(self) -> None:
        # Bank rows aren't 16-px tall.
        bank = np.zeros((2, 8, 16, 4), dtype=np.uint8)
        grid = np.array([[0]], dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match="is not "):
            assemble(bank, grid)

    def test_rejects_bank_with_wrong_dtype(self) -> None:
        bank = np.zeros((2, 16, 16, 4), dtype=np.float32)
        grid = np.array([[0]], dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match="dtype must be uint8"):
            assemble(bank, grid)

    def test_rejects_empty_bank(self) -> None:
        bank = np.zeros((0, 16, 16, 4), dtype=np.uint8)
        grid = np.array([[0]], dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match="is empty"):
            assemble(bank, grid)


# --- assemble_region -------------------------------------------------------


class TestAssembleRegion:
    def test_extracts_subgrid(self) -> None:
        bank = _colour_bank(5)
        # 3x3 grid, IDs 0..8 row-major.
        grid = np.array([[0, 1, 2], [3, 4, 0], [1, 2, 3]], dtype=np.uint16)
        # Pull centre-right 2x2 block — grid[0:2, 1:3] = [[1, 2], [4, 0]].
        out = assemble_region(bank, grid, x1=1, y1=0, x2=3, y2=2)
        assert out.shape == (32, 32, 4)
        assert tuple(out[0, 0]) == _expected_pixel(1)
        assert tuple(out[0, 16]) == _expected_pixel(2)
        assert tuple(out[16, 0]) == _expected_pixel(4)
        assert tuple(out[16, 16]) == _expected_pixel(0)

    def test_full_region_equals_full_assemble(self) -> None:
        bank = _colour_bank(3)
        grid = np.array([[0, 1, 2], [2, 1, 0]], dtype=np.uint16)
        full = assemble(bank, grid)
        same = assemble_region(bank, grid, x1=0, y1=0, x2=3, y2=2)
        assert np.array_equal(full, same)

    def test_one_cell_region(self) -> None:
        bank = _colour_bank(3)
        grid = np.array([[0, 1], [2, 0]], dtype=np.uint16)
        out = assemble_region(bank, grid, x1=1, y1=0, x2=2, y2=1)
        assert out.shape == (16, 16, 4)
        assert tuple(out[0, 0]) == _expected_pixel(1)

    @pytest.mark.parametrize(
        ("x1", "y1", "x2", "y2"),
        [
            (1, 0, 1, 1),  # zero-width (x1 == x2)
            (0, 2, 2, 2),  # zero-height (y1 == y2)
            (2, 0, 1, 1),  # x1 > x2
            (-1, 0, 1, 1),  # negative x1
            (0, 0, 5, 1),  # x2 beyond width
            (0, 0, 2, 5),  # y2 beyond height
        ],
    )
    def test_rejects_invalid_bounds(self, x1: int, y1: int, x2: int, y2: int) -> None:
        bank = _colour_bank(3)
        grid = np.array([[0, 1], [1, 2]], dtype=np.uint16)
        with pytest.raises(LayoutAssemblyError, match="invalid for"):
            assemble_region(bank, grid, x1=x1, y1=y1, x2=x2, y2=y2)


# --- clip_region -----------------------------------------------------------


class TestClipRegion:
    def test_in_bounds_unchanged(self) -> None:
        assert clip_region((10, 10), 1, 2, 5, 6) == (1, 2, 5, 6)

    def test_clips_right_and_bottom_overrun(self) -> None:
        assert clip_region((4, 5), 2, 3, 99, 99) == (2, 3, 5, 4)

    def test_clips_left_and_top_underflow(self) -> None:
        assert clip_region((5, 5), -3, -7, 2, 4) == (0, 0, 2, 4)

    def test_clips_to_full_grid_when_region_engulfs_it(self) -> None:
        assert clip_region((3, 4), -10, -10, 20, 20) == (0, 0, 4, 3)

    def test_rejects_fully_outside_left(self) -> None:
        with pytest.raises(LayoutAssemblyError, match="clipped to empty"):
            clip_region((5, 5), -10, 0, -1, 5)

    def test_rejects_fully_outside_bottom(self) -> None:
        with pytest.raises(LayoutAssemblyError, match="clipped to empty"):
            clip_region((5, 5), 0, 99, 5, 200)

    def test_rejects_degenerate_input(self) -> None:
        with pytest.raises(LayoutAssemblyError, match="clipped to empty"):
            clip_region((5, 5), 2, 2, 2, 4)


# --- mapbin_to_metatile_grid -----------------------------------------------


class TestMapbinToMetatileGrid:
    def test_extracts_metatile_ids_dropping_collision_and_elevation(self) -> None:
        # MapBin tile with non-zero collision + elevation; only metatile_id
        # should appear in the grid.
        rows = (
            (
                Tile(metatile_id=5, collision=2, elevation=3),
                Tile(metatile_id=10, collision=0, elevation=15),
            ),
            (
                Tile(metatile_id=0, collision=1, elevation=0),
                Tile(metatile_id=1023, collision=3, elevation=15),  # max IDs
            ),
        )
        mb = MapBin(width=2, height=2, tiles=rows)
        grid = mapbin_to_metatile_grid(mb)
        assert grid.shape == (2, 2)
        assert grid.dtype == np.uint16
        assert grid[0, 0] == 5
        assert grid[0, 1] == 10
        assert grid[1, 0] == 0
        assert grid[1, 1] == 1023

    def test_round_trip_assemble(self) -> None:
        # End-to-end: MapBin → grid → assemble produces the expected colour blocks.
        rows = (
            (
                Tile(metatile_id=0, collision=0, elevation=0),
                Tile(metatile_id=1, collision=0, elevation=0),
            ),
            (
                Tile(metatile_id=2, collision=0, elevation=0),
                Tile(metatile_id=0, collision=0, elevation=0),
            ),
        )
        mb = MapBin(width=2, height=2, tiles=rows)
        bank = _colour_bank(3)
        out = assemble(bank, mapbin_to_metatile_grid(mb))
        assert out.shape == (32, 32, 4)
        assert tuple(out[0, 0]) == _expected_pixel(0)
        assert tuple(out[0, 16]) == _expected_pixel(1)
        assert tuple(out[16, 0]) == _expected_pixel(2)
        assert tuple(out[16, 16]) == _expected_pixel(0)


# --- tile_border_around --------------------------------------------------


def _solid_rgba(h: int, w: int, rgba: tuple[int, int, int, int]) -> np.ndarray:
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:] = rgba
    return out


class TestTileBorderAround:
    def test_solid_border_wraps_solid_map(self) -> None:
        # Map: 2x2 metatiles (32x32 px) filled red.
        # Border: 2x2 metatiles (32x32 px) filled blue.
        # Frame: 3 metatiles per side.
        map_rgba = _solid_rgba(32, 32, (255, 0, 0, 255))
        border_rgba = _solid_rgba(32, 32, (0, 0, 255, 255))
        out = tile_border_around(
            map_rgba,
            border_rgba,
            frame_width_metatiles=3,
            frame_height_metatiles=3,
        )
        # 2 + 2*3 = 8 metatiles per side => 128 px.
        assert out.shape == (128, 128, 4)
        # Top-left corner is border (blue).
        assert tuple(out[0, 0]) == (0, 0, 255, 255)
        # Centre is the map (red).
        assert tuple(out[64, 64]) == (255, 0, 0, 255)
        # Right edge is border again.
        assert tuple(out[64, 127]) == (0, 0, 255, 255)
        # Map area unchanged.
        assert np.all(out[48:80, 48:80] == map_rgba)

    def test_border_tiles_by_modulo(self) -> None:
        # Border with a recognisable checker pattern: top-left and bottom-right
        # of the border are distinct colours; the tiling should repeat them.
        border_rgba = _solid_rgba(32, 32, (10, 20, 30, 255))
        # Override the 16x16 top-left quad with a different colour so we can
        # spot the repeat.
        border_rgba[0:16, 0:16] = (100, 200, 50, 255)
        map_rgba = _solid_rgba(16, 16, (0, 0, 0, 255))
        out = tile_border_around(
            map_rgba,
            border_rgba,
            frame_width_metatiles=2,
            frame_height_metatiles=2,
        )
        # Frame is 2 metatiles = 32 px per side. The border (32x32) tiles
        # twice across each frame side. The top-left 16x16 of the output
        # equals the border's top-left 16x16 (the recognisable green block).
        assert tuple(out[0, 0]) == (100, 200, 50, 255)
        # 32 px to the right, the border has tiled once → position (0, 32)
        # in output equals border[0, 0] → green again.
        assert tuple(out[0, 32]) == (100, 200, 50, 255)
        # Position (0, 16) in output is border[0, 16] → grey (10, 20, 30).
        assert tuple(out[0, 16]) == (10, 20, 30, 255)

    def test_zero_frame_returns_copy(self) -> None:
        map_rgba = _solid_rgba(16, 16, (5, 5, 5, 255))
        border_rgba = _solid_rgba(32, 32, (9, 9, 9, 255))
        out = tile_border_around(
            map_rgba,
            border_rgba,
            frame_width_metatiles=0,
            frame_height_metatiles=0,
        )
        assert out.shape == map_rgba.shape
        assert np.array_equal(out, map_rgba)
        # Distinct buffer — mutating the output must not change the input.
        out[0, 0] = (1, 2, 3, 4)
        assert tuple(map_rgba[0, 0]) == (5, 5, 5, 255)

    def test_asymmetric_frame(self) -> None:
        map_rgba = _solid_rgba(16, 16, (255, 255, 255, 255))
        border_rgba = _solid_rgba(16, 16, (0, 0, 0, 255))
        out = tile_border_around(
            map_rgba,
            border_rgba,
            frame_width_metatiles=4,
            frame_height_metatiles=1,
        )
        # Height: 1 + 1 + 1 = 3 metatiles = 48 px. Width: 4 + 1 + 4 = 9 mt = 144 px.
        assert out.shape == (48, 144, 4)
        # Map centred horizontally: starts at column 64 (4 * 16).
        assert np.all(out[16:32, 64:80] == map_rgba)

    def test_rejects_non_rgba_map(self) -> None:
        bad = np.zeros((16, 16, 3), dtype=np.uint8)
        good = _solid_rgba(16, 16, (0, 0, 0, 255))
        with pytest.raises(LayoutAssemblyError, match="map_rgba shape"):
            tile_border_around(bad, good, frame_width_metatiles=1, frame_height_metatiles=1)

    def test_rejects_non_metatile_dimensions(self) -> None:
        # 15 px is not a multiple of METATILE_SIZE.
        bad = np.zeros((15, 16, 4), dtype=np.uint8)
        good = _solid_rgba(16, 16, (0, 0, 0, 255))
        with pytest.raises(LayoutAssemblyError, match="multiple of 16"):
            tile_border_around(bad, good, frame_width_metatiles=1, frame_height_metatiles=1)

    def test_rejects_negative_frame(self) -> None:
        map_rgba = _solid_rgba(16, 16, (0, 0, 0, 255))
        border_rgba = _solid_rgba(16, 16, (0, 0, 0, 255))
        with pytest.raises(LayoutAssemblyError, match="frame dimensions must be non-negative"):
            tile_border_around(
                map_rgba, border_rgba, frame_width_metatiles=-1, frame_height_metatiles=0
            )
