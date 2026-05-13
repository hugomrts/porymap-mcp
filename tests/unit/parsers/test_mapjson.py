"""Tests for ``porymap_mcp.parsers.mapjson``."""

from __future__ import annotations

import pytest

from porymap_mcp.errors import MapJsonFormatError
from porymap_mcp.parsers import mapjson
from porymap_mcp.parsers.mapjson import Connection, MapJson

# --- Reference fixture: a realistic emerald-style map.json -----------------
#
# Modeled on pokeemerald's data/maps/LittlerootTown/map.json, trimmed for
# byte-stable round-trip testing. Includes the connection-as-array form,
# every event group populated, and the three RSE-emerald-only `allow_*`
# fields. floor_number is intentionally absent (emerald default).

REF_TEXT = """\
{
  "id": "MAP_LITTLEROOT_TOWN",
  "name": "LittlerootTown",
  "layout": "LAYOUT_LITTLEROOT_TOWN",
  "music": "MUS_LITTLEROOT",
  "region_map_section": "MAPSEC_LITTLEROOT_TOWN",
  "requires_flash": false,
  "weather": "WEATHER_NONE",
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
      "graphics_id": "OBJ_EVENT_GFX_TWIN",
      "x": 8,
      "y": 5,
      "elevation": 3,
      "movement_type": "MOVEMENT_TYPE_LOOK_AROUND",
      "movement_range_x": 0,
      "movement_range_y": 0,
      "trainer_type": "TRAINER_TYPE_NONE",
      "trainer_sight_or_berry_tree_id": "0",
      "script": "LittlerootTown_EventScript_Twin",
      "flag": "0"
    }
  ],
  "warp_events": [
    {
      "x": 5,
      "y": 4,
      "elevation": 0,
      "dest_map": "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F",
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


# Minimal header — the smallest legal map.json (all required keys, no
# optional/conditional fields, connections empty as null).
MIN_TEXT = """\
{
  "id": "MAP_BLANK",
  "name": "Blank",
  "layout": "LAYOUT_BLANK",
  "music": "MUS_NONE",
  "region_map_section": "MAPSEC_NONE",
  "requires_flash": false,
  "weather": "WEATHER_NONE",
  "map_type": "MAP_TYPE_NONE",
  "show_map_name": false,
  "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
  "connections": null
}
"""


# --- read ------------------------------------------------------------------


class TestRead:
    def test_reads_reference_header(self) -> None:
        doc = mapjson.read(REF_TEXT)
        assert doc.id == "MAP_LITTLEROOT_TOWN"
        assert doc.name == "LittlerootTown"
        assert doc.layout == "LAYOUT_LITTLEROOT_TOWN"
        assert doc.music == "MUS_LITTLEROOT"
        assert doc.region_map_section == "MAPSEC_LITTLEROOT_TOWN"
        assert doc.requires_flash is False
        assert doc.weather == "WEATHER_NONE"
        assert doc.map_type == "MAP_TYPE_TOWN"
        assert doc.show_map_name is True
        assert doc.battle_scene == "MAP_BATTLE_SCENE_NORMAL"

    def test_reads_optional_allow_flags(self) -> None:
        doc = mapjson.read(REF_TEXT)
        assert doc.allow_cycling is True
        assert doc.allow_escaping is False
        assert doc.allow_running is True

    def test_floor_number_absent_is_none(self) -> None:
        doc = mapjson.read(REF_TEXT)
        assert doc.floor_number is None

    def test_floor_number_negative_supported(self) -> None:
        anchor = '"battle_scene": "MAP_BATTLE_SCENE_NORMAL",\n  "connections": null'
        text = MIN_TEXT.replace(anchor, '"floor_number": -2,\n  ' + anchor)
        doc = mapjson.read(text)
        assert doc.floor_number == -2

    def test_reads_connection_array(self) -> None:
        doc = mapjson.read(REF_TEXT)
        assert len(doc.connections) == 1
        conn = doc.connections[0]
        assert conn.map == "MAP_ROUTE101"
        assert conn.offset == 0
        assert conn.direction == "up"
        assert conn.custom == {}

    def test_connections_null_means_empty(self) -> None:
        doc = mapjson.read(MIN_TEXT)
        assert doc.connections == ()

    def test_connections_empty_array_means_empty(self) -> None:
        text = MIN_TEXT.replace('"connections": null', '"connections": []')
        doc = mapjson.read(text)
        assert doc.connections == ()

    def test_connections_missing_key_means_empty(self) -> None:
        # Hand-edited file with no `connections` key at all.
        text = MIN_TEXT.replace(',\n  "connections": null', "")
        doc = mapjson.read(text)
        assert doc.connections == ()

    def test_connection_preserves_custom_keys(self) -> None:
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": [{"map": "MAP_X", "offset": 1, "direction": "left", "_note": "hi"}]',
        )
        doc = mapjson.read(text)
        assert doc.connections[0].custom == {"_note": "hi"}

    def test_reads_event_arrays(self) -> None:
        doc = mapjson.read(REF_TEXT)
        assert doc.object_events is not None
        assert len(doc.object_events) == 1
        assert doc.object_events[0]["graphics_id"] == "OBJ_EVENT_GFX_TWIN"
        assert doc.warp_events is not None
        assert len(doc.warp_events) == 1
        assert doc.coord_events == ()
        assert doc.bg_events is not None
        assert doc.bg_events[0]["type"] == "sign"

    def test_event_arrays_absent_when_inheriting(self) -> None:
        # Inheriting events: shared_events_map set, event arrays omitted.
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": null,\n  "shared_events_map": "MAP_OTHER"',
        )
        doc = mapjson.read(text)
        assert doc.shared_events_map == "MAP_OTHER"
        assert doc.object_events is None
        assert doc.warp_events is None

    def test_unknown_top_level_keys_preserved(self) -> None:
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": null,\n  "_provenance": "hand-edited",\n  "extra_int": 7',
        )
        doc = mapjson.read(text)
        assert doc.custom == {"_provenance": "hand-edited", "extra_int": 7}

    def test_unknown_event_fields_preserved(self) -> None:
        # Per ADR-0003 + map.json brief: events round-trip verbatim,
        # including feature-flag-gated fields like `local_id`, `quantity`,
        # `underfoot`, `type` for objects.
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": null,\n  "object_events": [{"local_id": "LOCALID_X", '
            '"graphics_id": "G", "x": 1, "y": 2, "elevation": 0, '
            '"movement_type": "M", "movement_range_x": 0, "movement_range_y": 0, '
            '"trainer_type": "T", "trainer_sight_or_berry_tree_id": "0", '
            '"script": "0x0", "flag": "0", "type": "object"}],\n'
            '  "warp_events": [], "coord_events": [], "bg_events": []',
        )
        doc = mapjson.read(text)
        assert doc.object_events is not None
        assert doc.object_events[0]["local_id"] == "LOCALID_X"
        assert doc.object_events[0]["type"] == "object"


class TestReadErrors:
    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(MapJsonFormatError, match="invalid JSON"):
            mapjson.read("{not json")

    def test_rejects_non_object_root(self) -> None:
        with pytest.raises(MapJsonFormatError, match="top-level"):
            mapjson.read("[]")

    def test_rejects_missing_required_keys(self) -> None:
        with pytest.raises(MapJsonFormatError, match="missing required top-level keys"):
            mapjson.read('{"id": "MAP_X"}')

    def test_rejects_wrong_type_on_required_string(self) -> None:
        text = MIN_TEXT.replace('"id": "MAP_BLANK"', '"id": 42')
        with pytest.raises(MapJsonFormatError, match="'id': expected string"):
            mapjson.read(text)

    def test_rejects_wrong_type_on_required_bool(self) -> None:
        text = MIN_TEXT.replace('"requires_flash": false', '"requires_flash": "no"')
        with pytest.raises(MapJsonFormatError, match="'requires_flash': expected boolean"):
            mapjson.read(text)

    def test_rejects_int_for_bool_field(self) -> None:
        # 0/1 are NOT booleans even though Python's bool subclasses int.
        text = MIN_TEXT.replace('"requires_flash": false', '"requires_flash": 0')
        with pytest.raises(MapJsonFormatError, match="expected boolean"):
            mapjson.read(text)

    def test_rejects_bool_for_int_field(self) -> None:
        anchor = '"battle_scene": "MAP_BATTLE_SCENE_NORMAL",\n  "connections": null'
        text = MIN_TEXT.replace(anchor, '"floor_number": true,\n  ' + anchor)
        with pytest.raises(MapJsonFormatError, match="'floor_number': expected integer"):
            mapjson.read(text)

    def test_rejects_non_array_connections(self) -> None:
        text = MIN_TEXT.replace('"connections": null', '"connections": "north"')
        with pytest.raises(MapJsonFormatError, match="'connections' must be"):
            mapjson.read(text)

    def test_rejects_connection_missing_required_keys(self) -> None:
        text = MIN_TEXT.replace('"connections": null', '"connections": [{"map": "X"}]')
        with pytest.raises(MapJsonFormatError, match="connections\\[0\\]: missing"):
            mapjson.read(text)

    def test_rejects_non_object_connection(self) -> None:
        text = MIN_TEXT.replace('"connections": null', '"connections": ["bad"]')
        with pytest.raises(MapJsonFormatError, match="connections\\[0\\]: expected object"):
            mapjson.read(text)

    def test_rejects_non_array_event_group(self) -> None:
        text = MIN_TEXT.replace(
            '"connections": null', '"connections": null,\n  "warp_events": "nope"'
        )
        with pytest.raises(MapJsonFormatError, match="'warp_events': expected array"):
            mapjson.read(text)

    def test_rejects_non_object_event_entry(self) -> None:
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": null,\n  "warp_events": [42]',
        )
        with pytest.raises(MapJsonFormatError, match="warp_events\\[0\\]: expected object"):
            mapjson.read(text)


# --- write -----------------------------------------------------------------


class TestWrite:
    def test_round_trips_reference(self) -> None:
        doc = mapjson.read(REF_TEXT)
        assert mapjson.write(doc) == REF_TEXT

    def test_round_trips_minimal(self) -> None:
        doc = mapjson.read(MIN_TEXT)
        assert mapjson.write(doc) == MIN_TEXT

    def test_empty_connections_emitted_as_null(self) -> None:
        doc = mapjson.read(MIN_TEXT)
        out = mapjson.write(doc)
        assert '"connections": null' in out
        assert '"connections": []' not in out

    def test_empty_array_form_normalized_to_null_on_write(self) -> None:
        # Porymap rule: empty connections -> null. We honor it on output
        # even when the input used [].
        text = MIN_TEXT.replace('"connections": null', '"connections": []')
        doc = mapjson.read(text)
        out = mapjson.write(doc)
        assert '"connections": null' in out

    def test_canonical_key_order(self) -> None:
        out = mapjson.write(mapjson.read(REF_TEXT))
        # Spot-check the documented canonical order at a few critical
        # boundaries.
        order = [
            '"id"',
            '"name"',
            '"layout"',
            '"music"',
            '"region_map_section"',
            '"requires_flash"',
            '"weather"',
            '"map_type"',
            '"allow_cycling"',
            '"allow_escaping"',
            '"allow_running"',
            '"show_map_name"',
            '"battle_scene"',
            '"connections"',
            '"object_events"',
            '"warp_events"',
            '"coord_events"',
            '"bg_events"',
        ]
        positions = [out.index(k) for k in order]
        assert positions == sorted(positions), "canonical key order violated: " + ", ".join(order)

    def test_optional_fields_omitted_when_none(self) -> None:
        doc = mapjson.read(MIN_TEXT)
        out = mapjson.write(doc)
        for absent in (
            '"allow_cycling"',
            '"allow_escaping"',
            '"allow_running"',
            '"floor_number"',
            '"shared_events_map"',
            '"shared_scripts_map"',
            '"object_events"',
            '"warp_events"',
            '"coord_events"',
            '"bg_events"',
        ):
            assert absent not in out, f"{absent} must be omitted when None"

    def test_inheritance_preserved(self) -> None:
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": null,\n  "shared_events_map": "MAP_OTHER",\n'
            '  "shared_scripts_map": "MAP_OTHER"',
        )
        doc = mapjson.read(text)
        out = mapjson.write(doc)
        assert out == text

    def test_custom_top_level_keys_appended(self) -> None:
        text = MIN_TEXT.replace(
            '"connections": null',
            '"connections": null,\n  "_provenance": "hand-edited"',
        )
        doc = mapjson.read(text)
        out = mapjson.write(doc)
        # Custom key must be present and after the canonical block.
        assert '"_provenance": "hand-edited"' in out
        assert out.index('"_provenance"') > out.index('"connections"')

    def test_connection_custom_keys_round_trip(self) -> None:
        doc = MapJson(
            id="MAP_X",
            name="X",
            layout="LAYOUT_X",
            music="MUS_NONE",
            region_map_section="MAPSEC_NONE",
            requires_flash=False,
            weather="WEATHER_NONE",
            map_type="MAP_TYPE_NONE",
            show_map_name=False,
            battle_scene="MAP_BATTLE_SCENE_NORMAL",
            connections=(
                Connection(
                    map="MAP_Y",
                    offset=2,
                    direction="left",
                    custom={"_extra": "hello"},
                ),
            ),
        )
        out = mapjson.write(doc)
        # Connection-level custom key must appear inside the connection
        # object after the canonical three.
        assert '"_extra": "hello"' in out
        assert out.index('"_extra"') > out.index('"direction"')

    def test_output_has_single_trailing_newline(self) -> None:
        out = mapjson.write(mapjson.read(REF_TEXT))
        assert out.endswith("\n")
        assert not out.endswith("\n\n")

    def test_two_space_indent(self) -> None:
        out = mapjson.write(mapjson.read(MIN_TEXT))
        lines = out.splitlines()
        assert lines[1].startswith('  "')
        assert not lines[1].startswith('   "')
