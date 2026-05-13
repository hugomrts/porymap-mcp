"""Tests for ``paint_prefab`` + the updated ``list_prefabs``."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from porymap_mcp.errors import CoordinatesOutOfBoundsError, ProjectError
from porymap_mcp.parsers import mapbin
from porymap_mcp.prefabs import LIBRARY, Prefab, PrefabTile
from porymap_mcp.tools import discovery, maps

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
      "id": "LAYOUT_X",
      "name": "X_Layout",
      "width": 6,
      "height": 6,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_LittlerootTown",
      "border_filepath": "data/layouts/X/border.bin",
      "blockdata_filepath": "data/layouts/X/map.bin"
    }
  ]
}
"""

MAP_GROUPS_JSON = """\
{
  "group_order": [
    "g"
  ],
  "g": [
    "X"
  ]
}
"""

X_MAP_JSON = """\
{
  "id": "MAP_X",
  "name": "X",
  "layout": "LAYOUT_X",
  "music": "MUS_NONE",
  "region_map_section": "MAPSEC_NONE",
  "requires_flash": false,
  "weather": "WEATHER_NONE",
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
    _write(root / "porymap.project.cfg", MIN_CFG)
    _write(root / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(root / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
    _write(root / "data" / "maps" / "X" / "map.json", X_MAP_JSON)
    _write_bytes(root / "data" / "layouts" / "X" / "map.bin", b"\x00\x00" * 36)
    _write_bytes(root / "data" / "layouts" / "X" / "border.bin", b"\x00\x00" * 4)
    return root


# --- list_prefabs ---------------------------------------------------------


class TestListPrefabs:
    def test_returns_library_entries(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_prefabs(str(tmp_path))
        names = {p["name"] for p in result["prefabs"]}
        assert names == set(LIBRARY.keys())

    def test_shape(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = discovery.list_prefabs(str(tmp_path))
        entry = next(p for p in result["prefabs"] if p["name"] == "house_small")
        assert entry["width"] == 3
        assert entry["height"] == 3
        assert entry["tileset_requirements"] == {"primary": None, "secondary": None}


# --- paint_prefab ---------------------------------------------------------


class TestPaintPrefab:
    def test_stamps_house_small(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = maps.paint_prefab(str(tmp_path), "MAP_X", "house_small", x=1, y=1)
        assert result["dimensions"] == {"width": 3, "height": 3}
        assert result["tiles_changed"] == 9
        data = (tmp_path / "data/layouts/X/map.bin").read_bytes()
        layout = mapbin.read(data, width=6, height=6)
        # Doorway tile at (2, 3) in the map = prefab(1, 2): walkable.
        assert layout.get(2, 3).collision == 0
        # Cells outside the prefab footprint untouched.
        assert layout.get(0, 0).metatile_id == 0

    def test_unknown_prefab(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="not found"):
            maps.paint_prefab(str(tmp_path), "MAP_X", "nonexistent", 0, 0)

    def test_out_of_bounds(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # house_small is 3x3; placing anchor at (4, 4) on a 6x6 map -> 6, 6 OOB.
        with pytest.raises(CoordinatesOutOfBoundsError):
            maps.paint_prefab(str(tmp_path), "MAP_X", "house_small", 4, 4)

    def test_tileset_mismatch(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Patch the library to inject a prefab with a strict requirement.
        strict = replace(
            LIBRARY["single_tree"],
            name="strict_tree",
            primary_tileset="gTileset_NotARealTileset",
        )
        LIBRARY["strict_tree"] = strict
        try:
            with pytest.raises(ProjectError, match="tileset mismatch"):
                maps.paint_prefab(str(tmp_path), "MAP_X", "strict_tree", 0, 0)
        finally:
            del LIBRARY["strict_tree"]

    def test_idempotent_no_op(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        maps.paint_prefab(str(tmp_path), "MAP_X", "single_tree", 2, 2)
        result = maps.paint_prefab(str(tmp_path), "MAP_X", "single_tree", 2, 2)
        assert result["tiles_changed"] == 0
        assert result["files_modified"] == []

    def test_prefab_dataclasses_are_frozen(self) -> None:
        # Sanity: the Prefab type is immutable so library entries can't be
        # corrupted by accident.
        from dataclasses import FrozenInstanceError

        tree = LIBRARY["single_tree"]
        with pytest.raises(FrozenInstanceError):
            tree.name = "other"  # type: ignore[misc]
        cell = PrefabTile(metatile_id=0, collision=0, elevation=0)
        with pytest.raises(FrozenInstanceError):
            cell.metatile_id = 1  # type: ignore[misc]
        # Smoke: Prefab type is importable.
        assert Prefab is not None
