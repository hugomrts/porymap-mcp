"""Tests for ``porymap_mcp.render.compose``.

Synthetic fixtures only — every PNG and ``.pal`` is built in-test from a
documented byte/index layout so an unfamiliar reader can verify the parser's
behaviour without checking out binary assets.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from porymap_mcp.errors import PaletteFormatError, TilesPngFormatError
from porymap_mcp.render.compose import (
    PALETTE_SIZE,
    TILE_SIZE,
    decode_palette_bank,
    decode_tile_bank,
)

# --- Synthetic fixture helpers ---------------------------------------------


def _write_indexed_png(path: Path, indices: np.ndarray) -> None:
    """Write a (H, W) uint8 palette-index array as an indexed PNG.

    Uses a trivial identity palette (entry i = grayscale i) since the
    decoder discards palette bytes from the PNG itself — only the per-pixel
    indices matter for ``decode_tile_bank``.
    """
    assert indices.dtype == np.uint8
    assert indices.ndim == 2
    img = Image.fromarray(indices, mode="P")
    # 256-entry grayscale palette (irrelevant to decode_tile_bank; required
    # by PIL for "P" mode to round-trip cleanly).
    img.putpalette([v for i in range(256) for v in (i, i, i)])
    img.save(path, format="PNG")


def _make_jasc(colours: list[tuple[int, int, int]], *, declared: int | None = None) -> str:
    """Build a JASC-PAL text block from 16 RGB triples."""
    body = "\n".join(f"{r} {g} {b}" for r, g, b in colours)
    count = PALETTE_SIZE if declared is None else declared
    return f"JASC-PAL\n0100\n{count}\n{body}\n"


def _identity_palette() -> list[tuple[int, int, int]]:
    """16 distinct RGB triples with values that survive ``& 0xF8`` cleanly
    AND values that don't, so quantization can be verified per entry.
    """
    # Indices 0..7: already 5-bit-aligned (low 3 bits zero).
    # Indices 8..15: low 3 bits set, must be truncated.
    aligned = [(i * 16, i * 16, i * 16) for i in range(8)]
    misaligned = [(i * 16 + 7, i * 16 + 7, i * 16 + 7) for i in range(8, 16)]
    return aligned + misaligned


# --- decode_tile_bank -------------------------------------------------------


class TestDecodeTileBank:
    def test_two_tiles_8x16(self, tmp_path: Path) -> None:
        # 8 px tall, 16 px wide = 2 tiles side by side. Tile 0 is all zeros;
        # tile 1 is a known pattern (row r = palette index r for r in 0..7).
        indices = np.zeros((8, 16), dtype=np.uint8)
        for r in range(8):
            indices[r, 8:16] = r
        png = tmp_path / "tiles.png"
        _write_indexed_png(png, indices)

        bank = decode_tile_bank(png)
        assert bank.shape == (2, TILE_SIZE, TILE_SIZE)
        assert bank.dtype == np.uint8
        assert np.array_equal(bank[0], np.zeros((8, 8), dtype=np.uint8))
        expected_tile_1 = np.array([[r] * 8 for r in range(8)], dtype=np.uint8)
        assert np.array_equal(bank[1], expected_tile_1)

    def test_row_major_tile_order(self, tmp_path: Path) -> None:
        # 16x16 grid -> 4 tiles in (col, row) order: 0=top-left, 1=top-right,
        # 2=bottom-left, 3=bottom-right. The decoder must produce that order.
        indices = np.zeros((16, 16), dtype=np.uint8)
        indices[0:8, 0:8] = 1  # top-left
        indices[0:8, 8:16] = 2  # top-right
        indices[8:16, 0:8] = 3  # bottom-left
        indices[8:16, 8:16] = 4  # bottom-right
        png = tmp_path / "tiles.png"
        _write_indexed_png(png, indices)

        bank = decode_tile_bank(png)
        assert bank.shape == (4, TILE_SIZE, TILE_SIZE)
        assert int(bank[0, 0, 0]) == 1
        assert int(bank[1, 0, 0]) == 2
        assert int(bank[2, 0, 0]) == 3
        assert int(bank[3, 0, 0]) == 4

    def test_masks_high_nibble(self, tmp_path: Path) -> None:
        # A single 8x8 tile filled with index 0x5F. Decoder must keep only the
        # low 4 bits (0xF) — Porymap's flattenTo4bppImage convention.
        indices = np.full((8, 8), 0x5F, dtype=np.uint8)
        png = tmp_path / "tiles.png"
        _write_indexed_png(png, indices)

        bank = decode_tile_bank(png)
        assert np.all(bank == 0x0F)

    def test_rejects_width_not_multiple_of_8(self, tmp_path: Path) -> None:
        indices = np.zeros((8, 9), dtype=np.uint8)
        png = tmp_path / "tiles.png"
        _write_indexed_png(png, indices)
        with pytest.raises(TilesPngFormatError, match="multiple of 8"):
            decode_tile_bank(png)

    def test_rejects_height_not_multiple_of_8(self, tmp_path: Path) -> None:
        indices = np.zeros((9, 8), dtype=np.uint8)
        png = tmp_path / "tiles.png"
        _write_indexed_png(png, indices)
        with pytest.raises(TilesPngFormatError, match="multiple of 8"):
            decode_tile_bank(png)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TilesPngFormatError, match=r"could not read tiles\.png"):
            decode_tile_bank(tmp_path / "nope.png")

    def test_non_png_file_raises(self, tmp_path: Path) -> None:
        garbage = tmp_path / "garbage.png"
        garbage.write_bytes(b"this is not a PNG")
        with pytest.raises(TilesPngFormatError, match=r"could not read tiles\.png"):
            decode_tile_bank(garbage)


# --- decode_palette_bank ----------------------------------------------------


class TestDecodePaletteBank:
    def test_one_palette_shape_and_dtype(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        pal.write_text(_make_jasc(_identity_palette()), encoding="utf-8")

        bank = decode_palette_bank([pal])
        assert bank.shape == (1, PALETTE_SIZE, 4)
        assert bank.dtype == np.uint8

    def test_gba_5bit_quantization_truncates_low_bits(self, tmp_path: Path) -> None:
        # All channels = 0xFF (max) -> 0xF8 after & 0xF8.
        pal = tmp_path / "00.pal"
        pal.write_text(_make_jasc([(255, 255, 255)] * PALETTE_SIZE), encoding="utf-8")

        bank = decode_palette_bank([pal])
        # Index 0 is transparent (alpha 0); RGB still quantised.
        assert tuple(bank[0, 0]) == (0xF8, 0xF8, 0xF8, 0)
        # Indices 1..15 are opaque, RGB quantised.
        for i in range(1, PALETTE_SIZE):
            assert tuple(bank[0, i]) == (0xF8, 0xF8, 0xF8, 255)

    def test_quantization_misaligned_values(self, tmp_path: Path) -> None:
        # 7 -> 0 (low 3 bits zeroed), 15 -> 8, 16 -> 16, 23 -> 16, 24 -> 24, 255 -> 248.
        cases = [(7, 0), (15, 8), (16, 16), (23, 16), (24, 24), (255, 248)]
        colours = [(r, g, b) for r, g, b in [(c, c, c) for c, _ in cases]]
        # Pad up to PALETTE_SIZE
        colours.extend([(0, 0, 0)] * (PALETTE_SIZE - len(colours)))
        pal = tmp_path / "00.pal"
        pal.write_text(_make_jasc(colours), encoding="utf-8")

        bank = decode_palette_bank([pal])
        for i, (_, expected) in enumerate(cases):
            r, g, b, _a = bank[0, i]
            assert int(r) == expected, f"index {i} red: got {int(r)}, want {expected}"
            assert int(g) == expected
            assert int(b) == expected

    def test_palette_index_0_is_transparent_other_indices_opaque(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        pal.write_text(_make_jasc(_identity_palette()), encoding="utf-8")
        bank = decode_palette_bank([pal])
        assert int(bank[0, 0, 3]) == 0  # alpha
        for i in range(1, PALETTE_SIZE):
            assert int(bank[0, i, 3]) == 255

    def test_multiple_palettes_stacked_in_order(self, tmp_path: Path) -> None:
        first_colours = [(8, 0, 0)] * PALETTE_SIZE
        second_colours = [(0, 8, 0)] * PALETTE_SIZE
        third_colours = [(0, 0, 8)] * PALETTE_SIZE
        for idx, colours in enumerate([first_colours, second_colours, third_colours]):
            (tmp_path / f"{idx:02d}.pal").write_text(_make_jasc(colours), encoding="utf-8")

        paths = [tmp_path / f"{i:02d}.pal" for i in range(3)]
        bank = decode_palette_bank(paths)
        assert bank.shape == (3, PALETTE_SIZE, 4)
        # Index 1 of each palette retains the source colour (8 & 0xF8 == 8) and alpha 255.
        assert tuple(bank[0, 1]) == (8, 0, 0, 255)
        assert tuple(bank[1, 1]) == (0, 8, 0, 255)
        assert tuple(bank[2, 1]) == (0, 0, 8, 255)

    def test_empty_path_sequence_rejects(self) -> None:
        with pytest.raises(PaletteFormatError, match="at least one palette path"):
            decode_palette_bank([])

    def test_missing_file_rejects(self, tmp_path: Path) -> None:
        with pytest.raises(PaletteFormatError, match="could not read palette"):
            decode_palette_bank([tmp_path / "nope.pal"])

    def test_wrong_jasc_header_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        text = _make_jasc(_identity_palette()).replace("JASC-PAL", "NOPE-PAL", 1)
        pal.write_text(text, encoding="utf-8")
        with pytest.raises(PaletteFormatError, match="JASC-PAL"):
            decode_palette_bank([pal])

    def test_wrong_version_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        text = _make_jasc(_identity_palette()).replace("0100", "0200", 1)
        pal.write_text(text, encoding="utf-8")
        with pytest.raises(PaletteFormatError, match="'0100'"):
            decode_palette_bank([pal])

    def test_wrong_declared_count_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        # Declare 8 but body still has 16 colours (parser checks declaration first).
        pal.write_text(_make_jasc(_identity_palette(), declared=8), encoding="utf-8")
        with pytest.raises(PaletteFormatError, match="declared colour count"):
            decode_palette_bank([pal])

    def test_too_few_lines_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        pal.write_text("JASC-PAL\n0100\n16\n0 0 0\n", encoding="utf-8")
        with pytest.raises(PaletteFormatError, match="at least"):
            decode_palette_bank([pal])

    def test_non_decimal_rgb_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        colours = _identity_palette()
        bad = _make_jasc(colours).replace("0 0 0", "FF 00 00", 1)
        pal.write_text(bad, encoding="utf-8")
        with pytest.raises(PaletteFormatError, match="non-decimal RGB"):
            decode_palette_bank([pal])

    def test_rgb_out_of_range_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        colours = _identity_palette()
        bad = _make_jasc(colours).replace("0 0 0", "256 0 0", 1)
        pal.write_text(bad, encoding="utf-8")
        with pytest.raises(PaletteFormatError, match=r"out of \[0, 255\]"):
            decode_palette_bank([pal])

    def test_wrong_arity_rejects(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        colours = _identity_palette()
        bad = _make_jasc(colours).replace("0 0 0", "0 0", 1)
        pal.write_text(bad, encoding="utf-8")
        with pytest.raises(PaletteFormatError, match="decimal triple"):
            decode_palette_bank([pal])

    def test_crlf_line_endings_accepted(self, tmp_path: Path) -> None:
        pal = tmp_path / "00.pal"
        text = _make_jasc(_identity_palette()).replace("\n", "\r\n")
        pal.write_text(text, encoding="utf-8")
        bank = decode_palette_bank([pal])
        # CRLF should parse cleanly and produce the same content as LF.
        assert bank.shape == (1, PALETTE_SIZE, 4)
