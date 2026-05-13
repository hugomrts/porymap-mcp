"""Tests for ``porymap_mcp.parsers.layoutsjson``."""

from __future__ import annotations

import pytest

from porymap_mcp.errors import LayoutsJsonFormatError
from porymap_mcp.parsers import layoutsjson
from porymap_mcp.parsers.layoutsjson import LayoutEntry, LayoutsJson

# --- Reference fixtures (matches format-expert-validated examples) ---------

REF_RSE_TEXT = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_PETALBURG_CITY",
      "name": "PetalburgCity_Layout",
      "width": 30,
      "height": 30,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_Petalburg",
      "border_filepath": "data/layouts/PetalburgCity/border.bin",
      "blockdata_filepath": "data/layouts/PetalburgCity/map.bin"
    }
  ]
}
"""

REF_FRLG_TEXT = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_PALLET_TOWN",
      "name": "PalletTown_Layout",
      "width": 20,
      "height": 20,
      "border_width": 2,
      "border_height": 2,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_PalletTown",
      "border_filepath": "data/layouts/PalletTown/border.bin",
      "blockdata_filepath": "data/layouts/PalletTown/map.bin"
    }
  ]
}
"""


# --- read ---


class TestRead:
    def test_reads_rse_reference(self) -> None:
        doc = layoutsjson.read(REF_RSE_TEXT)
        assert doc.layouts_table_label == "gMapLayouts"
        assert len(doc.layouts) == 1
        entry = doc.layouts[0]
        assert entry.id == "LAYOUT_PETALBURG_CITY"
        assert entry.name == "PetalburgCity_Layout"
        assert entry.width == 30
        assert entry.height == 30
        assert entry.primary_tileset == "gTileset_General"
        assert entry.secondary_tileset == "gTileset_Petalburg"
        assert entry.border_filepath == "data/layouts/PetalburgCity/border.bin"
        assert entry.blockdata_filepath == "data/layouts/PetalburgCity/map.bin"
        assert entry.border_width is None
        assert entry.border_height is None

    def test_reads_frlg_reference_with_border_dims(self) -> None:
        doc = layoutsjson.read(REF_FRLG_TEXT)
        assert doc.layouts[0].border_width == 2
        assert doc.layouts[0].border_height == 2

    def test_empty_layouts_array_is_valid(self) -> None:
        doc = layoutsjson.read('{"layouts_table_label": "gMapLayouts", "layouts": []}\n')
        assert doc.layouts == ()

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="invalid JSON"):
            layoutsjson.read("{not json")

    def test_rejects_non_object_root(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="top-level"):
            layoutsjson.read("[]")

    def test_rejects_missing_table_label(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="layouts_table_label"):
            layoutsjson.read('{"layouts": []}')

    def test_rejects_missing_layouts(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="'layouts'"):
            layoutsjson.read('{"layouts_table_label": "gMapLayouts"}')

    def test_rejects_non_string_label(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="layouts_table_label"):
            layoutsjson.read('{"layouts_table_label": 42, "layouts": []}')

    def test_rejects_non_array_layouts(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="'layouts' must be an array"):
            layoutsjson.read('{"layouts_table_label": "gMapLayouts", "layouts": {}}')

    def test_rejects_null_entry(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="null"):
            layoutsjson.read('{"layouts_table_label": "gMapLayouts", "layouts": [null]}')

    def test_rejects_entry_missing_required_keys(self) -> None:
        bad = """
        {
          "layouts_table_label": "gMapLayouts",
          "layouts": [
            {"id": "LAYOUT_X", "name": "X_Layout"}
          ]
        }
        """
        with pytest.raises(LayoutsJsonFormatError, match="missing required keys"):
            layoutsjson.read(bad)

    def test_rejects_mismatched_border_dims(self) -> None:
        bad = """
        {
          "layouts_table_label": "gMapLayouts",
          "layouts": [
            {
              "id": "LAYOUT_X",
              "name": "X_Layout",
              "width": 10,
              "height": 10,
              "border_width": 2,
              "primary_tileset": "gTileset_General",
              "secondary_tileset": "gTileset_X",
              "border_filepath": "data/layouts/X/border.bin",
              "blockdata_filepath": "data/layouts/X/map.bin"
            }
          ]
        }
        """
        with pytest.raises(LayoutsJsonFormatError, match="border_width and border_height"):
            layoutsjson.read(bad)

    def test_rejects_non_int_width(self) -> None:
        bad = REF_RSE_TEXT.replace('"width": 30', '"width": "30"')
        with pytest.raises(LayoutsJsonFormatError, match=r"width.*expected integer"):
            layoutsjson.read(bad)

    def test_rejects_bool_for_width(self) -> None:
        # bool is a subclass of int in Python — must be rejected explicitly.
        bad = REF_RSE_TEXT.replace('"width": 30', '"width": true')
        with pytest.raises(LayoutsJsonFormatError, match="width"):
            layoutsjson.read(bad)


# --- LayoutEntry validation ---


class TestLayoutEntryValidation:
    def _minimal_kwargs(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = dict(
            id="LAYOUT_X",
            name="X_Layout",
            width=10,
            height=10,
            primary_tileset="gTileset_General",
            secondary_tileset="gTileset_X",
            border_filepath="data/layouts/X/border.bin",
            blockdata_filepath="data/layouts/X/map.bin",
        )
        base.update(overrides)
        return base

    def test_rejects_only_border_width(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="border_width and border_height"):
            LayoutEntry(**self._minimal_kwargs(border_width=2))  # type: ignore[arg-type]

    def test_rejects_only_border_height(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="border_width and border_height"):
            LayoutEntry(**self._minimal_kwargs(border_height=2))  # type: ignore[arg-type]

    def test_rejects_zero_width(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="positive"):
            LayoutEntry(**self._minimal_kwargs(width=0))  # type: ignore[arg-type]

    def test_rejects_negative_height(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="positive"):
            LayoutEntry(**self._minimal_kwargs(height=-1))  # type: ignore[arg-type]

    def test_rejects_zero_border_width(self) -> None:
        with pytest.raises(LayoutsJsonFormatError, match="border_width must be positive"):
            LayoutEntry(**self._minimal_kwargs(border_width=0, border_height=2))  # type: ignore[arg-type]


# --- write ---


class TestWrite:
    def test_round_trips_rse(self) -> None:
        doc = layoutsjson.read(REF_RSE_TEXT)
        assert layoutsjson.write(doc) == REF_RSE_TEXT

    def test_round_trips_frlg_with_border_dims(self) -> None:
        doc = layoutsjson.read(REF_FRLG_TEXT)
        assert layoutsjson.write(doc) == REF_FRLG_TEXT

    def test_omits_border_dims_when_none(self) -> None:
        doc = LayoutsJson(
            layouts_table_label="gMapLayouts",
            layouts=(
                LayoutEntry(
                    id="LAYOUT_X",
                    name="X_Layout",
                    width=10,
                    height=10,
                    primary_tileset="gTileset_General",
                    secondary_tileset="gTileset_X",
                    border_filepath="data/layouts/X/border.bin",
                    blockdata_filepath="data/layouts/X/map.bin",
                ),
            ),
        )
        out = layoutsjson.write(doc)
        assert "border_width" not in out
        assert "border_height" not in out

    def test_emits_canonical_key_order(self) -> None:
        doc = LayoutsJson(
            layouts_table_label="gMapLayouts",
            layouts=(
                LayoutEntry(
                    id="LAYOUT_X",
                    name="X_Layout",
                    width=10,
                    height=10,
                    border_width=2,
                    border_height=2,
                    primary_tileset="gTileset_General",
                    secondary_tileset="gTileset_X",
                    border_filepath="data/layouts/X/border.bin",
                    blockdata_filepath="data/layouts/X/map.bin",
                ),
            ),
        )
        out = layoutsjson.write(doc)
        # Verify each key appears in the expected canonical order.
        order = (
            "id",
            "name",
            "width",
            "height",
            "border_width",
            "border_height",
            "primary_tileset",
            "secondary_tileset",
            "border_filepath",
            "blockdata_filepath",
        )
        positions = [out.index(f'"{k}"') for k in order]
        assert positions == sorted(positions)

    def test_output_has_trailing_newline(self) -> None:
        doc = layoutsjson.read(REF_RSE_TEXT)
        out = layoutsjson.write(doc)
        assert out.endswith("\n")
        assert not out.endswith("\n\n")

    def test_preserves_layout_array_order(self) -> None:
        text = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_A",
      "name": "A_Layout",
      "width": 10,
      "height": 10,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_A",
      "border_filepath": "data/layouts/A/border.bin",
      "blockdata_filepath": "data/layouts/A/map.bin"
    },
    {
      "id": "LAYOUT_B",
      "name": "B_Layout",
      "width": 5,
      "height": 5,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_B",
      "border_filepath": "data/layouts/B/border.bin",
      "blockdata_filepath": "data/layouts/B/map.bin"
    }
  ]
}
"""
        doc = layoutsjson.read(text)
        assert [e.id for e in doc.layouts] == ["LAYOUT_A", "LAYOUT_B"]
        assert layoutsjson.write(doc) == text
