"""Tests for ``porymap_mcp.tools.rendering``.

Each test builds a complete synthetic pokeemerald-shape project under
``tmp_path`` — porymap.project.cfg, layouts.json, map_groups.json,
a map.json + map.bin, and a primary/secondary tileset pair (tiles.png +
00.pal..12.pal + metatiles.bin + metatile_attributes.bin). The render
tools' body functions are then invoked directly. We assert on:

  - the round-trip pixel content of the returned PNG (palette mode is
    lossless by construction, so decoded RGBA must match the assembled
    layout pixel-for-pixel),
  - the ``ToolResult.structured_content`` metadata fields, and
  - every error path (unsupported overlays / include_border, scale
    bounds, region bounds, missing palettes, mismatched tileset kinds).
"""

from __future__ import annotations

import base64
import io
import struct
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from PIL import Image

from porymap_mcp.errors import (
    PaletteFormatError,
    ProjectError,
)
from porymap_mcp.render.compose import PALETTE_SIZE
from porymap_mcp.tools import rendering

# --- Synthetic fixture helpers --------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_indexed_png(path: Path, indices: np.ndarray) -> None:
    """Write a (H, W) uint8 palette-index array as an 8-bit indexed PNG."""
    img = Image.fromarray(indices.astype(np.uint8), mode="P")
    img.putpalette([v for i in range(256) for v in (i, i, i)])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _make_jasc(colours: list[tuple[int, int, int]]) -> str:
    body = "\n".join(f"{r} {g} {b}" for r, g, b in colours)
    return f"JASC-PAL\n0100\n{PALETTE_SIZE}\n{body}\n"


def _solid_palette(rgb: tuple[int, int, int]) -> str:
    # Index 0 is transparent by convention; we still set it to ``rgb`` for
    # background-fill predictability. Indices 1..15 get the same colour so
    # any (palette, index) reference resolves to it.
    return _make_jasc([rgb] * PALETTE_SIZE)


def _tile_word(tile_id: int, palette_num: int = 0, xflip: bool = False, yflip: bool = False) -> int:
    """Pack a 2-byte tile entry per ADR-0010 §"Metatile composition"."""
    return (
        (tile_id & 0x03FF)
        | ((1 if xflip else 0) << 10)
        | ((1 if yflip else 0) << 11)
        | ((palette_num & 0x0F) << 12)
    )


def _metatile_bytes(tile_entries: list[int]) -> bytes:
    """Encode a list of 16-bit tile entries (length 8 dual / 12 triple)."""
    return b"".join(struct.pack("<H", w) for w in tile_entries)


def _map_bin_bytes(width: int, height: int, metatile_ids: list[list[int]]) -> bytes:
    """Pack metatile_ids[y][x] into the map.bin layout."""
    out = bytearray()
    for y in range(height):
        for x in range(width):
            mid = metatile_ids[y][x]
            out.extend(struct.pack("<H", mid & 0x03FF))
    return bytes(out)


PROJECT_CFG = (
    "base_game_version=pokeemerald\n"
    "use_poryscript=0\n"
    "use_custom_border_size=0\n"
    "enable_triple_layer_metatiles=0\n"
    "metatile_attributes_size=2\n"
    "metatile_behavior_mask=0x00FF\n"
    "metatile_terrain_type_mask=0x3E00\n"
    "metatile_encounter_type_mask=0xC000\n"
    "metatile_layer_type_mask=0x6000\n"
    "unused_tile_normal=0x0000\n"
    "unused_tile_covered=0x0000\n"
    "unused_tile_split=0x0000\n"
    # transparency_color absent → falls back to palette[0][0]
)


LAYOUTS_JSON = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_TEST_TOWN",
      "name": "TestTown_Layout",
      "width": 3,
      "height": 2,
      "primary_tileset": "gTileset_PrimaryTest",
      "secondary_tileset": "gTileset_SecondaryTest",
      "border_filepath": "data/layouts/TestTown/border.bin",
      "blockdata_filepath": "data/layouts/TestTown/map.bin"
    }
  ]
}
"""

MAP_GROUPS_JSON = """\
{
  "group_order": [
    "gMapGroup_Test"
  ],
  "gMapGroup_Test": [
    "TestTown"
  ]
}
"""

MAP_JSON = """\
{
  "id": "MAP_TEST_TOWN",
  "name": "TestTown",
  "layout": "LAYOUT_TEST_TOWN",
  "music": "MUS_NONE",
  "region_map_section": "MAPSEC_NONE",
  "requires_flash": false,
  "weather": "WEATHER_NONE",
  "map_type": "MAP_TYPE_TOWN",
  "allow_cycling": true,
  "allow_escaping": false,
  "allow_running": true,
  "show_map_name": true,
  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
  "object_events": [],
  "warp_events": [],
  "coord_events": [],
  "bg_events": [],
  "connections": []
}
"""


def _build_tileset(
    project_root: Path,
    *,
    kind: str,
    name: str,
    palette_rgb_primary: tuple[int, int, int],
    palette_rgb_secondary: tuple[int, int, int],
    metatiles: list[bytes],
    attributes: bytes,
    tile_count: int = 4,
) -> None:
    """Write a tileset to disk with a known palette + N solid-colour tiles.

    The tileset's own ``tiles.png`` contains ``tile_count`` 8x8 tiles. Tile 0
    is filled with palette index 1 (opaque); tile i (i > 0) is filled with
    palette index ``i`` if i < 16, else 1. All 13 palette files exist on
    disk. Slots 0..5 use ``palette_rgb_primary``; slots 6..12 use
    ``palette_rgb_secondary``. The kind ("primary" / "secondary") only
    affects placement under ``data/tilesets/<kind>/<name>/``.
    """
    base = project_root / "data" / "tilesets" / kind / name
    # tiles.png: tile_count tiles laid out horizontally, each 8x8.
    indices = np.zeros((8, tile_count * 8), dtype=np.uint8)
    for tid in range(tile_count):
        idx_value = (tid % 15) + 1  # always > 0 so the tile is fully opaque
        indices[:, tid * 8 : (tid + 1) * 8] = idx_value
    _write_indexed_png(base / "tiles.png", indices)

    # palettes/00..12.pal
    for i in range(13):
        colour = palette_rgb_primary if i < 6 else palette_rgb_secondary
        _write(base / "palettes" / f"{i:02d}.pal", _solid_palette(colour))

    # metatiles.bin (dual-layer: 16 bytes per metatile)
    _write_bytes(base / "metatiles.bin", b"".join(metatiles))
    # metatile_attributes.bin (2 bytes per metatile, all zero → Normal layer)
    _write_bytes(base / "metatile_attributes.bin", attributes)


def _solid_metatile(tile_id: int, palette_num: int) -> bytes:
    """Build a dual-layer metatile (8 tile entries) where every entry is the
    same (tile_id, palette_num). Layer_type defaults to Normal, so the
    bottom layer is filled by ``unused_tile_normal=0`` → tile 0 of the
    bank, painted with palette 0.
    """
    word = _tile_word(tile_id, palette_num=palette_num)
    return _metatile_bytes([word] * 8)


def _build_project(tmp_path: Path) -> Path:
    """Build a complete 3x2 synthetic project under ``tmp_path`` and return root.

    Layout:
      - Primary tileset ``primary_test`` with 2 metatiles:
          * metatile 0 (id 0): solid colour A from palette 0 (primary's slot).
          * metatile 1 (id 1): solid colour B from palette 6 (secondary slot,
            referenced from primary metatile to verify cross-tileset palette
            indexing works in the combined bank).
      - Secondary tileset ``secondary_test`` with 1 metatile:
          * metatile 0 (which lives at combined index 512): solid colour C
            from palette 0.

      - Map layout (3x2), top-left origin:
          row 0: [ 0 | 1 | 512 ]
          row 1: [ 1 | 0 | 512 ]
    """
    project = tmp_path / "project"
    project.mkdir()
    _write(project / "porymap.project.cfg", PROJECT_CFG)
    _write(project / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(project / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
    _write(project / "data" / "maps" / "TestTown" / "map.json", MAP_JSON)

    # Primary: 2 metatiles, attributes all-zero (LayerType=Normal → bottom
    # layer filled by unused_tile_normal=0 = primary's tile 0, palette 0).
    # We make tile 0 use palette index 1 (opaque) so the "unused fill"
    # tile is opaque too — keeps PNG palette mode active.
    primary_metatiles = [
        _solid_metatile(tile_id=0, palette_num=0),  # metatile 0 -> palette 0 (colour A)
        _solid_metatile(tile_id=0, palette_num=6),  # metatile 1 -> palette 6 (colour C)
    ]
    primary_attrs = b"\x00\x00" * 2  # both zero → Normal
    _build_tileset(
        project,
        kind="primary",
        name="primary_test",
        palette_rgb_primary=(8, 0, 0),  # colour A: red
        palette_rgb_secondary=(0, 0, 8),  # unused on primary's side
        metatiles=primary_metatiles,
        attributes=primary_attrs,
    )

    # Secondary: 1 metatile referencing its own palette 0
    # (which in the combined bank maps to the primary's palette 0).
    # But the metatile sits at combined index NUM_METATILES_PRIMARY (512),
    # so map.bin can reference 512.
    secondary_metatiles = [_solid_metatile(tile_id=0, palette_num=0)]
    secondary_attrs = b"\x00\x00"
    _build_tileset(
        project,
        kind="secondary",
        name="secondary_test",
        palette_rgb_primary=(8, 0, 0),  # slots 0..5 — match primary
        palette_rgb_secondary=(0, 0, 8),  # slots 6..12 — colour C: blue
        metatiles=secondary_metatiles,
        attributes=secondary_attrs,
    )

    # map.bin (3x2): row 0 = [0, 1, 512]; row 1 = [1, 0, 512]
    grid = [[0, 1, 512], [1, 0, 512]]
    _write_bytes(
        project / "data" / "layouts" / "TestTown" / "map.bin",
        _map_bin_bytes(3, 2, grid),
    )
    # border.bin (default 2x2, all zeros — irrelevant since include_border
    # is not implemented in this slice but the file must exist for the
    # Project layer if anything tries to read it).
    _write_bytes(
        project / "data" / "layouts" / "TestTown" / "border.bin",
        _map_bin_bytes(2, 2, [[0, 0], [0, 0]]),
    )
    return project


def _decode_png(png_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes back to a ``uint8 (H, W, 4)`` RGBA array via Pillow."""
    return np.array(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))


def _decode_tool_result_image(result: object) -> np.ndarray:
    """Pluck the ImageContent block out of a ToolResult and decode it."""
    content = getattr(result, "content", None)
    assert content is not None
    assert len(content) == 1
    block = content[0]
    assert block.type == "image"
    assert block.mimeType == "image/png"
    return _decode_png(base64.b64decode(block.data))


# --- render_map -----------------------------------------------------------


class TestRenderMap:
    def test_full_render_pixel_content(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result = rendering.render_map(str(project), "MAP_TEST_TOWN")
        rgba = _decode_tool_result_image(result)

        # 3x2 metatiles * 16 pixels = 48x32 image.
        assert rgba.shape == (32, 48, 4)
        # Spot-check each metatile cell (16x16 block) by its centre pixel.
        red = (8, 0, 0, 255)
        blue = (0, 0, 8, 255)
        # Layout:
        #   row 0: [colour_A=red(M0), colour_C=blue(M1), colour_A=red(M512)]
        #   row 1: [colour_C=blue(M1), colour_A=red(M0), colour_A=red(M512)]
        expected = [
            [red, blue, red],
            [blue, red, red],
        ]
        for grid_y, row in enumerate(expected):
            for grid_x, want_rgba in enumerate(row):
                py = grid_y * 16 + 8
                px = grid_x * 16 + 8
                got = tuple(int(c) for c in rgba[py, px])
                assert got == want_rgba, (
                    f"mismatch at metatile ({grid_x},{grid_y}) px=({px},{py}): "
                    f"got {got}, want {want_rgba}"
                )

    def test_structured_content_metadata(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result = rendering.render_map(str(project), "MAP_TEST_TOWN", scale=2)
        sc = cast(dict[str, object], result.structured_content)

        assert sc["map_name"] == "MAP_TEST_TOWN"
        assert sc["layout_id"] == "LAYOUT_TEST_TOWN"
        assert sc["dimensions"] == {"width": 3, "height": 2}
        assert sc["pixel_dimensions"] == {"width": 48 * 2, "height": 32 * 2}
        assert sc["scale"] == 2
        assert sc["encoding"] in ("png-palette-8", "png-rgba-8")
        assert isinstance(sc["byte_size"], int)
        assert sc["tilesets"] == {"primary": "primary_test", "secondary": "secondary_test"}
        assert sc["include_border"] is False
        assert sc["overlays"] == []

    def test_scale_applies_nearest_neighbor(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result_1x = rendering.render_map(str(project), "MAP_TEST_TOWN", scale=1)
        result_4x = rendering.render_map(str(project), "MAP_TEST_TOWN", scale=4)
        rgba_1x = _decode_tool_result_image(result_1x)
        rgba_4x = _decode_tool_result_image(result_4x)

        assert rgba_4x.shape == (rgba_1x.shape[0] * 4, rgba_1x.shape[1] * 4, 4)
        # Every 4x4 block in rgba_4x must equal the matching 1x1 pixel in rgba_1x.
        for y in range(rgba_1x.shape[0]):
            for x in range(rgba_1x.shape[1]):
                block = rgba_4x[y * 4 : (y + 1) * 4, x * 4 : (x + 1) * 4]
                assert np.all(block == rgba_1x[y, x]), (
                    f"scale=4 block at ({x},{y}) is not uniform / matches 1x"
                )

    def test_rejects_overlays(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match="overlays not yet implemented"):
            rendering.render_map(str(project), "MAP_TEST_TOWN", overlays=["collision"])

    def test_include_border_wraps_map_in_border_frame(self, tmp_path: Path) -> None:
        # Border.bin in the fixture references metatile 0 (colour A red), so
        # include_border=True should produce a map with a red frame around
        # the original map content. Frame default is 7 metatiles per side =
        # 7*16 = 112 px each side.
        project = _build_project(tmp_path)
        result = rendering.render_map(str(project), "MAP_TEST_TOWN", include_border=True)
        rgba = _decode_tool_result_image(result)

        from porymap_mcp.tools.rendering import DEFAULT_BORDER_FRAME_METATILES

        frame_px = DEFAULT_BORDER_FRAME_METATILES * 16  # 112
        # Map: 3x2 metatiles = 48x32 px. Output: 48+2*112 = 272 wide,
        # 32+2*112 = 256 tall.
        assert rgba.shape == (32 + 2 * frame_px, 48 + 2 * frame_px, 4)
        # Top-left corner is the border (red, colour A).
        assert tuple(int(c) for c in rgba[0, 0]) == (8, 0, 0, 255)
        # Centre of the map area: position (frame_px + 8, frame_px + 8) is
        # the centre of metatile (0, 0) of the original map → metatile 0
        # → colour A red.
        assert tuple(int(c) for c in rgba[frame_px + 8, frame_px + 8]) == (8, 0, 0, 255)
        # Centre of the original map's metatile (1, 0) (colour C blue).
        assert tuple(int(c) for c in rgba[frame_px + 8, frame_px + 16 + 8]) == (0, 0, 8, 255)

        sc = cast(dict[str, object], result.structured_content)
        assert sc["include_border"] is True
        assert sc["border_dimensions"] == {"width": 2, "height": 2}
        assert sc["border_frame_metatiles"] == DEFAULT_BORDER_FRAME_METATILES
        assert sc["pixel_dimensions"] == {
            "width": 48 + 2 * frame_px,
            "height": 32 + 2 * frame_px,
        }

    @pytest.mark.parametrize("scale", [0, -1, 9, 1000])
    def test_rejects_out_of_range_scale(self, tmp_path: Path, scale: int) -> None:
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match=r"scale must be an integer in 1\.\."):
            rendering.render_map(str(project), "MAP_TEST_TOWN", scale=scale)

    def test_missing_palette_file_raises(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        # Delete one of the required palette files.
        secondary = project / "data" / "tilesets" / "secondary" / "secondary_test"
        (secondary / "palettes" / "08.pal").unlink()
        with pytest.raises(PaletteFormatError, match="palette file missing"):
            rendering.render_map(str(project), "MAP_TEST_TOWN")


# --- render_map_region ----------------------------------------------------


class TestRenderMapRegion:
    def test_region_pixel_content(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        # Render only the top-right 1x1 region (metatile 1 in row 0 -> blue).
        result = rendering.render_map_region(str(project), "MAP_TEST_TOWN", x1=1, y1=0, x2=2, y2=1)
        rgba = _decode_tool_result_image(result)
        assert rgba.shape == (16, 16, 4)
        got = tuple(int(c) for c in rgba[8, 8])
        assert got == (0, 0, 8, 255)

    def test_structured_content(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result = rendering.render_map_region(
            str(project), "MAP_TEST_TOWN", x1=0, y1=0, x2=2, y2=2, scale=1
        )
        sc = cast(dict[str, object], result.structured_content)
        assert sc["region"] == {"x1": 0, "y1": 0, "x2": 2, "y2": 2}
        assert sc["dimensions"] == {"width": 2, "height": 2}
        assert sc["pixel_dimensions"] == {"width": 32, "height": 32}

    @pytest.mark.parametrize(
        ("x1", "y1", "x2", "y2"),
        [
            (0, 0, 0, 1),  # zero width
            (0, 0, 1, 0),  # zero height
            (2, 0, 1, 1),  # reversed x
            (-1, 0, 1, 1),  # negative
            (0, 0, 4, 1),  # beyond width
            (0, 0, 1, 3),  # beyond height
        ],
    )
    def test_invalid_region_raises(
        self, tmp_path: Path, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match="render_map_region: region"):
            rendering.render_map_region(str(project), "MAP_TEST_TOWN", x1, y1, x2, y2)

    def test_rejects_overlays(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match="overlays not yet implemented"):
            rendering.render_map_region(
                str(project), "MAP_TEST_TOWN", 0, 0, 1, 1, overlays=["grid"]
            )


# --- render_metatile ------------------------------------------------------


class TestRenderMetatile:
    def test_renders_primary_metatile(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result = rendering.render_metatile(str(project), "primary_test", 0, scale=1)
        rgba = _decode_tool_result_image(result)

        assert rgba.shape == (16, 16, 4)
        # metatile 0 uses palette 0 → colour A (red)
        got = tuple(int(c) for c in rgba[8, 8])
        assert got == (8, 0, 0, 255)

    def test_renders_secondary_metatile(self, tmp_path: Path) -> None:
        # Secondary's metatile 0 lives at id 0 from the *tileset's own*
        # perspective. The tool exposes metatile_id as the per-tileset
        # local id? No — per phase-4 §4, metatile_id is the absolute id.
        # We rendered secondary metatile (combined index 512) above; for
        # a pure secondary tileset preview the user would call with
        # metatile_id=512.
        project = _build_project(tmp_path)
        result = rendering.render_metatile(str(project), "secondary_test", 512, scale=1)
        rgba = _decode_tool_result_image(result)
        assert rgba.shape == (16, 16, 4)
        # Secondary metatile 0 uses palette 0 in the secondary tileset →
        # the combined-bank palette 0 (primary's slot 0) → colour A (red).
        got = tuple(int(c) for c in rgba[8, 8])
        assert got == (8, 0, 0, 255)

    def test_default_scale_is_4(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result = rendering.render_metatile(str(project), "primary_test", 0)
        rgba = _decode_tool_result_image(result)
        # 16 px * 4 = 64
        assert rgba.shape == (64, 64, 4)
        sc = cast(dict[str, object], result.structured_content)
        assert sc["scale"] == 4

    def test_companion_tileset_pairing(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        result = rendering.render_metatile(str(project), "primary_test", 0, scale=1)
        sc = cast(dict[str, object], result.structured_content)
        assert sc["tileset_name"] == "primary_test"
        assert sc["tileset_kind"] == "primary"
        assert sc["companion_tileset"] == "secondary_test"

    def test_rejects_out_of_range_metatile_id(self, tmp_path: Path) -> None:
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match="out of range"):
            rendering.render_metatile(str(project), "primary_test", 1024)

    def test_rejects_metatile_id_not_in_bank(self, tmp_path: Path) -> None:
        # Primary has 2 metatiles + padding to 512 + secondary's 1 = 513 total.
        # Asking for 513 should fail with "not present".
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match="not present"):
            rendering.render_metatile(str(project), "primary_test", 513)

    @pytest.mark.parametrize("scale", [0, -1, 9])
    def test_rejects_invalid_scale(self, tmp_path: Path, scale: int) -> None:
        project = _build_project(tmp_path)
        with pytest.raises(ProjectError, match=r"scale must be an integer in 1\.\."):
            rendering.render_metatile(str(project), "primary_test", 0, scale=scale)

    def test_missing_companion_raises(self, tmp_path: Path) -> None:
        # A project with only primaries (no secondary) cannot pair.
        project = tmp_path / "lonely"
        project.mkdir()
        _write(project / "porymap.project.cfg", PROJECT_CFG)
        _write(project / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
        _write(project / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
        _write(project / "data" / "maps" / "TestTown" / "map.json", MAP_JSON)
        _build_tileset(
            project,
            kind="primary",
            name="primary_test",
            palette_rgb_primary=(8, 0, 0),
            palette_rgb_secondary=(0, 0, 8),
            metatiles=[_solid_metatile(0, 0)],
            attributes=b"\x00\x00",
        )
        with pytest.raises(ProjectError, match="no secondary tileset available"):
            rendering.render_metatile(str(project), "primary_test", 0)


# --- Tileset-pair resolution ----------------------------------------------


class TestTilesetPairResolution:
    def test_layout_with_wrong_kind_raises(self, tmp_path: Path) -> None:
        """A layout that declares a secondary's c_label as primary_tileset
        should be rejected with a clear message — surfaces a class of
        configuration bug the L1 layer can't catch on its own."""
        project = _build_project(tmp_path)
        # Patch layouts.json to swap primary/secondary references.
        bad_layouts = (
            (project / "data" / "layouts" / "layouts.json")
            .read_text(encoding="utf-8")
            .replace('"gTileset_PrimaryTest"', '"_TMP_"')
            .replace('"gTileset_SecondaryTest"', '"gTileset_PrimaryTest"')
            .replace('"_TMP_"', '"gTileset_SecondaryTest"')
        )
        _write(project / "data" / "layouts" / "layouts.json", bad_layouts)
        with pytest.raises(ProjectError, match="resolves to a"):
            rendering.render_map(str(project), "MAP_TEST_TOWN")


# --- Registration smoke ---------------------------------------------------


class TestRegister:
    def test_build_server_registers_render_tools(self) -> None:
        import asyncio

        from porymap_mcp.server import build_server

        mcp = build_server()
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert {"render_map", "render_map_region", "render_metatile"}.issubset(names)
