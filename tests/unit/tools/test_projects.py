"""Tests for ``porymap_mcp.tools.projects`` (register_map, unregister_map)."""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.errors import MapNotFoundError, ProjectError
from porymap_mcp.tools import projects

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
      "id": "LAYOUT_REG",
      "name": "Reg_Layout",
      "width": 1,
      "height": 1,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_X",
      "border_filepath": "data/layouts/Reg/border.bin",
      "blockdata_filepath": "data/layouts/Reg/map.bin"
    }
  ]
}
"""

REGISTERED_MAP_JSON = """\
{
  "id": "MAP_REGISTERED",
  "name": "Reg",
  "layout": "LAYOUT_REG",
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

ORPHAN_MAP_JSON = """\
{
  "id": "MAP_ORPHAN",
  "name": "Orphan",
  "layout": "LAYOUT_REG",
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

MAP_GROUPS_REG_ONLY = """\
{
  "group_order": [
    "gMapGroup_Existing"
  ],
  "gMapGroup_Existing": [
    "Reg"
  ]
}
"""


def _build_project(root: Path, *, with_orphan: bool = True) -> Path:
    _write(root / "porymap.project.cfg", MIN_CFG)
    _write(root / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(root / "data" / "maps" / "map_groups.json", MAP_GROUPS_REG_ONLY)
    _write(root / "data" / "maps" / "Reg" / "map.json", REGISTERED_MAP_JSON)
    _write_bytes(root / "data" / "layouts" / "Reg" / "map.bin", b"\x00\x00")
    _write_bytes(root / "data" / "layouts" / "Reg" / "border.bin", b"\x00\x00" * 4)
    if with_orphan:
        # Map exists on disk but is NOT in map_groups.json.
        _write(root / "data" / "maps" / "Orphan" / "map.json", ORPHAN_MAP_JSON)
        _write_bytes(root / "data" / "layouts" / "Orphan" / "map.bin", b"\x00\x00")
        _write_bytes(root / "data" / "layouts" / "Orphan" / "border.bin", b"\x00\x00" * 4)
    return root


# --- register_map ---------------------------------------------------------


class TestRegisterMap:
    def test_registers_orphan_in_existing_group(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = projects.register_map(str(tmp_path), "MAP_ORPHAN", "gMapGroup_Existing")
        assert result["bare_name"] == "Orphan"
        assert result["group_created"] is False
        assert result["was_already_registered"] is False
        text = (tmp_path / "data/maps/map_groups.json").read_text(encoding="utf-8")
        assert '"Orphan"' in text

    def test_registers_into_new_group(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = projects.register_map(str(tmp_path), "MAP_ORPHAN", "gMapGroup_NewLand")
        assert result["group_created"] is True

    def test_already_registered_is_noop(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = projects.register_map(str(tmp_path), "MAP_REGISTERED", "gMapGroup_Existing")
        assert result["was_already_registered"] is True
        assert result["files_modified"] == []

    def test_registered_in_different_group_raises(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="already registered"):
            projects.register_map(str(tmp_path), "MAP_REGISTERED", "gMapGroup_NewLand")

    def test_no_map_on_disk_raises(self, tmp_path: Path) -> None:
        _build_project(tmp_path, with_orphan=False)
        with pytest.raises(MapNotFoundError):
            projects.register_map(str(tmp_path), "MAP_ORPHAN", "gMapGroup_Existing")


# --- unregister_map -------------------------------------------------------


class TestUnregisterMap:
    def test_unregisters_existing_map(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = projects.unregister_map(str(tmp_path), "MAP_REGISTERED")
        # Only map in its group -> group is removed.
        assert result["group_removed"] is True
        text = (tmp_path / "data/maps/map_groups.json").read_text(encoding="utf-8")
        assert '"Reg"' not in text
        # Files preserved.
        assert (tmp_path / "data/maps/Reg/map.json").is_file()
        assert (tmp_path / "data/layouts/Reg/map.bin").is_file()
        # orphaned_files reports them.
        assert "data/maps/Reg/map.json" in result["orphaned_files"]
        assert "data/layouts/Reg/map.bin" in result["orphaned_files"]

    def test_unregister_already_unregistered_noop(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Orphan map: on disk but not in map_groups.json -> no-op success.
        result = projects.unregister_map(str(tmp_path), "MAP_ORPHAN")
        assert result["was_already_unregistered"] is True
        assert result["files_modified"] == []

    def test_unregister_group_kept_if_other_members(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        # Register orphan into the same group so removing one leaves a non-empty group.
        projects.register_map(str(tmp_path), "MAP_ORPHAN", "gMapGroup_Existing")
        result = projects.unregister_map(str(tmp_path), "MAP_REGISTERED")
        assert result["group_removed"] is False
        text = (tmp_path / "data/maps/map_groups.json").read_text(encoding="utf-8")
        assert "gMapGroup_Existing" in text

    def test_no_map_on_disk_raises(self, tmp_path: Path) -> None:
        _build_project(tmp_path, with_orphan=False)
        with pytest.raises(MapNotFoundError):
            projects.unregister_map(str(tmp_path), "MAP_NOWHERE")


# --- Registration smoke test ---------------------------------------------


class TestRegisteredOnServer:
    def test_all_eight_mutation_tools_registered(self) -> None:
        import asyncio

        from porymap_mcp.server import build_server

        mcp = build_server()
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert {
            "paint_metatile",
            "paint_rectangle",
            "flood_fill",
            "set_border",
            "create_map",
            "resize_map",
            "register_map",
            "unregister_map",
        }.issubset(names)
