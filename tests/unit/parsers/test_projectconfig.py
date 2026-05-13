"""Tests for ``porymap_mcp.parsers.projectconfig``."""

from __future__ import annotations

import pytest

from porymap_mcp.errors import ProjectConfigFormatError
from porymap_mcp.parsers import projectconfig
from porymap_mcp.parsers.projectconfig import ProjectConfig

# --- Reference fixture (matches the format-expert-validated example) -------

REF_CFG_TEXT = """\
base_game_version=pokeemerald
use_poryscript=0
use_custom_border_size=0
enable_triple_layer_metatiles=0
default_metatile=1
default_elevation=3
default_collision=0
default_primary_tileset=gTileset_General
default_secondary_tileset=gTileset_Petalburg
metatile_attributes_size=2
metatile_behavior_mask=0x00FF
metatile_terrain_type_mask=0x3E00
metatile_encounter_type_mask=0xC000
metatile_layer_type_mask=0x6000
block_metatile_id_mask=0x03FF
block_collision_mask=0x0C00
block_elevation_mask=0xF000
"""


class TestRead:
    def test_reads_reference(self) -> None:
        cfg = projectconfig.read(REF_CFG_TEXT)
        assert cfg.base_game_version == "pokeemerald"
        assert cfg.use_poryscript is False
        assert cfg.use_custom_border_size is False
        assert cfg.enable_triple_layer_metatiles is False
        assert cfg.metatile_attributes_size == 2
        assert cfg.block_metatile_id_mask == 0x03FF
        assert cfg.block_collision_mask == 0x0C00
        assert cfg.block_elevation_mask == 0xF000
        assert cfg.metatile_behavior_mask == 0x00FF
        assert cfg.metatile_terrain_type_mask == 0x3E00
        assert cfg.metatile_encounter_type_mask == 0xC000
        assert cfg.metatile_layer_type_mask == 0x6000

    def test_preserves_insertion_order(self) -> None:
        cfg = projectconfig.read(REF_CFG_TEXT)
        keys = list(cfg.entries.keys())
        assert keys[0] == "base_game_version"
        assert keys[1] == "use_poryscript"
        assert keys[-1] == "block_elevation_mask"

    def test_drops_comments_and_blank_lines(self) -> None:
        text = (
            "# a comment\n"
            "\n"
            "base_game_version=pokeemerald\n"
            "   \n"
            "#another comment\n"
            "use_poryscript=1\n"
        )
        cfg = projectconfig.read(text)
        assert list(cfg.entries.keys()) == ["base_game_version", "use_poryscript"]
        assert cfg.use_poryscript is True

    def test_trims_whitespace_around_key_and_value(self) -> None:
        text = "  base_game_version  =   pokeemerald  \n"
        cfg = projectconfig.read(text)
        assert cfg.entries["base_game_version"] == "pokeemerald"

    def test_duplicate_key_last_wins(self) -> None:
        text = "default_metatile=1\ndefault_metatile=42\n"
        cfg = projectconfig.read(text)
        assert cfg.entries["default_metatile"] == "42"

    def test_value_may_contain_equals(self) -> None:
        # path/key syntax in Porymap allows arbitrary values; '=' in values
        # is rare but technically permitted by the split-on-first-equals rule.
        text = "path/x=foo=bar\n"
        cfg = projectconfig.read(text)
        assert cfg.entries["path/x"] == "foo=bar"

    def test_value_may_be_empty(self) -> None:
        text = "prefabs_filepath=\n"
        cfg = projectconfig.read(text)
        assert cfg.entries["prefabs_filepath"] == ""

    def test_rejects_line_without_equals(self) -> None:
        with pytest.raises(ProjectConfigFormatError, match="line 2"):
            projectconfig.read("base_game_version=pokeemerald\nthis_is_not_kv\n")

    def test_rejects_empty_key(self) -> None:
        with pytest.raises(ProjectConfigFormatError, match="empty key"):
            projectconfig.read("=value\n")


class TestTypedAccessors:
    def test_base_game_version_missing_raises(self) -> None:
        cfg = projectconfig.read("use_poryscript=1\n")
        with pytest.raises(ProjectConfigFormatError, match="base_game_version"):
            _ = cfg.base_game_version

    def test_defaults_when_keys_absent(self) -> None:
        cfg = projectconfig.read("base_game_version=pokeemerald\n")
        assert cfg.use_poryscript is False
        assert cfg.use_custom_border_size is False
        assert cfg.metatile_attributes_size == 2
        assert cfg.block_metatile_id_mask == 0x03FF
        assert cfg.block_collision_mask == 0x0C00
        assert cfg.block_elevation_mask == 0xF000

    def test_bool_accepts_only_0_or_1(self) -> None:
        cfg = projectconfig.read(
            "base_game_version=pokeemerald\nuse_poryscript=true\n"
        )
        with pytest.raises(ProjectConfigFormatError, match="use_poryscript"):
            _ = cfg.use_poryscript

    def test_int_rejects_non_decimal(self) -> None:
        cfg = projectconfig.read(
            "base_game_version=pokeemerald\nmetatile_attributes_size=0x02\n"
        )
        with pytest.raises(ProjectConfigFormatError, match="metatile_attributes_size"):
            _ = cfg.metatile_attributes_size

    def test_hex_accepts_with_or_without_prefix(self) -> None:
        # ``int(s, 16)`` happily parses both forms; the writer always
        # emits ``0x...`` but the reader is tolerant.
        cfg = projectconfig.read(
            "base_game_version=pokeemerald\nblock_metatile_id_mask=03FF\n"
        )
        assert cfg.block_metatile_id_mask == 0x03FF

    def test_hex_rejects_garbage(self) -> None:
        cfg = projectconfig.read(
            "base_game_version=pokeemerald\nblock_metatile_id_mask=nope\n"
        )
        with pytest.raises(ProjectConfigFormatError, match="block_metatile_id_mask"):
            _ = cfg.block_metatile_id_mask


class TestWrite:
    def test_round_trips_reference(self) -> None:
        cfg = projectconfig.read(REF_CFG_TEXT)
        assert projectconfig.write(cfg) == REF_CFG_TEXT

    def test_round_trip_preserves_unknown_keys(self) -> None:
        text = (
            "base_game_version=pokeemerald\n"
            "path/data_map_folders=data/maps\n"
            "global_constant/MY_FLAG=FLAG_TEMP_1\n"
        )
        cfg = projectconfig.read(text)
        assert projectconfig.write(cfg) == text

    def test_write_empty_config(self) -> None:
        cfg = ProjectConfig()
        assert projectconfig.write(cfg) == ""

    def test_write_single_entry_has_trailing_newline(self) -> None:
        cfg = projectconfig.read("base_game_version=pokeemerald\n")
        out = projectconfig.write(cfg)
        assert out.endswith("\n")
        assert out == "base_game_version=pokeemerald\n"
