"""Runnable companion to ``examples/04_render_loop/README.md``.

Demonstrates the L3 self-critique loop end to end:

    paint -> render -> critique -> fix -> re-render

The script:

1. Bootstraps a small synthetic pokeemerald-shape project under
   ``_demo_project/`` (gitignored). In real usage this step is replaced by
   "point ``project_path`` at your pokeemerald checkout".
2. Runs **iteration 1**: a deliberately weak draft of a coastal town
   (a single house dropped onto a sea of grass). Renders to
   ``renders/iter1.png``.
3. Prints the kind of critique the ``map-design-critic`` sub-agent
   produces on iter 1 — the *narrative* lives in this script so the
   example is self-contained; in a real Claude session the critic is
   invoked via the ``Task`` tool with ``subagent_type="map-design-critic"``
   and the iter 1 PNG as input.
4. Runs **iteration 2**: applies the top fixes (coastline, path,
   trees, second house, signpost). Renders to ``renders/iter2.png``.

Both PNGs are committed to the repo so the README can link them
without forcing readers to run Python.

The bootstrap mirrors the synthetic-fixture pattern in
``tests/unit/tools/test_rendering.py`` — see that file for the
byte-level explanation of every artefact written here.
"""

from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from porymap_mcp.render.compose import PALETTE_SIZE
from porymap_mcp.tools import maps as map_tools
from porymap_mcp.tools import rendering as render_tools

# --------------------------------------------------------------------------
# Vocabulary: 8 named metatiles, each a solid colour.
#
# Six metatiles live in the primary tileset (ids 0..5); two live in the
# secondary tileset (combined ids 512, 513). Every metatile is a single
# solid colour drawn from a dedicated palette slot; the "tile art" is
# intentionally bare — the loop is what we're showcasing, not pixel art.
# --------------------------------------------------------------------------

WATER = 0
SAND = 1
GRASS = 2
PATH = 3
TREE = 4
HOUSE_WALL = 5
HOUSE_ROOF = 512
SIGN = 513

# RGB colours per palette slot. All components are multiples of 8 so they
# survive the GBA 5-bit hardware quantization (``& 0xF8``) byte-for-byte.
PALETTES: dict[int, tuple[int, int, int]] = {
    0: (24, 56, 168),  # water  — deep blue
    1: (224, 200, 144),  # sand   — warm tan
    2: (48, 152, 48),  # grass  — mid green
    3: (192, 160, 96),  # path   — light brown
    4: (16, 80, 16),  # tree   — dark green
    5: (160, 56, 56),  # house wall — barn red
    6: (88, 56, 24),  # house roof — dark wood (secondary palette)
    7: (240, 240, 224),  # signpost — bone white (secondary palette)
}

MAP_WIDTH = 8
MAP_HEIGHT = 6
PROJECT_DIR_NAME = "_demo_project"
MAP_BARE_NAME = "CoastalCove"
MAP_ID = f"MAP_{MAP_BARE_NAME.upper()}"


# --------------------------------------------------------------------------
# Bootstrap: build the synthetic project on disk
# --------------------------------------------------------------------------


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_indexed_png(path: Path, indices: np.ndarray) -> None:
    img = Image.fromarray(indices.astype(np.uint8), mode="P")
    img.putpalette([v for i in range(256) for v in (i, i, i)])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _make_jasc(colours: list[tuple[int, int, int]]) -> str:
    body = "\n".join(f"{r} {g} {b}" for r, g, b in colours)
    return f"JASC-PAL\n0100\n{PALETTE_SIZE}\n{body}\n"


def _solid_palette_for(slot_rgb: tuple[int, int, int]) -> str:
    # Every index in the palette resolves to the same colour, so a tile
    # painted with any index 1..15 reads back as ``slot_rgb``. Index 0 is
    # transparent on upper layers, but for our bottom-layer-only metatiles
    # this is irrelevant.
    return _make_jasc([slot_rgb] * PALETTE_SIZE)


def _tile_word(tile_id: int, palette_num: int) -> int:
    """Pack a 2-byte tile entry: 10b id | xflip | yflip | 4b palette."""
    return (tile_id & 0x03FF) | ((palette_num & 0x0F) << 12)


def _solid_metatile(palette_num: int) -> bytes:
    """A dual-layer metatile (8 tile entries) of one solid palette index.

    All entries point at tile 0 of the bank, which the synthetic tileset
    fills with a single palette index — so the whole 16x16 block reads
    back as the chosen palette colour.
    """
    word = _tile_word(tile_id=0, palette_num=palette_num)
    return b"".join(struct.pack("<H", word) for _ in range(8))


def _write_tileset(
    project_root: Path,
    *,
    kind: str,
    name: str,
    metatile_payload: list[bytes],
) -> None:
    base = project_root / "data" / "tilesets" / kind / name

    # tiles.png — a single 8x8 tile filled with palette index 1 (always opaque).
    tiles = np.ones((8, 8), dtype=np.uint8)
    _write_indexed_png(base / "tiles.png", tiles)

    # palettes/00..12.pal — every slot exists; each slot is solid PALETTES[i]
    # for i < 8, then a neutral fill for the unused 8..12 slots.
    for slot in range(13):
        rgb = PALETTES.get(slot, (0, 0, 0))
        _write_text(base / "palettes" / f"{slot:02d}.pal", _solid_palette_for(rgb))

    # metatiles.bin (dual-layer: 16 bytes per metatile = 8 tile entries x 2 bytes)
    _write_bytes(base / "metatiles.bin", b"".join(metatile_payload))

    # metatile_attributes.bin (2 bytes per metatile, all zero -> LayerType=Normal)
    _write_bytes(
        base / "metatile_attributes.bin",
        b"\x00\x00" * len(metatile_payload),
    )


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
)


def _layouts_json() -> str:
    return (
        "{\n"
        '  "layouts_table_label": "gMapLayouts",\n'
        '  "layouts": [\n'
        "    {\n"
        f'      "id": "LAYOUT_{MAP_BARE_NAME.upper()}",\n'
        f'      "name": "{MAP_BARE_NAME}_Layout",\n'
        f'      "width": {MAP_WIDTH},\n'
        f'      "height": {MAP_HEIGHT},\n'
        '      "primary_tileset": "gTileset_PrimaryDemo",\n'
        '      "secondary_tileset": "gTileset_SecondaryDemo",\n'
        f'      "border_filepath": "data/layouts/{MAP_BARE_NAME}/border.bin",\n'
        f'      "blockdata_filepath": "data/layouts/{MAP_BARE_NAME}/map.bin"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def _map_groups_json() -> str:
    return (
        f'{{\n  "group_order": ["gMapGroup_Demo"],\n  "gMapGroup_Demo": ["{MAP_BARE_NAME}"]\n}}\n'
    )


def _map_json() -> str:
    return (
        "{\n"
        f'  "id": "{MAP_ID}",\n'
        f'  "name": "{MAP_BARE_NAME}",\n'
        f'  "layout": "LAYOUT_{MAP_BARE_NAME.upper()}",\n'
        '  "music": "MUS_NONE",\n'
        '  "region_map_section": "MAPSEC_NONE",\n'
        '  "requires_flash": false,\n'
        '  "weather": "WEATHER_NONE",\n'
        '  "map_type": "MAP_TYPE_TOWN",\n'
        '  "allow_cycling": true,\n'
        '  "allow_escaping": false,\n'
        '  "allow_running": true,\n'
        '  "show_map_name": true,\n'
        '  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",\n'
        '  "object_events": [],\n'
        '  "warp_events": [],\n'
        '  "coord_events": [],\n'
        '  "bg_events": [],\n'
        '  "connections": []\n'
        "}\n"
    )


def _pack_map_bin(width: int, height: int, fill_metatile_id: int) -> bytes:
    """All cells filled with one metatile id, collision/elevation = 0."""
    word = struct.pack("<H", fill_metatile_id & 0x03FF)
    return word * (width * height)


def bootstrap_project(project_root: Path) -> None:
    """Write every file needed for a minimal pokeemerald-shape project.

    The map starts filled with GRASS so iter 1 only has to drop a single
    house onto an otherwise empty canvas.
    """
    if project_root.exists():
        shutil.rmtree(project_root)
    project_root.mkdir(parents=True)

    _write_text(project_root / "porymap.project.cfg", PROJECT_CFG)
    _write_text(project_root / "data" / "layouts" / "layouts.json", _layouts_json())
    _write_text(project_root / "data" / "maps" / "map_groups.json", _map_groups_json())
    _write_text(project_root / "data" / "maps" / MAP_BARE_NAME / "map.json", _map_json())

    # Primary tileset — 6 metatiles, ids 0..5: WATER..HOUSE_WALL.
    primary_metatiles = [
        _solid_metatile(palette_num=0),  # WATER
        _solid_metatile(palette_num=1),  # SAND
        _solid_metatile(palette_num=2),  # GRASS
        _solid_metatile(palette_num=3),  # PATH
        _solid_metatile(palette_num=4),  # TREE
        _solid_metatile(palette_num=5),  # HOUSE_WALL
    ]
    _write_tileset(
        project_root,
        kind="primary",
        name="primary_demo",
        metatile_payload=primary_metatiles,
    )

    # Secondary tileset — 2 metatiles, combined ids 512 and 513.
    secondary_metatiles = [
        _solid_metatile(palette_num=6),  # HOUSE_ROOF
        _solid_metatile(palette_num=7),  # SIGN
    ]
    _write_tileset(
        project_root,
        kind="secondary",
        name="secondary_demo",
        metatile_payload=secondary_metatiles,
    )

    # map.bin filled with GRASS, border.bin filled with TREE.
    _write_bytes(
        project_root / "data" / "layouts" / MAP_BARE_NAME / "map.bin",
        _pack_map_bin(MAP_WIDTH, MAP_HEIGHT, fill_metatile_id=GRASS),
    )
    _write_bytes(
        project_root / "data" / "layouts" / MAP_BARE_NAME / "border.bin",
        _pack_map_bin(2, 2, fill_metatile_id=TREE),
    )


# --------------------------------------------------------------------------
# Demo loop — the part a real MCP session reproduces tool-for-tool
# --------------------------------------------------------------------------


def _save_render(project_path: str, out_png: Path, *, label: str) -> None:
    """Call render_map and write the returned PNG bytes to disk."""
    result = render_tools.render_map(project_path, MAP_ID, scale=4)
    block = result.content[0]
    assert block.type == "image"
    assert block.mimeType == "image/png"
    import base64

    png_bytes = base64.b64decode(block.data)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_png.write_bytes(png_bytes)
    rel = out_png.relative_to(Path.cwd()) if out_png.is_absolute() else out_png
    print(f"  rendered {label}: {rel} ({len(png_bytes)} bytes)")


def iter1_draft(project_path: str) -> None:
    """A weak first draft: empty grass canvas + one stranded house tile."""
    print("\n--- Iteration 1: draft ---")
    print("  Drop a single house tile at (4, 3). Otherwise leave the map blank.")
    map_tools.paint_metatile(project_path, MAP_ID, 4, 3, HOUSE_WALL)


# What ``map-design-critic`` would say after seeing iter 1. In a real
# session this is invoked via ``Task(subagent_type="map-design-critic",
# prompt=..., attachments=[iter1.png])`` and its actual output guides
# the next paint pass. The narrative here is illustrative only.
ITER1_CRITIQUE = """\
map-design-critic — iter 1 (illustrative)

  Score: 7 / 36

  Findings (highest impact first):
  1. No coastal feature.       Brief says "coastal town" but the map has
                               no water. Add a beach + sea band along an edge.
  2. No tile variety.          5 out of 6 metatiles unused. A Gen 3 map
                               averages 4-6 distinct biomes per screen.
  3. No path geometry.         The lone house is stranded — no connecting
                               path, no walkable approach.
  4. Buildings = 1.            Towns need at least 2 buildings to read
                               as a settlement (Center + Mart at minimum).
  5. Bare borders.             Top edge has no trees or natural framing.
"""


def iter2_revision(project_path: str) -> None:
    """Apply the top fixes from the critique: coastline, path, trees, second house, signpost."""
    print("\n--- Iteration 2: applying critic's top 5 fixes ---")

    # Fix #1 + #2: coastline + tile variety. Bottom row = water; row above = sand.
    print("  Coastline: water along the south edge, sand strip above it.")
    map_tools.paint_rectangle(project_path, MAP_ID, 0, 5, 7, 5, WATER)
    map_tools.paint_rectangle(project_path, MAP_ID, 0, 4, 7, 4, SAND)

    # Fix #5: tree-line framing the north edge.
    print("  Tree-line framing the north edge.")
    map_tools.paint_rectangle(project_path, MAP_ID, 0, 0, 7, 0, TREE)

    # Fix #3: a path running south from the trees down to the beach.
    print("  Path running N-S through the middle of town.")
    map_tools.paint_rectangle(project_path, MAP_ID, 3, 1, 3, 3, PATH)

    # Fix #4: a second building plus the original house gets a roof tile.
    # House A (existing wall stays at (4, 3); add roof at (4, 2)).
    print("  Two buildings: existing house gains a roof; a second house to the west.")
    map_tools.paint_metatile(project_path, MAP_ID, 4, 2, HOUSE_ROOF)
    # House B at (1, 2)-(1, 3): roof on top, wall on bottom.
    map_tools.paint_metatile(project_path, MAP_ID, 1, 2, HOUSE_ROOF)
    map_tools.paint_metatile(project_path, MAP_ID, 1, 3, HOUSE_WALL)

    # Touch: a signpost beside the path, between the two houses.
    print("  Signpost beside the path.")
    map_tools.paint_metatile(project_path, MAP_ID, 2, 3, SIGN)


ITER2_CRITIQUE = """\
map-design-critic — iter 2 (illustrative)

  Score: 21 / 36   (delta: +14)

  Resolved: coastal feature, tile variety, path geometry, two buildings,
            framed north edge.

  Remaining (lower priority, deferred to iter 3+):
  - Houses lack horizontal extent (1 tile wide reads as a hut, not a
    "building"). Widen each to 2 tiles.
  - Path doesn't terminate cleanly at the beach; consider a sand-path
    transition tile.
  - Signpost is mid-path; relocate to the path shoulder.
"""


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    here = Path(__file__).resolve().parent
    project_root = here / PROJECT_DIR_NAME
    renders_dir = here / "renders"

    print(f"Bootstrapping synthetic project under {project_root.relative_to(here)}/")
    bootstrap_project(project_root)
    project_path = str(project_root)

    iter1_draft(project_path)
    _save_render(project_path, renders_dir / "iter1.png", label="iter 1")
    print(ITER1_CRITIQUE)

    iter2_revision(project_path)
    _save_render(project_path, renders_dir / "iter2.png", label="iter 2")
    print(ITER2_CRITIQUE)

    print("Done. Inspect renders/iter1.png and renders/iter2.png to see the loop output.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
