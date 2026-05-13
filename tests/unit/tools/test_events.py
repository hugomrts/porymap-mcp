"""Tests for ``porymap_mcp.tools.events`` (add_warp, add_object_event,
add_sign, add_trigger, remove_event)."""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.errors import CoordinatesOutOfBoundsError, MapNotFoundError, ProjectError
from porymap_mcp.parsers import mapjson
from porymap_mcp.tools import events

# --- Fixture helpers ------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


CFG_PORY = "base_game_version=pokeemerald\nuse_poryscript=1\n"
CFG_INC = "base_game_version=pokeemerald\nuse_poryscript=0\n"

LAYOUTS_JSON = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_X",
      "name": "X_Layout",
      "width": 5,
      "height": 5,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_X",
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


def _build_project(root: Path, *, poryscript: bool = True) -> Path:
    _write(root / "porymap.project.cfg", CFG_PORY if poryscript else CFG_INC)
    _write(root / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(root / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
    _write(root / "data" / "maps" / "X" / "map.json", X_MAP_JSON)
    _write_bytes(root / "data" / "layouts" / "X" / "map.bin", b"\x00\x00" * 25)
    _write_bytes(root / "data" / "layouts" / "X" / "border.bin", b"\x00\x00" * 4)
    return root


def _read_map_json(root: Path) -> dict:
    text = (root / "data/maps/X/map.json").read_text(encoding="utf-8")
    doc = mapjson.read(text)
    return {
        "warp_events": doc.warp_events,
        "object_events": doc.object_events,
        "coord_events": doc.coord_events,
        "bg_events": doc.bg_events,
    }


# --- add_warp -------------------------------------------------------------


class TestAddWarp:
    def test_appends_warp(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = events.add_warp(
            str(tmp_path),
            "MAP_X",
            x=1,
            y=2,
            dest_map="MAP_Y",
            dest_warp_id=3,
        )
        assert result["event_id"] == "warp_events:0"
        assert result["files_modified"] == ["data/maps/X/map.json"]
        warps = _read_map_json(tmp_path)["warp_events"]
        assert len(warps) == 1
        assert warps[0]["x"] == 1
        assert warps[0]["dest_map"] == "MAP_Y"
        assert warps[0]["dest_warp_id"] == "3"

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        events.add_warp(str(tmp_path), "MAP_X", 0, 0, "MAP_Y", 0)
        result = events.add_warp(str(tmp_path), "MAP_X", 1, 1, "MAP_Z", 1)
        assert result["event_id"] == "warp_events:1"

    def test_out_of_bounds(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(CoordinatesOutOfBoundsError):
            events.add_warp(str(tmp_path), "MAP_X", 99, 0, "MAP_Y", 0)

    def test_unknown_map(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(MapNotFoundError):
            events.add_warp(str(tmp_path), "MAP_NOWHERE", 0, 0, "MAP_Y", 0)


# --- add_object_event -----------------------------------------------------


class TestAddObjectEvent:
    def test_minimal_npc(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = events.add_object_event(
            str(tmp_path),
            "MAP_X",
            x=2,
            y=2,
            graphics_id="OBJ_EVENT_GFX_MOM",
        )
        assert result["event_id"] == "object_events:0"
        objects = _read_map_json(tmp_path)["object_events"]
        assert objects[0]["graphics_id"] == "OBJ_EVENT_GFX_MOM"
        assert objects[0]["script"] == "0"  # empty script -> "0"
        assert objects[0]["flag"] == "0"

    def test_with_script_and_flag(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        events.add_object_event(
            str(tmp_path),
            "MAP_X",
            x=0,
            y=0,
            graphics_id="OBJ_EVENT_GFX_BOY_1",
            script="X_EventScript_Boy",
            flag="FLAG_HIDE_BOY",
        )
        objects = _read_map_json(tmp_path)["object_events"]
        assert objects[0]["script"] == "X_EventScript_Boy"
        assert objects[0]["flag"] == "FLAG_HIDE_BOY"


# --- add_sign -------------------------------------------------------------


class TestAddSign:
    def test_poryscript_stub(self, tmp_path: Path) -> None:
        _build_project(tmp_path, poryscript=True)
        result = events.add_sign(str(tmp_path), "MAP_X", x=1, y=1, text="Hello!")
        assert result["script_symbol"] == "X_EventScript_Sign_0"
        assert result["script_file"] == "data/maps/X/scripts.pory"
        bg = _read_map_json(tmp_path)["bg_events"]
        assert bg[0]["type"] == "sign"
        assert bg[0]["script"] == "X_EventScript_Sign_0"
        text = (tmp_path / "data/maps/X/scripts.pory").read_text(encoding="utf-8")
        assert "script X_EventScript_Sign_0" in text
        assert 'msgbox("Hello!", MSGBOX_SIGN)' in text

    def test_inc_stub(self, tmp_path: Path) -> None:
        _build_project(tmp_path, poryscript=False)
        result = events.add_sign(str(tmp_path), "MAP_X", x=1, y=1, text="Yo")
        assert result["script_file"] == "data/maps/X/scripts.inc"
        text = (tmp_path / "data/maps/X/scripts.inc").read_text(encoding="utf-8")
        assert "X_EventScript_Sign_0::" in text
        assert "X_EventText_Sign_0:" in text
        assert '.string "Yo$"' in text

    def test_multiple_signs_increment_index(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        r1 = events.add_sign(str(tmp_path), "MAP_X", x=0, y=0, text="One")
        r2 = events.add_sign(str(tmp_path), "MAP_X", x=1, y=1, text="Two")
        assert r1["script_symbol"] == "X_EventScript_Sign_0"
        assert r2["script_symbol"] == "X_EventScript_Sign_1"

    def test_text_escaping(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        events.add_sign(str(tmp_path), "MAP_X", x=0, y=0, text='He said "hi"\nbye')
        text = (tmp_path / "data/maps/X/scripts.pory").read_text(encoding="utf-8")
        assert r"\"" in text
        assert r"\n" in text

    def test_duplicate_symbol_raises(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        events.add_sign(str(tmp_path), "MAP_X", x=0, y=0, text="One")
        # Manually re-introduce the same stub via a forced collision
        # (write a hand-edited scripts.pory that already declares Sign_1).
        script_path = tmp_path / "data/maps/X/scripts.pory"
        script_path.write_text(
            script_path.read_text(encoding="utf-8") + "\nscript X_EventScript_Sign_1 {\n}\n",
            encoding="utf-8",
        )
        # Now add_sign would derive Sign_1 from bg_events (only one sign
        # registered yet) — actually it derives next_n from bg_events array
        # = 1, so the new symbol IS Sign_1 and collision detection should
        # catch the hand-edited stub.
        with pytest.raises(ProjectError, match="already exists"):
            events.add_sign(str(tmp_path), "MAP_X", x=2, y=2, text="X")


# --- add_trigger ----------------------------------------------------------


class TestAddTrigger:
    def test_appends_trigger(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = events.add_trigger(
            str(tmp_path),
            "MAP_X",
            x=1,
            y=1,
            var="VAR_TEMP_1",
            value=0,
            script="X_EventScript_Trig",
        )
        assert result["event_id"] == "coord_events:0"
        coords = _read_map_json(tmp_path)["coord_events"]
        assert coords[0]["var"] == "VAR_TEMP_1"
        assert coords[0]["var_value"] == "0"
        assert coords[0]["script"] == "X_EventScript_Trig"


# --- remove_event ---------------------------------------------------------


class TestRemoveEvent:
    def test_removes_warp(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        events.add_warp(str(tmp_path), "MAP_X", 0, 0, "MAP_Y", 0)
        events.add_warp(str(tmp_path), "MAP_X", 1, 1, "MAP_Z", 1)
        result = events.remove_event(str(tmp_path), "MAP_X", "warp_events:0")
        assert result["removed_event"]["dest_map"] == "MAP_Y"
        warps = _read_map_json(tmp_path)["warp_events"]
        assert len(warps) == 1
        # Indices shift: the prior warp_events:1 is now warp_events:0.
        assert warps[0]["dest_map"] == "MAP_Z"

    def test_idempotent_missing_index(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        result = events.remove_event(str(tmp_path), "MAP_X", "warp_events:99")
        assert result["removed_event"] is None
        assert result["files_modified"] == []

    def test_malformed_event_id(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="malformed"):
            events.remove_event(str(tmp_path), "MAP_X", "warp_events_no_colon")

    def test_unknown_class(self, tmp_path: Path) -> None:
        _build_project(tmp_path)
        with pytest.raises(ProjectError, match="unknown event class"):
            events.remove_event(str(tmp_path), "MAP_X", "trainer_events:0")


# --- Registration smoke test ---------------------------------------------


class TestRegisteredOnServer:
    def test_all_five_event_tools_registered(self) -> None:
        import asyncio

        from porymap_mcp.server import build_server

        mcp = build_server()
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert {
            "add_warp",
            "add_object_event",
            "add_sign",
            "add_trigger",
            "remove_event",
        }.issubset(names)
