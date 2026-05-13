"""Tests for ``porymap_mcp.parsers.tileset`` (ADR-0004 stage 1).

Stage 1 is purely filesystem-driven, so every test builds a tiny
project layout under ``tmp_path`` with empty marker files and asserts
on the discovery result. No real tileset assets are involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.parsers.tileset import (
    TilesetEntry,
    derive_c_label,
    discover_tilesets,
)


def _make_tileset_dir(root: Path, kind: str, name: str) -> Path:
    directory = root / "data" / "tilesets" / kind / name
    directory.mkdir(parents=True)
    # Conventional asset markers — stage 1 doesn't read them but a real
    # project ships them.
    (directory / "tiles.png").touch()
    (directory / "metatiles.bin").touch()
    (directory / "metatile_attributes.bin").touch()
    (directory / "palettes").mkdir()
    return directory


# --- derive_c_label --------------------------------------------------------


class TestDeriveCLabel:
    def test_single_word(self) -> None:
        assert derive_c_label("general") == "gTileset_General"

    def test_two_words(self) -> None:
        assert derive_c_label("petalburg_woods") == "gTileset_PetalburgWoods"

    def test_three_words(self) -> None:
        assert derive_c_label("rustboro_city_pokemon_center") == (
            "gTileset_RustboroCityPokemonCenter"
        )

    def test_already_lowercase_segments(self) -> None:
        # No re-casing beyond the first letter — preserves intra-word
        # capitalization if the fork has it (rare in vanilla).
        assert derive_c_label("hoenn") == "gTileset_Hoenn"

    def test_drops_empty_segments(self) -> None:
        assert derive_c_label("foo__bar") == "gTileset_FooBar"
        assert derive_c_label("_foo") == "gTileset_Foo"
        assert derive_c_label("foo_") == "gTileset_Foo"


# --- discover_tilesets -----------------------------------------------------


class TestDiscoverTilesets:
    def test_empty_project_returns_empty(self, tmp_path: Path) -> None:
        assert discover_tilesets(tmp_path) == ()

    def test_only_primary(self, tmp_path: Path) -> None:
        _make_tileset_dir(tmp_path, "primary", "general")
        result = discover_tilesets(tmp_path)
        assert len(result) == 1
        entry = result[0]
        assert entry.name == "general"
        assert entry.c_label == "gTileset_General"
        assert entry.c_label_unverified is True
        assert entry.kind == "primary"
        assert entry.is_compressed is None

    def test_paths_are_posix_relative(self, tmp_path: Path) -> None:
        _make_tileset_dir(tmp_path, "secondary", "petalburg_woods")
        entry = discover_tilesets(tmp_path)[0]
        assert entry.tiles_path == "data/tilesets/secondary/petalburg_woods/tiles.png"
        assert entry.metatiles_path == ("data/tilesets/secondary/petalburg_woods/metatiles.bin")
        assert entry.attributes_path == (
            "data/tilesets/secondary/petalburg_woods/metatile_attributes.bin"
        )
        assert entry.palettes_dir == "data/tilesets/secondary/petalburg_woods/palettes"
        # Stage 1 must not produce backslashes on any OS.
        for path_field in (
            entry.tiles_path,
            entry.metatiles_path,
            entry.attributes_path,
            entry.palettes_dir,
        ):
            assert "\\" not in path_field

    def test_primary_before_secondary_then_name_sorted(self, tmp_path: Path) -> None:
        # Insert in deliberately scrambled order to defeat readdir.
        _make_tileset_dir(tmp_path, "secondary", "littleroot_town")
        _make_tileset_dir(tmp_path, "primary", "general")
        _make_tileset_dir(tmp_path, "secondary", "petalburg_woods")
        _make_tileset_dir(tmp_path, "primary", "building")
        result = discover_tilesets(tmp_path)
        names = [(e.kind, e.name) for e in result]
        # Stable order: primary first, then secondary, each sorted by name.
        assert names == [
            ("primary", "building"),
            ("primary", "general"),
            ("secondary", "littleroot_town"),
            ("secondary", "petalburg_woods"),
        ]

    def test_only_secondary_directory_present(self, tmp_path: Path) -> None:
        # primary/ is missing entirely — secondary alone is fine.
        _make_tileset_dir(tmp_path, "secondary", "house")
        result = discover_tilesets(tmp_path)
        assert len(result) == 1
        assert result[0].kind == "secondary"
        assert result[0].name == "house"

    def test_ignores_files_at_top_level(self, tmp_path: Path) -> None:
        # A stray file under data/tilesets/primary/ must not be reported
        # as a tileset.
        primary = tmp_path / "data" / "tilesets" / "primary"
        primary.mkdir(parents=True)
        (primary / "README.txt").write_text("a stray file")
        _make_tileset_dir(tmp_path, "primary", "general")
        result = discover_tilesets(tmp_path)
        assert [e.name for e in result] == ["general"]

    def test_directory_without_assets_is_still_discovered(self, tmp_path: Path) -> None:
        # ADR-0004: stage 1 reports any subdirectory under primary/
        # or secondary/, even one missing tiles.png. Validation is the
        # caller's job (the L1 tool that tries to read).
        empty = tmp_path / "data" / "tilesets" / "primary" / "empty_tileset"
        empty.mkdir(parents=True)
        result = discover_tilesets(tmp_path)
        assert len(result) == 1
        assert result[0].name == "empty_tileset"
        # Paths are still emitted conventionally — the file just isn't there.
        assert result[0].tiles_path == "data/tilesets/primary/empty_tileset/tiles.png"

    def test_entries_are_frozen(self, tmp_path: Path) -> None:
        _make_tileset_dir(tmp_path, "primary", "general")
        entry = discover_tilesets(tmp_path)[0]
        with pytest.raises(AttributeError, match="cannot assign"):
            entry.name = "different"  # type: ignore[misc]

    def test_returns_tuple_not_list(self, tmp_path: Path) -> None:
        _make_tileset_dir(tmp_path, "primary", "general")
        result = discover_tilesets(tmp_path)
        assert isinstance(result, tuple)
        assert all(isinstance(e, TilesetEntry) for e in result)
