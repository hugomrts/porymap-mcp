"""Tests for ``porymap_mcp.parsers.mapgroups``."""

from __future__ import annotations

import pytest

from porymap_mcp.errors import MapGroupsFormatError
from porymap_mcp.parsers import mapgroups
from porymap_mcp.parsers.mapgroups import MapGroups

# --- Reference fixture (matches the format-expert-validated example) -------

REF_TEXT = """\
{
  "group_order": [
    "gMapGroup_TownsAndRoutes",
    "gMapGroup_Indoor"
  ],
  "gMapGroup_TownsAndRoutes": [
    "LittlerootTown",
    "Route101"
  ],
  "gMapGroup_Indoor": [
    "LittlerootTown_BrendansHouse_1F"
  ]
}
"""


# --- read ---


class TestRead:
    def test_reads_reference(self) -> None:
        doc = mapgroups.read(REF_TEXT)
        assert doc.group_order == ("gMapGroup_TownsAndRoutes", "gMapGroup_Indoor")
        assert doc.groups == {
            "gMapGroup_TownsAndRoutes": ("LittlerootTown", "Route101"),
            "gMapGroup_Indoor": ("LittlerootTown_BrendansHouse_1F",),
        }
        assert doc.custom == {}

    def test_empty_group_is_legal(self) -> None:
        text = """{
  "group_order": ["gMapGroup_Empty"],
  "gMapGroup_Empty": []
}
"""
        doc = mapgroups.read(text)
        assert doc.groups["gMapGroup_Empty"] == ()

    def test_group_listed_in_order_but_missing_treated_as_empty(self) -> None:
        text = """{
  "group_order": ["gMapGroup_A", "gMapGroup_B"],
  "gMapGroup_A": ["MapOne"]
}
"""
        doc = mapgroups.read(text)
        assert doc.groups["gMapGroup_A"] == ("MapOne",)
        assert doc.groups["gMapGroup_B"] == ()

    def test_unknown_sibling_keys_preserved_in_custom(self) -> None:
        text = """{
  "group_order": ["gMapGroup_A"],
  "gMapGroup_A": ["MapOne"],
  "_comment": "hand-edited",
  "extra_table": [1, 2, 3]
}
"""
        doc = mapgroups.read(text)
        assert doc.custom == {"_comment": "hand-edited", "extra_table": [1, 2, 3]}

    def test_empty_group_order_is_legal(self) -> None:
        doc = mapgroups.read('{"group_order": []}')
        assert doc.group_order == ()
        assert doc.groups == {}

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(MapGroupsFormatError, match="invalid JSON"):
            mapgroups.read("{not json")

    def test_rejects_non_object_root(self) -> None:
        with pytest.raises(MapGroupsFormatError, match="top-level"):
            mapgroups.read("[]")

    def test_rejects_missing_group_order(self) -> None:
        with pytest.raises(MapGroupsFormatError, match="group_order"):
            mapgroups.read('{"gMapGroup_A": []}')

    def test_rejects_non_array_group_order(self) -> None:
        with pytest.raises(MapGroupsFormatError, match="must be an array"):
            mapgroups.read('{"group_order": "gMapGroup_A"}')

    def test_rejects_non_string_in_group_order(self) -> None:
        with pytest.raises(MapGroupsFormatError, match=r"group_order\[1\]"):
            mapgroups.read('{"group_order": ["gMapGroup_A", 42]}')

    def test_rejects_empty_string_in_group_order(self) -> None:
        with pytest.raises(MapGroupsFormatError, match="empty string"):
            mapgroups.read('{"group_order": [""]}')

    def test_rejects_non_array_group_value(self) -> None:
        text = """{
  "group_order": ["gMapGroup_A"],
  "gMapGroup_A": "not_an_array"
}
"""
        with pytest.raises(MapGroupsFormatError, match=r"gMapGroup_A.*expected array"):
            mapgroups.read(text)

    def test_rejects_null_inside_group(self) -> None:
        text = """{
  "group_order": ["gMapGroup_A"],
  "gMapGroup_A": ["MapOne", null]
}
"""
        with pytest.raises(MapGroupsFormatError, match="null is not allowed"):
            mapgroups.read(text)

    def test_rejects_non_string_inside_group(self) -> None:
        text = """{
  "group_order": ["gMapGroup_A"],
  "gMapGroup_A": ["MapOne", 7]
}
"""
        with pytest.raises(MapGroupsFormatError, match=r"gMapGroup_A.*expected string"):
            mapgroups.read(text)

    def test_rejects_empty_map_name(self) -> None:
        text = """{
  "group_order": ["gMapGroup_A"],
  "gMapGroup_A": [""]
}
"""
        with pytest.raises(MapGroupsFormatError, match="empty map name"):
            mapgroups.read(text)


# --- write ---


class TestWrite:
    def test_round_trips_reference(self) -> None:
        doc = mapgroups.read(REF_TEXT)
        assert mapgroups.write(doc) == REF_TEXT

    def test_write_empty_doc(self) -> None:
        doc = MapGroups()
        assert mapgroups.write(doc) == '{\n  "group_order": []\n}\n'

    def test_emits_group_order_first(self) -> None:
        doc = mapgroups.read(REF_TEXT)
        out = mapgroups.write(doc)
        assert out.index('"group_order"') < out.index('"gMapGroup_TownsAndRoutes"')

    def test_emits_groups_in_group_order(self) -> None:
        # If the dict stores groups in a different order than group_order,
        # the writer must follow group_order — not dict insertion order.
        doc = MapGroups(
            group_order=("gMapGroup_A", "gMapGroup_B"),
            groups={
                "gMapGroup_B": ("MapB",),
                "gMapGroup_A": ("MapA",),
            },
        )
        out = mapgroups.write(doc)
        assert out.index('"gMapGroup_A"') < out.index('"gMapGroup_B"')

    def test_emits_missing_group_as_empty_array(self) -> None:
        doc = MapGroups(
            group_order=("gMapGroup_A", "gMapGroup_B"),
            groups={"gMapGroup_A": ("MapOne",)},
        )
        out = mapgroups.write(doc)
        # Both groups must appear, with the missing one as [].
        assert '"gMapGroup_A"' in out
        assert '"gMapGroup_B": []' in out

    def test_round_trips_custom_keys(self) -> None:
        text = """{
  "group_order": [
    "gMapGroup_A"
  ],
  "gMapGroup_A": [
    "MapOne"
  ],
  "_comment": "hand-edited"
}
"""
        doc = mapgroups.read(text)
        assert mapgroups.write(doc) == text

    def test_output_has_trailing_newline(self) -> None:
        doc = mapgroups.read(REF_TEXT)
        out = mapgroups.write(doc)
        assert out.endswith("\n")
        assert not out.endswith("\n\n")
