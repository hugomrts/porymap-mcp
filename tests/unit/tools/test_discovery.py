"""Tests for ``porymap_mcp.tools.discovery``.

Every test builds a tiny on-disk project under ``tmp_path`` from inline
fixtures, then invokes each tool's underlying body function directly
(the ``register()`` path is exercised by a single smoke test at the end).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.errors import MapNotFoundError, ProjectError, UnsupportedBaseGameError
from porymap_mcp.tools import discovery

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
      "width": 20,
      "height": 20,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_LittlerootTown",
      "border_filepath": "data/layouts/LittlerootTown/border.bin",
      "blockdata_filepath": "data/layouts/LittlerootTown/map.bin"
    },
    {
      "id": "LAYOUT_ROUTE_101",
      "name": "Route101_Layout",
      "width": 30,
      "height": 20,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_Route101",
      "border_filepath": "data/layouts/Route101/border.bin",
      "blockdata_filepath": "data/layouts/Route101/map.bin"
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
    "LittlerootTown",
    "Route101",
    "Route101_TownGuide"
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
  "allow_cycling": true,
  "allow_escaping": false,
  "allow_running": true,
  "show_map_name": true,
  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
  "connections": [
    {
      "map": "MAP_ROUTE101",
      "offset": 0,
      "direction": "up"
    }
  ],
  "object_events": [
    {
      "graphics_id": "OBJ_EVENT_GFX_MOM",
      "x": 8,
      "y": 5,
      "elevation": 3,
      "movement_type": "MOVEMENT_TYPE_LOOK_AROUND",
      "movement_range_x": 0,
      "movement_range_y": 0,
      "trainer_type": "TRAINER_TYPE_NONE",
      "trainer_sight_or_berry_tree_id": "0",
      "script": "LittlerootTown_EventScript_Mom",
      "flag": "FLAG_HIDE_LITTLEROOT_MOM"
    }
  ],
  "warp_events": [
    {
      "x": 2,
      "y": 3,
      "elevation": 0,
      "dest_map": "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F",
      "dest_warp_id": "0"
    },
    {
      "x": 14,
      "y": 8,
      "elevation": 0,
      "dest_map": "MAP_LITTLEROOT_TOWN_MAYS_HOUSE_1F",
      "dest_warp_id": "0"
    }
  ],
  "coord_events": [],
  "bg_events": [
    {
      "type": "sign",
      "x": 6,
      "y": 4,
      "elevation": 0,
      "player_facing_dir": "BG_EVENT_PLAYER_FACING_ANY",
      "script": "LittlerootTown_EventScript_TownSign"
    }
  ]
}
"""

ROUTE101_MAP_JSON = """\
{
  "id": "MAP_ROUTE101",
  "name": "Route101",
  "layout": "LAYOUT_ROUTE_101",
  "music": "MUS_ROUTE101",
  "region_map_section": "MAPSEC_ROUTE_101",
  "requires_flash": false,
  "weather": "WEATHER_SUNNY",
  "map_type": "MAP_TYPE_ROUTE",
  "show_map_name": true,
  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
  "connections": null,
  "object_events": [],
  "warp_events": [],
  "coord_events": [],
  "bg_events": []
}
"""

# A map that inherits its events from Route101 (Porymap omits the four
# event arrays entirely when shared_events_map is set).
ROUTE101_GUIDE_MAP_JSON = """\
{
  "id": "MAP_ROUTE101_TOWN_GUIDE",
  "name": "Route101_TownGuide",
  "layout": "LAYOUT_ROUTE_101",
  "music": "MUS_ROUTE101",
  "region_map_section": "MAPSEC_ROUTE_101",
  "requires_flash": false,
  "weather": "WEATHER_SUNNY",
  "map_type": "MAP_TYPE_ROUTE",
  "show_map_name": true,
  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
  "connections": null,
  "shared_events_map": "MAP_ROUTE101",
  "shared_scripts_map": "MAP_ROUTE101"
}
"""


def _build_project(root: Path, *, with_tilesets: bool = True) -> Path:
    """Lay down a minimal pokeemerald-shaped project at ``root``. Returns ``root``."""
    _write(root / "porymap.project.cfg", MIN_CFG)
    _write(root / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(root / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
    _write(root / "data" / "maps" / "LittlerootTown" / "map.json", LITTLEROOT_MAP_JSON)
    _write(root / "data" / "maps" / "Route101" / "map.json", ROUTE101_MAP_JSON)
    _write(
        root / "data" / "maps" / "Route101_TownGuide" / "map.json",
        ROUTE101_GUIDE_MAP_JSON,
    )
    # map.bin / border.bin existence is irrelevant for discovery tools, but
    # keep the project shape consistent in case a test reaches for them.
    _write_bytes(
        root / "data" / "layouts" / "LittlerootTown" / "map.bin",
        b"\x00\x00" * (20 * 20),
    )
    _write_bytes(
        root / "data" / "layouts" / "LittlerootTown" / "border.bin",
        b"\x00\x00" * 4,
    )
    _write_bytes(
        root / "data" / "layouts" / "Route101" / "map.bin",
        b"\x00\x00" * (30 * 20),
    )
    _write_bytes(root / "data" / "layouts" / "Route101" / "border.bin", b"\x00\x00" * 4)
    if with_tilesets:
        _add_tileset(root, "primary", "general", metatile_count=8)
        _add_tileset(root, "secondary", "littleroot_town", metatile_count=4)
    return root


def _add_tileset(root: Path, kind: str, name: str, *, metatile_count: int) -> None:
    """Create a tileset directory with a metatiles.bin sized for the
    file-size-derived count (16 bytes per metatile, per ADR-0005)."""
    directory = root / "data" / "tilesets" / kind / name
    directory.mkdir(parents=True)
    (directory / "tiles.png").touch()
    (directory / "metatiles.bin").write_bytes(b"\x00" * (metatile_count * 16))
    (directory / "metatile_attributes.bin").touch()
    (directory / "palettes").mkdir()


# --- get_project_info -----------------------------------------------------


class TestGetProjectInfo:
    def test_happy_path(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.get_project_info(str(tmp_path))
        assert result["base_game_version"] == "pokeemerald"
        assert result["map_count"] == 3
        assert result["layout_count"] == 2
        assert result["tileset_count"] == 2
        assert result["primary_tileset_count"] == 1
        assert result["secondary_tileset_count"] == 1
        assert result["project_path"] == tmp_path.resolve().as_posix()
        assert result["config_path"].endswith("porymap.project.cfg")
        assert "pokeemerald" in result["summary"]

    def test_user_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _build_project(tmp_path)
        # Force ~ to expand to tmp_path so we can test the expanduser path.
        monkeypatch.setenv("HOME", str(tmp_path))
        result = discovery.get_project_info("~")
        assert result["project_path"] == tmp_path.resolve().as_posix()

    def test_missing_project_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError):
            discovery.get_project_info(str(tmp_path / "does_not_exist"))

    def test_unsupported_base_game(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        _write(tmp_path / "porymap.project.cfg", "base_game_version=pokecrystal\n")
        with pytest.raises(UnsupportedBaseGameError):
            discovery.get_project_info(str(tmp_path))


# --- list_maps ------------------------------------------------------------


class TestListMaps:
    def test_canonical_order(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_maps(str(tmp_path))
        names = [m["name"] for m in result["maps"]]
        assert names == ["MAP_LITTLEROOT_TOWN", "MAP_ROUTE101", "MAP_ROUTE101_TOWN_GUIDE"]

    def test_includes_group_and_dimensions(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_maps(str(tmp_path))
        littleroot = next(m for m in result["maps"] if m["name"] == "MAP_LITTLEROOT_TOWN")
        assert littleroot["group"] == "gMapGroup_TownsAndRoutes"
        assert littleroot["layout_id"] == "LAYOUT_LITTLEROOT_TOWN"
        assert littleroot["dimensions"] == {"width": 20, "height": 20}

    def test_summary_reports_counts(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_maps(str(tmp_path))
        assert "3 maps" in result["summary"]
        assert "1 group" in result["summary"]

    def test_orphan_layout_id_yields_null_dimensions(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Rewrite LittlerootTown's map.json to point at a layout id that
        # is not in layouts.json — list_maps should swallow the lookup
        # failure and emit ``dimensions: null``.
        bad = LITTLEROOT_MAP_JSON.replace(
            '"layout": "LAYOUT_LITTLEROOT_TOWN"',
            '"layout": "LAYOUT_NONEXISTENT"',
        )
        _write(tmp_path / "data" / "maps" / "LittlerootTown" / "map.json", bad)
        result = discovery.list_maps(str(tmp_path))
        littleroot = next(m for m in result["maps"] if m["name"] == "MAP_LITTLEROOT_TOWN")
        assert littleroot["layout_id"] == "LAYOUT_NONEXISTENT"
        assert littleroot["dimensions"] is None


# --- get_map_info ---------------------------------------------------------


class TestGetMapInfo:
    def test_full_metadata(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.get_map_info(str(tmp_path), "MAP_LITTLEROOT_TOWN")
        assert result["map_name"] == "MAP_LITTLEROOT_TOWN"
        assert result["group"] == "gMapGroup_TownsAndRoutes"
        assert result["dimensions"] == {"width": 20, "height": 20}
        assert result["border_dimensions"] == {"width": 2, "height": 2}
        assert result["layout"]["id"] == "LAYOUT_LITTLEROOT_TOWN"
        assert result["layout"]["primary_tileset"] == "gTileset_General"
        assert result["layout"]["secondary_tileset"] == "gTileset_LittlerootTown"
        assert result["event_counts"] == {
            "object_events": 1,
            "warp_events": 2,
            "coord_events": 0,
            "bg_events": 1,
            "total": 4,
        }
        assert result["connection_count"] == 1
        assert result["inherits_events_from"] is None
        assert result["inherits_scripts_from"] is None

    def test_header_block(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.get_map_info(str(tmp_path), "MAP_LITTLEROOT_TOWN")
        header = result["header"]
        assert header["music"] == "MUS_LITTLEROOT"
        assert header["allow_cycling"] is True
        assert header["allow_escaping"] is False
        assert header["floor_number"] is None

    def test_inherited_map(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.get_map_info(str(tmp_path), "MAP_ROUTE101_TOWN_GUIDE")
        assert result["inherits_events_from"] == "MAP_ROUTE101"
        assert result["inherits_scripts_from"] == "MAP_ROUTE101"
        # Inherited maps have zero local events.
        assert result["event_counts"]["total"] == 0

    def test_unknown_map_raises(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(MapNotFoundError):
            discovery.get_map_info(str(tmp_path), "MAP_NOWHERE")


# --- list_tilesets --------------------------------------------------------


class TestListTilesets:
    def test_lists_primary_and_secondary(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_tilesets(str(tmp_path))
        assert len(result["tilesets"]) == 2
        kinds = {t["kind"] for t in result["tilesets"]}
        assert kinds == {"primary", "secondary"}

    def test_metatile_count_from_file_size(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_tilesets(str(tmp_path))
        general = next(t for t in result["tilesets"] if t["name"] == "general")
        littleroot = next(t for t in result["tilesets"] if t["name"] == "littleroot_town")
        assert general["metatile_count"] == 8
        assert littleroot["metatile_count"] == 4

    def test_missing_metatiles_bin_yields_null(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Remove metatiles.bin from the primary tileset.
        (tmp_path / "data" / "tilesets" / "primary" / "general" / "metatiles.bin").unlink()
        result = discovery.list_tilesets(str(tmp_path))
        general = next(t for t in result["tilesets"] if t["name"] == "general")
        assert general["metatile_count"] is None

    def test_tileset_shape(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_tilesets(str(tmp_path))
        general = next(t for t in result["tilesets"] if t["name"] == "general")
        assert general["c_label"] == "gTileset_General"
        assert general["c_label_unverified"] is True
        assert general["is_primary"] is True
        assert general["paths"]["metatiles"] == "data/tilesets/primary/general/metatiles.bin"

    def test_empty_project_yields_empty_list(self, tmp_path: Path) -> None:
        _build_project(tmp_path, with_tilesets=False)
        result = discovery.list_tilesets(str(tmp_path))
        assert result["tilesets"] == []
        assert "0 tileset" in result["summary"]


# --- list_metatiles -------------------------------------------------------


class TestListMetatiles:
    def test_stub_mode(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_metatiles(str(tmp_path), "general")
        assert result["tileset_name"] == "general"
        assert result["kind"] == "primary"
        assert result["c_label"] == "gTileset_General"
        assert result["metatile_count"] == 8
        assert result["metatiles"] == []

    def test_unknown_tileset_raises(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="tileset not found by name"):
            discovery.list_metatiles(str(tmp_path), "nope")


# --- list_prefabs ---------------------------------------------------------


class TestListPrefabs:
    def test_empty_in_v0(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_prefabs(str(tmp_path))
        assert result["prefabs"] == []
        assert "No prefabs" in result["summary"]


# --- list_events ----------------------------------------------------------


class TestListEvents:
    def test_event_ids_assigned(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_events(str(tmp_path), "MAP_LITTLEROOT_TOWN")
        assert result["object_events"][0]["_event_id"] == "object_events:0"
        assert result["warp_events"][0]["_event_id"] == "warp_events:0"
        assert result["warp_events"][1]["_event_id"] == "warp_events:1"
        assert result["bg_events"][0]["_event_id"] == "bg_events:0"

    def test_raw_dict_round_trips(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_events(str(tmp_path), "MAP_LITTLEROOT_TOWN")
        mom = result["object_events"][0]
        assert mom["graphics_id"] == "OBJ_EVENT_GFX_MOM"
        assert mom["flag"] == "FLAG_HIDE_LITTLEROOT_MOM"

    def test_inherited_events(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_events(str(tmp_path), "MAP_ROUTE101_TOWN_GUIDE")
        assert result["inherits_events_from"] == "MAP_ROUTE101"
        assert result["object_events"] == []
        assert result["warp_events"] == []
        assert result["coord_events"] == []
        assert result["bg_events"] == []

    def test_unknown_map(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(MapNotFoundError):
            discovery.list_events(str(tmp_path), "MAP_NOWHERE")


# --- Registration smoke test ----------------------------------------------


class TestRegister:
    def test_build_server_registers_all_seven(self) -> None:
        import asyncio

        from porymap_mcp.server import build_server

        mcp = build_server()
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert names == {
            "get_project_info",
            "list_maps",
            "get_map_info",
            "list_tilesets",
            "list_metatiles",
            "list_prefabs",
            "list_events",
        }
