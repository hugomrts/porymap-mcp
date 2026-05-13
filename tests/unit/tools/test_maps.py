"""Tests for ``porymap_mcp.tools.maps`` (paint_*, flood_fill, set_border,
create_map, resize_map).

Builds a tiny on-disk project under ``tmp_path`` and exercises each
mutation tool's body function directly. Idempotence (CC-1) and
``files_modified`` (CC-3) are verified per tool.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.errors import CoordinatesOutOfBoundsError, MapNotFoundError, ProjectError
from porymap_mcp.parsers import mapbin
from porymap_mcp.tools import maps

# --- Fixture helpers ------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


MIN_CFG = "base_game_version=pokeemerald\n"

LAYOUTS_JSON = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_LITTLEROOT_TOWN",
      "name": "LittlerootTown_Layout",
      "width": 4,
      "height": 3,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_LittlerootTown",
      "border_filepath": "data/layouts/LittlerootTown/border.bin",
      "blockdata_filepath": "data/layouts/LittlerootTown/map.bin"
    }
  ]
}
"""

MAP_GROUPS_JSON = """\
{
  "group_order": [
    "gMapGroup_TownsAndRoutes"
  ],
  "gMapGroup_TownsAndRoutes": [
    "LittlerootTown"
  ]
}
"""

LITTLEROOT_MAP_JSON = """\
{
  "id": "MAP_LITTLEROOT_TOWN",
  "name": "LittlerootTown",
  "layout": "LAYOUT_LITTLEROOT_TOWN",
  "music": "MUS_LITTLEROOT",
  "region_map_section": "MAPSEC_LITTLEROOT_TOWN",
  "requires_flash": false,
  "weather": "WEATHER_SUNNY",
  "map_type": "MAP_TYPE_TOWN",
  "show_map_name": true,
  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
  "connections": null,
  "object_events": [],
  "warp_events": [],
  "coord_events": [],
  "bg_events": []
}
"""


def _build_project(root: Path) -> Path:
    """Lay down a minimal pokeemerald project at ``root``. Returns ``root``.

    4x3 map.bin pre-filled so that (0,0).metatile_id == 1, (1,0) == 2, etc.
    so tests can rely on known previous values.
    """
    _write(root / "porymap.project.cfg", MIN_CFG)
    _write(root / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(root / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
    _write(root / "data" / "maps" / "LittlerootTown" / "map.json", LITTLEROOT_MAP_JSON)
    # 4x3 map.bin: tile (x, y) = packed(metatile_id=x+y*4+1, collision=0, elevation=0)
    map_bin_bytes = bytearray()
    for y in range(3):
        for x in range(4):
            metatile_id = x + y * 4 + 1
            map_bin_bytes.extend(metatile_id.to_bytes(2, "little"))
    _write_bytes(root / "data" / "layouts" / "LittlerootTown" / "map.bin", bytes(map_bin_bytes))
    # 2x2 border, all zero.
    _write_bytes(
        root / "data" / "layouts" / "LittlerootTown" / "border.bin",
        b"\x00\x00" * 4,
    )
    return root


# --- paint_metatile -------------------------------------------------------


class TestPaintMetatile:
    def test_paints_and_returns_previous(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.paint_metatile(
            str(tmp_path), "MAP_LITTLEROOT_TOWN", x=1, y=0, metatile_id=0x42
        )
        assert result["previous"]["metatile_id"] == 2
        assert result["metatile_id"] == 0x42
        assert result["files_modified"] == ["data/layouts/LittlerootTown/map.bin"]
        # On-disk verification.
        data = (tmp_path / "data/layouts/LittlerootTown/map.bin").read_bytes()
        layout = mapbin.read(data, width=4, height=3)
        assert layout.get(1, 0).metatile_id == 0x42

    def test_preserves_collision_and_elevation_when_none(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # First, set collision=2 and elevation=5 at (0, 0).
        maps.paint_metatile(
            str(tmp_path),
            "MAP_LITTLEROOT_TOWN",
            x=0,
            y=0,
            metatile_id=1,
            collision=2,
            elevation=5,
        )
        # Now repaint metatile only — collision/elevation preserved.
        result = maps.paint_metatile(
            str(tmp_path), "MAP_LITTLEROOT_TOWN", x=0, y=0, metatile_id=0x99
        )
        assert result["collision"] == 2
        assert result["elevation"] == 5
        assert "preserved collision=2, elevation=5" in result["summary"]

    def test_idempotent_no_op(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Original value at (1, 0) is 2.
        result = maps.paint_metatile(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=1, y=0, metatile_id=2)
        assert result["files_modified"] == []
        assert "no change" in result["summary"]

    def test_out_of_bounds(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(CoordinatesOutOfBoundsError):
            maps.paint_metatile(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=99, y=0, metatile_id=1)

    def test_invalid_metatile_id(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="metatile_id"):
            maps.paint_metatile(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=0, y=0, metatile_id=0x500)

    def test_invalid_collision(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="collision"):
            maps.paint_metatile(
                str(tmp_path),
                "MAP_LITTLEROOT_TOWN",
                x=0,
                y=0,
                metatile_id=1,
                collision=99,
            )

    def test_unknown_map(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(MapNotFoundError):
            maps.paint_metatile(str(tmp_path), "MAP_NOWHERE", x=0, y=0, metatile_id=1)


# --- paint_rectangle ------------------------------------------------------


class TestPaintRectangle:
    def test_paints_inclusive_rectangle(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.paint_rectangle(
            str(tmp_path),
            "MAP_LITTLEROOT_TOWN",
            x1=1,
            y1=0,
            x2=2,
            y2=1,
            metatile_id=0x100,
        )
        # 2x2 area = 4 tiles, all initially different from 0x100.
        assert result["tile_count"] == 4
        assert result["tiles_changed"] == 4
        data = (tmp_path / "data/layouts/LittlerootTown/map.bin").read_bytes()
        layout = mapbin.read(data, width=4, height=3)
        for x in (1, 2):
            for y in (0, 1):
                assert layout.get(x, y).metatile_id == 0x100

    def test_reversed_corners_raise(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="top-left, bottom-right"):
            maps.paint_rectangle(
                str(tmp_path),
                "MAP_LITTLEROOT_TOWN",
                x1=3,
                y1=2,
                x2=1,
                y2=0,
                metatile_id=1,
            )

    def test_idempotent_no_op(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        maps.paint_rectangle(
            str(tmp_path),
            "MAP_LITTLEROOT_TOWN",
            x1=0,
            y1=0,
            x2=3,
            y2=2,
            metatile_id=0x77,
        )
        # Second call must be a no-op.
        result = maps.paint_rectangle(
            str(tmp_path),
            "MAP_LITTLEROOT_TOWN",
            x1=0,
            y1=0,
            x2=3,
            y2=2,
            metatile_id=0x77,
        )
        assert result["tiles_changed"] == 0
        assert result["files_modified"] == []

    def test_partial_overlap_reports_changed_count(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Pre-set one of the four tiles to the target id so only 3 change.
        maps.paint_metatile(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=1, y=0, metatile_id=0x33)
        result = maps.paint_rectangle(
            str(tmp_path),
            "MAP_LITTLEROOT_TOWN",
            x1=1,
            y1=0,
            x2=2,
            y2=1,
            metatile_id=0x33,
        )
        assert result["tile_count"] == 4
        assert result["tiles_changed"] == 3


# --- flood_fill -----------------------------------------------------------


class TestFloodFill:
    def test_fills_uniform_area(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Fill the whole map with metatile 5 first.
        maps.paint_rectangle(
            str(tmp_path),
            "MAP_LITTLEROOT_TOWN",
            x1=0,
            y1=0,
            x2=3,
            y2=2,
            metatile_id=5,
        )
        result = maps.flood_fill(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=0, y=0, metatile_id=9)
        assert result["tiles_changed"] == 12  # 4 * 3
        assert result["source_metatile_id"] == 5
        assert result["target_metatile_id"] == 9

    def test_4_connected_not_diagonal(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Set up a 4x3 like:
        #   1 2 1 1
        #   2 1 2 2
        #   1 2 1 1
        # Seed at (0, 0) with metatile_id=1 -> floods only the diag-disconnected
        # corner cell; 4-connected can't reach the rest because every neighbor
        # is metatile 2.
        for y in range(3):
            for x in range(4):
                # Checkerboard-ish pattern using 1s and 2s.
                v = 1 if (x + y) % 2 == 0 else 2
                maps.paint_metatile(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=x, y=y, metatile_id=v)
        result = maps.flood_fill(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=0, y=0, metatile_id=7)
        # Only (0, 0) is reachable from itself under 4-connectivity in a
        # strict checkerboard — diagonal neighbors are not 4-connected.
        assert result["tiles_changed"] == 1

    def test_no_op_when_seed_matches(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # (0, 0) has metatile_id=1 by construction.
        result = maps.flood_fill(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=0, y=0, metatile_id=1)
        assert result["tiles_changed"] == 0
        assert result["files_modified"] == []

    def test_out_of_bounds(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(CoordinatesOutOfBoundsError):
            maps.flood_fill(str(tmp_path), "MAP_LITTLEROOT_TOWN", x=4, y=0, metatile_id=1)


# --- set_border -----------------------------------------------------------


class TestSetBorder:
    def test_sets_border_grid(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        new_grid = [[0x10, 0x11], [0x12, 0x13]]
        result = maps.set_border(str(tmp_path), "MAP_LITTLEROOT_TOWN", new_grid)
        assert result["cells_changed"] == 4
        # Verify on disk.
        data = (tmp_path / "data/layouts/LittlerootTown/border.bin").read_bytes()
        border = mapbin.read(data, width=2, height=2)
        assert border.get(0, 0).metatile_id == 0x10
        assert border.get(1, 0).metatile_id == 0x11
        assert border.get(0, 1).metatile_id == 0x12
        assert border.get(1, 1).metatile_id == 0x13

    def test_shape_mismatch(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # 3x2 grid instead of 2x2.
        with pytest.raises(ProjectError, match="border dimension mismatch"):
            maps.set_border(
                str(tmp_path),
                "MAP_LITTLEROOT_TOWN",
                [[0, 0, 0], [0, 0, 0]],
            )

    def test_idempotent_no_op(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        maps.set_border(str(tmp_path), "MAP_LITTLEROOT_TOWN", [[1, 1], [1, 1]])
        result = maps.set_border(str(tmp_path), "MAP_LITTLEROOT_TOWN", [[1, 1], [1, 1]])
        assert result["cells_changed"] == 0
        assert result["files_modified"] == []


# --- create_map -----------------------------------------------------------


class TestCreateMap:
    def test_creates_in_existing_group(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.create_map(
            str(tmp_path),
            name="NewTown",
            group="gMapGroup_TownsAndRoutes",
            width=10,
            height=10,
            primary_tileset="gTileset_General",
            secondary_tileset="gTileset_LittlerootTown",
        )
        assert result["map_name"] == "MAP_NEW_TOWN"
        assert result["layout_id"] == "LAYOUT_NEW_TOWN"
        assert result["group_created"] is False
        assert len(result["files_modified"]) == 5
        assert (tmp_path / "data/maps/NewTown/map.json").is_file()
        assert (tmp_path / "data/layouts/NewTown/map.bin").is_file()
        assert (tmp_path / "data/layouts/NewTown/border.bin").is_file()

    def test_creates_new_group(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.create_map(
            str(tmp_path),
            name="OtherTown",
            group="gMapGroup_NewLand",
            width=5,
            height=5,
            primary_tileset="gTileset_General",
            secondary_tileset="gTileset_OtherTown",
        )
        assert result["group_created"] is True
        # Verify group appears in map_groups.json.
        text = (tmp_path / "data/maps/map_groups.json").read_text(encoding="utf-8")
        assert "gMapGroup_NewLand" in text
        assert '"OtherTown"' in text

    def test_rejects_map_constant_as_name(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="bare PascalCase"):
            maps.create_map(
                str(tmp_path),
                name="MAP_NEWTOWN",
                group="gMapGroup_TownsAndRoutes",
                width=5,
                height=5,
                primary_tileset="gTileset_General",
                secondary_tileset="gTileset_LittlerootTown",
            )

    def test_rejects_snake_case_name(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="without underscores"):
            maps.create_map(
                str(tmp_path),
                name="New_Town",
                group="gMapGroup_TownsAndRoutes",
                width=5,
                height=5,
                primary_tileset="gTileset_General",
                secondary_tileset="gTileset_LittlerootTown",
            )

    def test_rejects_duplicate_layout(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="layout id"):
            maps.create_map(
                str(tmp_path),
                name="LittlerootTown",
                group="gMapGroup_TownsAndRoutes",
                width=5,
                height=5,
                primary_tileset="gTileset_General",
                secondary_tileset="gTileset_LittlerootTown",
            )

    def test_rejects_invalid_dimensions(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="positive"):
            maps.create_map(
                str(tmp_path),
                name="NewTown",
                group="gMapGroup_TownsAndRoutes",
                width=0,
                height=5,
                primary_tileset="gTileset_General",
                secondary_tileset="gTileset_LittlerootTown",
            )

    def test_header_overrides_apply(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        maps.create_map(
            str(tmp_path),
            name="RouteTwentyTwo",
            group="gMapGroup_TownsAndRoutes",
            width=10,
            height=5,
            primary_tileset="gTileset_General",
            secondary_tileset="gTileset_Route22",
            header_overrides={
                "map_type": "MAP_TYPE_ROUTE",
                "music": "MUS_ROUTE22",
            },
        )
        text = (tmp_path / "data/maps/RouteTwentyTwo/map.json").read_text(encoding="utf-8")
        assert '"map_type": "MAP_TYPE_ROUTE"' in text
        assert '"music": "MUS_ROUTE22"' in text

    def test_fill_metatile_applied(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        maps.create_map(
            str(tmp_path),
            name="FilledTown",
            group="gMapGroup_TownsAndRoutes",
            width=3,
            height=2,
            primary_tileset="gTileset_General",
            secondary_tileset="gTileset_X",
            fill_metatile_id=0x42,
        )
        data = (tmp_path / "data/layouts/FilledTown/map.bin").read_bytes()
        layout = mapbin.read(data, width=3, height=2)
        for y in range(2):
            for x in range(3):
                assert layout.get(x, y).metatile_id == 0x42


# --- resize_map -----------------------------------------------------------


class TestResizeMap:
    def test_grows_layout(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.resize_map(str(tmp_path), "MAP_LITTLEROOT_TOWN", new_width=6, new_height=4)
        assert result["previous_dimensions"] == {"width": 4, "height": 3}
        assert result["new_dimensions"] == {"width": 6, "height": 4}
        assert result["cells_added"] == 6 * 4 - 4 * 3
        # Verify dimensions are persisted.
        data = (tmp_path / "data/layouts/LittlerootTown/map.bin").read_bytes()
        layout = mapbin.read(data, width=6, height=4)
        # Existing content preserved at top-left.
        assert layout.get(0, 0).metatile_id == 1
        assert layout.get(3, 2).metatile_id == 12  # last of original
        # New cells filled with default (metatile 0).
        assert layout.get(5, 3).metatile_id == 0

    def test_shrinks_when_no_events(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.resize_map(str(tmp_path), "MAP_LITTLEROOT_TOWN", new_width=2, new_height=2)
        assert result["cells_removed"] == 4 * 3 - 2 * 2
        data = (tmp_path / "data/layouts/LittlerootTown/map.bin").read_bytes()
        layout = mapbin.read(data, width=2, height=2)
        assert layout.get(0, 0).metatile_id == 1
        assert layout.get(1, 1).metatile_id == 6

    def test_shrinks_refuses_when_orphans_events(self, tmp_path: Path) -> None:
        # Patch map.json to add a warp at (3, 2) that would be orphaned.
        _build_project(tmp_path)
        map_json_path = tmp_path / "data/maps/LittlerootTown/map.json"
        text = map_json_path.read_text(encoding="utf-8")
        new_text = text.replace(
            '"warp_events": []',
            '"warp_events": [{"x": 3, "y": 2, "elevation": 0, '
            '"dest_map": "MAP_X", "dest_warp_id": "0"}]',
        )
        map_json_path.write_text(new_text, encoding="utf-8")
        with pytest.raises(ProjectError, match="orphan"):
            maps.resize_map(str(tmp_path), "MAP_LITTLEROOT_TOWN", new_width=2, new_height=2)

    def test_no_op_when_dimensions_unchanged(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.resize_map(str(tmp_path), "MAP_LITTLEROOT_TOWN", new_width=4, new_height=3)
        assert result["files_modified"] == []
        assert result["cells_added"] == 0
        assert result["cells_removed"] == 0

    def test_unsupported_anchor(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="anchor"):
            maps.resize_map(
                str(tmp_path),
                "MAP_LITTLEROOT_TOWN",
                new_width=5,
                new_height=5,
                anchor="center",
            )


# --- Helpers --------------------------------------------------------------


class TestBareToSnake:
    @pytest.mark.parametrize(
        ("bare", "expected"),
        [
            ("LittlerootTown", "LITTLEROOT_TOWN"),
            ("Route101", "ROUTE101"),
            ("BattleHQ", "BATTLE_HQ"),
            ("FortuneCity", "FORTUNE_CITY"),
            ("A", "A"),
            ("AB", "AB"),
        ],
    )
    def test_cases(self, bare: str, expected: str) -> None:
        assert maps._bare_to_snake(bare) == expected
