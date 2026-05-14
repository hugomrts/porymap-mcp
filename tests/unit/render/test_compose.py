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

from porymap_mcp.errors import (
    MetatilesBinFormatError,
    PaletteFormatError,
    TilesPngFormatError,
)
from porymap_mcp.parsers.attributes import MetatileAttributes
from porymap_mcp.render.compose import (
    PALETTE_SIZE,
    TILE_SIZE,
    decode_metatile_bank,
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

    def test_jasc_values_passthrough_unchanged(self, tmp_path: Path) -> None:
        # Porymap does not apply GBA 5-bit hardware quantization to JASC
        # palette entries on export — pokeemerald's pal files already
        # store the artist's chosen 8-bit RGB, and Porymap propagates
        # those bytes byte-for-byte through to the rendered PNG. Verified
        # against the L3 fidelity corpus (cases 1-3) — see ADR-0010 §"GBA
        # quantization" addendum.
        pal = tmp_path / "00.pal"
        pal.write_text(_make_jasc([(255, 255, 255)] * PALETTE_SIZE), encoding="utf-8")

        bank = decode_palette_bank([pal])
        # Index 0 is transparent (alpha 0); RGB preserved as 255.
        assert tuple(bank[0, 0]) == (255, 255, 255, 0)
        for i in range(1, PALETTE_SIZE):
            assert tuple(bank[0, i]) == (255, 255, 255, 255)

    def test_misaligned_5bit_values_preserved(self, tmp_path: Path) -> None:
        # Values that don't sit on a 5-bit boundary (e.g. 41, 139, 197 —
        # commonplace in pokeemerald pal files) are kept verbatim, NOT
        # quantized down. The earlier behaviour (truncate to multiples
        # of 8) broke the fidelity test on every grass / cave / building
        # metatile.
        cases = [(7, 7), (15, 15), (16, 16), (23, 23), (24, 24), (255, 255), (41, 41), (139, 139)]
        colours = [(c, c, c) for c, _ in cases]
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


# --- decode_metatile_bank ---------------------------------------------------
#
# All ``decode_metatile_bank`` tests share these synthetic banks:
#
#   * Tile bank: 16 tiles where tile ``i`` is an 8x8 block filled with palette
#     index ``i`` (so tile 0 is "all index 0" — fully transparent for upper
#     layers; tile 5 is "all index 5"; etc.). Plus a few asymmetric tiles
#     appended for the xflip / yflip tests.
#   * Palette bank: 2 palettes. Palette 0 is a greyscale ramp; palette 1 is a
#     pure-red ramp. Both follow the decoder's convention of alpha=0 at
#     index 0, alpha=255 elsewhere. All RGB values are GBA-aligned (multiples
#     of 8), so & 0xF8 is a no-op on them and per-pixel assertions are exact.


def _solid_tile_bank() -> np.ndarray:
    """16 solid tiles (tile ``i`` = all-``i``) for predictable colour output."""
    bank = np.zeros((16, TILE_SIZE, TILE_SIZE), dtype=np.uint8)
    for i in range(16):
        bank[i] = i
    return bank


def _two_palette_bank() -> np.ndarray:
    """Palette 0 greyscale (R=G=B=i*16), palette 1 pure red (R=i*16)."""
    bank = np.zeros((2, PALETTE_SIZE, 4), dtype=np.uint8)
    for i in range(PALETTE_SIZE):
        v = i * 16
        alpha = 0 if i == 0 else 255
        bank[0, i] = (v, v, v, alpha)
        bank[1, i] = (v, 0, 0, alpha)
    return bank


def _tile_word(tile_id: int, *, xflip: bool = False, yflip: bool = False, palette: int = 0) -> int:
    """Pack one 2-byte tile entry per ADR-0010 §"Metatile composition"."""
    return (
        (tile_id & 0x03FF)
        | ((1 if xflip else 0) << 10)
        | ((1 if yflip else 0) << 11)
        | ((palette & 0x0F) << 12)
    )


def _metatile_bytes(words: list[int]) -> bytes:
    """Pack a list of 16-bit tile entries into little-endian bytes."""
    return b"".join(w.to_bytes(2, "little") for w in words)


def _attr(layer_type: int = 0) -> MetatileAttributes:
    """Minimal :class:`MetatileAttributes` for tests — only ``layer_type`` matters."""
    return MetatileAttributes(
        behavior=0, terrain_type=0, encounter_type=0, layer_type=layer_type, raw=0
    )


def _transparent_dual() -> bytes:
    """8 tile entries all = tile 0 (fully transparent, palette 0)."""
    return _metatile_bytes([_tile_word(0)] * 8)


def _common_kwargs(**overrides: int | None) -> dict[str, int | None]:
    """Default ``decode_metatile_bank`` kwargs; tests override what they need."""
    base: dict[str, int | None] = {
        "unused_tile_normal": 0,
        "unused_tile_covered": 0,
        "unused_tile_split": 0,
        "transparency_color": None,
    }
    base.update(overrides)
    return base


class TestDecodeMetatileBankDualLayer:
    """Dual-layer mode (vanilla RSE / pokeemerald — 16-byte metatiles)."""

    def test_layer_type_normal_paints_unused_tile_on_bottom(self) -> None:
        # All 8 file entries are transparent (tile 0). Only the unused_tile_normal
        # fill on the bottom layer should show — palette 0, alpha 255.
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=0)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_normal=5),  # type: ignore[arg-type]
        )
        assert bank.shape == (1, 16, 16, 4)
        # palette[0][5] = (80, 80, 80, 255)
        expected = np.tile(np.array([80, 80, 80, 255], dtype=np.uint8), (16, 16, 1))
        assert np.array_equal(bank[0], expected)

    def test_layer_type_covered_paints_unused_tile_on_top(self) -> None:
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=1)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_covered=7),  # type: ignore[arg-type]
        )
        # palette[0][7] = (112, 112, 112, 255). Bottom + middle are transparent;
        # top (= unused_covered) paints over.
        assert np.all(bank[0] == np.array([112, 112, 112, 255], dtype=np.uint8))

    def test_layer_type_split_paints_unused_tile_in_middle(self) -> None:
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=2)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_split=9),  # type: ignore[arg-type]
        )
        # palette[0][9] = (144, 144, 144, 255). Middle (unused_split) paints;
        # bottom & top are transparent file content.
        assert np.all(bank[0] == np.array([144, 144, 144, 255], dtype=np.uint8))

    def test_unknown_layer_type_falls_back_to_normal(self) -> None:
        # layer_type=3 isn't one of the defined values in dual-layer mode —
        # per Porymap's switch-default behavior we treat it as Normal.
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=3)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_normal=4),  # type: ignore[arg-type]
        )
        # palette[0][4] = (64, 64, 64, 255). If covered/split were used we'd
        # see unused_tile_covered/split (both 0 → fully transparent → bg=black).
        assert np.all(bank[0] == np.array([64, 64, 64, 255], dtype=np.uint8))

    def test_layer_z_order_top_overrides_bottom(self) -> None:
        # Normal: bottom=unused_normal=5, middle=file[0:4], top=file[4:8].
        # File middle = tile 0 (transparent). File top tile 0 = tile_id=3 at the
        # top-left quad (palette 1 → pure red index 3 = (48, 0, 0, 255)).
        # Expected pixel at (0,0): red from top overrides grey bottom.
        # Expected pixel elsewhere: grey from bottom (top tiles 1..3 transparent).
        bank = decode_metatile_bank(
            _metatile_bytes(
                [_tile_word(0)] * 4  # middle: all transparent
                + [_tile_word(3, palette=1), _tile_word(0), _tile_word(0), _tile_word(0)]  # top
            ),
            [_attr(layer_type=0)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_normal=5),  # type: ignore[arg-type]
        )
        # Top-left 8x8 quadrant: pure red index 3 (48, 0, 0, 255).
        assert np.all(bank[0, 0:8, 0:8] == np.array([48, 0, 0, 255], dtype=np.uint8))
        # Other three quadrants: grey index 5 (80, 80, 80, 255) — bottom layer.
        assert np.all(bank[0, 0:8, 8:16] == np.array([80, 80, 80, 255], dtype=np.uint8))
        assert np.all(bank[0, 8:16, 0:8] == np.array([80, 80, 80, 255], dtype=np.uint8))
        assert np.all(bank[0, 8:16, 8:16] == np.array([80, 80, 80, 255], dtype=np.uint8))

    def test_quad_positions_top_right_bottom_left_bottom_right(self) -> None:
        # Verify the 4 sub-tile slots map to (0,0), (0,8), (8,0), (8,8). Each
        # of the 4 middle-layer entries gets a distinct tile (1, 2, 3, 4) and
        # we read back the 8x8 quadrants.
        words = (
            [_tile_word(1), _tile_word(2), _tile_word(3), _tile_word(4)]  # middle
            + [_tile_word(0)] * 4  # top transparent
        )
        bank = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr(layer_type=1)],  # Covered → bottom=file[0:4], middle=file[4:8], top=unused
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_covered=0),  # type: ignore[arg-type]
        )
        # Bottom layer paints since file[0:4] are non-transparent in palette 0.
        # palette[0][i] = (i*16, i*16, i*16, 255).
        assert np.all(bank[0, 0:8, 0:8] == np.array([16, 16, 16, 255], dtype=np.uint8))
        assert np.all(bank[0, 0:8, 8:16] == np.array([32, 32, 32, 255], dtype=np.uint8))
        assert np.all(bank[0, 8:16, 0:8] == np.array([48, 48, 48, 255], dtype=np.uint8))
        assert np.all(bank[0, 8:16, 8:16] == np.array([64, 64, 64, 255], dtype=np.uint8))


class TestDecodeMetatileBankTripleLayer:
    """Triple-layer mode (pokeemerald-expansion — 24-byte metatiles)."""

    def test_three_file_layers_ignore_layer_type_and_unused_fills(self) -> None:
        # File: bottom=tile 2 (all positions), middle=transparent, top=tile 4
        # at quad (0,0) only. Triple-layer ignores layer_type and unused_tile_*.
        # Bottom paints grey 2 → (32, 32, 32, 255).
        # Top at quad (0,0) paints grey 4 → (64, 64, 64, 255) overrides.
        words = (
            [_tile_word(2), _tile_word(2), _tile_word(2), _tile_word(2)]  # bottom
            + [_tile_word(0)] * 4  # middle transparent
            + [_tile_word(4), _tile_word(0), _tile_word(0), _tile_word(0)]  # top
        )
        bank = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr(layer_type=2)],  # would be Split in dual mode — must be ignored
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=3,
            **_common_kwargs(unused_tile_normal=15, unused_tile_split=15),  # type: ignore[arg-type]
        )
        # Top-left: tile 4 from top layer.
        assert np.all(bank[0, 0:8, 0:8] == np.array([64, 64, 64, 255], dtype=np.uint8))
        # Other quadrants: bottom tile 2 — unused_tile_15 (would be all-15 →
        # (240, 240, 240)) does NOT appear because triple-layer ignores fills.
        assert np.all(bank[0, 0:8, 8:16] == np.array([32, 32, 32, 255], dtype=np.uint8))
        assert np.all(bank[0, 8:16, 0:8] == np.array([32, 32, 32, 255], dtype=np.uint8))
        assert np.all(bank[0, 8:16, 8:16] == np.array([32, 32, 32, 255], dtype=np.uint8))


class TestDecodeMetatileBankTileFlips:
    """xflip / yflip bit handling on individual tile entries."""

    @staticmethod
    def _asymmetric_tile_bank() -> np.ndarray:
        """Tile bank where tile 1 has top half index 1, bottom half index 2;
        tile 3 has left half index 1, right half index 2."""
        bank = np.zeros((16, TILE_SIZE, TILE_SIZE), dtype=np.uint8)
        for i in range(16):
            bank[i] = i  # solid by default
        bank[1, :, :] = 0  # reset
        bank[1, 0:4, :] = 1  # top half
        bank[1, 4:8, :] = 2  # bottom half
        bank[3, :, :] = 0
        bank[3, :, 0:4] = 1  # left half
        bank[3, :, 4:8] = 2  # right half
        return bank

    def test_yflip_swaps_top_and_bottom_rows(self) -> None:
        # Cover the top-left quad of a triple-layer metatile's top layer with
        # tile 1 (top half = idx 1 grey, bottom half = idx 2 grey), with yflip.
        # Expected: rows 0..3 of quad get idx 2 (32, 32, 32, 255); rows 4..7
        # get idx 1 (16, 16, 16, 255).
        bank = self._asymmetric_tile_bank()
        words = (
            [_tile_word(0)] * 4  # bottom transparent
            + [_tile_word(0)] * 4  # middle transparent
            + [_tile_word(1, yflip=True), _tile_word(0), _tile_word(0), _tile_word(0)]
        )
        out = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr()],
            bank,
            _two_palette_bank(),
            layers=3,
            **_common_kwargs(),  # type: ignore[arg-type]
        )
        # Top-left quad rows 0..3: idx 2 (32, 32, 32, 255).
        assert np.all(out[0, 0:4, 0:8] == np.array([32, 32, 32, 255], dtype=np.uint8))
        # Top-left quad rows 4..7: idx 1 (16, 16, 16, 255).
        assert np.all(out[0, 4:8, 0:8] == np.array([16, 16, 16, 255], dtype=np.uint8))

    def test_xflip_swaps_left_and_right_columns(self) -> None:
        bank = self._asymmetric_tile_bank()
        words = (
            [_tile_word(0)] * 4
            + [_tile_word(0)] * 4
            + [_tile_word(3, xflip=True), _tile_word(0), _tile_word(0), _tile_word(0)]
        )
        out = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr()],
            bank,
            _two_palette_bank(),
            layers=3,
            **_common_kwargs(),  # type: ignore[arg-type]
        )
        # Top-left quad cols 0..3: idx 2 (32, 32, 32, 255).
        assert np.all(out[0, 0:8, 0:4] == np.array([32, 32, 32, 255], dtype=np.uint8))
        # Top-left quad cols 4..7: idx 1 (16, 16, 16, 255).
        assert np.all(out[0, 0:8, 4:8] == np.array([16, 16, 16, 255], dtype=np.uint8))

    def test_xflip_and_yflip_combined(self) -> None:
        # Tile 1 (top=1, bottom=2) with both flips: top↔bottom (yflip) — xflip
        # leaves it unchanged since the tile is horizontally uniform.
        bank = self._asymmetric_tile_bank()
        words = (
            [_tile_word(0)] * 4
            + [_tile_word(0)] * 4
            + [_tile_word(1, xflip=True, yflip=True), _tile_word(0), _tile_word(0), _tile_word(0)]
        )
        out = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr()],
            bank,
            _two_palette_bank(),
            layers=3,
            **_common_kwargs(),  # type: ignore[arg-type]
        )
        # Expected same as pure yflip on tile 1.
        assert np.all(out[0, 0:4, 0:8] == np.array([32, 32, 32, 255], dtype=np.uint8))
        assert np.all(out[0, 4:8, 0:8] == np.array([16, 16, 16, 255], dtype=np.uint8))


class TestDecodeMetatileBankTransparencyFill:
    """Bottom-layer transparency colour (ADR-0010 §"Metatile composition")."""

    def test_transparency_color_fills_when_set(self) -> None:
        # All layers transparent — entire metatile shows the transparency colour.
        transparency_color = 0x80C0F0  # 5-bit aligned: 0x80 & 0xF8 == 0x80, etc.
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=0)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            unused_tile_normal=0,  # transparent: tile 0 is all-zero, palette 0[0]=alpha 0
            unused_tile_covered=0,
            unused_tile_split=0,
            transparency_color=transparency_color,
        )
        assert np.all(bank[0] == np.array([0x80, 0xC0, 0xF0, 255], dtype=np.uint8))

    def test_transparency_color_passthrough_unchanged(self) -> None:
        # Porymap propagates the configured transparency_color verbatim
        # (no GBA quantization), matching ADR-0010 §"GBA quantization"
        # addendum verified against the L3 fidelity corpus.
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=0)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            unused_tile_normal=0,
            unused_tile_covered=0,
            unused_tile_split=0,
            transparency_color=0xFFFFFF,
        )
        assert np.all(bank[0] == np.array([0xFF, 0xFF, 0xFF, 255], dtype=np.uint8))

    def test_transparency_color_none_falls_back_to_palette_zero_zero(self) -> None:
        # Custom palette[0][0] RGB; alpha 0 (per decode_palette_bank).
        palettes = _two_palette_bank()
        palettes[0, 0] = (48, 80, 16, 0)
        bank = decode_metatile_bank(
            _transparent_dual(),
            [_attr(layer_type=0)],
            _solid_tile_bank(),
            palettes,
            layers=2,
            unused_tile_normal=0,
            unused_tile_covered=0,
            unused_tile_split=0,
            transparency_color=None,
        )
        # Canvas takes palette[0][0]'s RGB with alpha 255 (opaque background).
        assert np.all(bank[0] == np.array([48, 80, 16, 255], dtype=np.uint8))


class TestDecodeMetatileBankValidation:
    """Input validation errors."""

    def test_rejects_layers_other_than_2_or_3(self) -> None:
        with pytest.raises(MetatilesBinFormatError, match="layers must be 2"):
            decode_metatile_bank(
                _transparent_dual(),
                [_attr()],
                _solid_tile_bank(),
                _two_palette_bank(),
                layers=4,
                **_common_kwargs(),  # type: ignore[arg-type]
            )

    def test_rejects_size_not_multiple_of_dual_layer_metatile(self) -> None:
        with pytest.raises(MetatilesBinFormatError, match="not a positive multiple of 16"):
            decode_metatile_bank(
                b"\x00" * 15,  # one byte short of a dual-layer metatile
                [_attr()],
                _solid_tile_bank(),
                _two_palette_bank(),
                layers=2,
                **_common_kwargs(),  # type: ignore[arg-type]
            )

    def test_rejects_empty_bytes(self) -> None:
        with pytest.raises(MetatilesBinFormatError, match="not a positive multiple"):
            decode_metatile_bank(
                b"",
                [],
                _solid_tile_bank(),
                _two_palette_bank(),
                layers=2,
                **_common_kwargs(),  # type: ignore[arg-type]
            )

    def test_rejects_attribute_count_mismatch(self) -> None:
        with pytest.raises(MetatilesBinFormatError, match=r"declares 2 metatiles but 1"):
            decode_metatile_bank(
                _transparent_dual() * 2,
                [_attr()],  # only 1, but file declares 2
                _solid_tile_bank(),
                _two_palette_bank(),
                layers=2,
                **_common_kwargs(),  # type: ignore[arg-type]
            )

    def test_rejects_empty_palette_bank(self) -> None:
        with pytest.raises(PaletteFormatError, match="palette_bank is empty"):
            decode_metatile_bank(
                _transparent_dual(),
                [_attr()],
                _solid_tile_bank(),
                np.zeros((0, PALETTE_SIZE, 4), dtype=np.uint8),
                layers=2,
                **_common_kwargs(),  # type: ignore[arg-type]
            )

    def test_out_of_range_tile_id_silently_skipped(self) -> None:
        # tile_id beyond the bank length is treated as transparent (matches
        # Porymap's fallback when a metatile references a tile slot the
        # currently-loaded tilesets don't provide).
        words = (
            [_tile_word(999)] * 4  # middle: all out-of-range
            + [_tile_word(0)] * 4  # top: transparent
        )
        bank = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr(layer_type=0)],
            _solid_tile_bank(),  # only 16 tiles
            _two_palette_bank(),
            layers=2,
            **_common_kwargs(unused_tile_normal=2),  # type: ignore[arg-type]
        )
        # Bottom layer paints unused_tile_normal=2 = grey idx 2.
        assert np.all(bank[0] == np.array([32, 32, 32, 255], dtype=np.uint8))

    def test_out_of_range_palette_silently_skipped(self) -> None:
        # palette=15 with only 2 palettes in bank: the entry is skipped.
        # Same scaffolding as the previous test — bottom unused_normal still wins.
        words = (
            [_tile_word(1, palette=15)] * 4  # middle: palette out-of-range
            + [_tile_word(0)] * 4
        )
        bank = decode_metatile_bank(
            _metatile_bytes(words),
            [_attr(layer_type=0)],
            _solid_tile_bank(),
            _two_palette_bank(),  # only palettes 0 and 1
            layers=2,
            **_common_kwargs(unused_tile_normal=3),  # type: ignore[arg-type]
        )
        # Middle skipped → bottom (idx 3 grey = (48, 48, 48, 255)) wins.
        assert np.all(bank[0] == np.array([48, 48, 48, 255], dtype=np.uint8))

    def test_multiple_metatiles_handled_independently(self) -> None:
        # Two metatiles back-to-back: first Normal (bottom = unused_normal=5),
        # second Covered (top = unused_covered=7). Verify both decode correctly.
        data = _transparent_dual() + _transparent_dual()
        bank = decode_metatile_bank(
            data,
            [_attr(layer_type=0), _attr(layer_type=1)],
            _solid_tile_bank(),
            _two_palette_bank(),
            layers=2,
            unused_tile_normal=5,
            unused_tile_covered=7,
            unused_tile_split=0,
            transparency_color=None,
        )
        assert bank.shape == (2, 16, 16, 4)
        assert np.all(bank[0] == np.array([80, 80, 80, 255], dtype=np.uint8))
        assert np.all(bank[1] == np.array([112, 112, 112, 255], dtype=np.uint8))
