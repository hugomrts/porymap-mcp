"""Tests for ``porymap_mcp.project.Project``.

Each test builds a tiny on-disk project under ``tmp_path`` from explicit
text/byte fixtures defined inline — no test reads from the repo's
``tests/fixtures/`` directory, so the assertions are self-contained.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.errors import ProjectError, UnsupportedBaseGameError
from porymap_mcp.parsers.layoutsjson import LayoutEntry, LayoutsJson
from porymap_mcp.parsers.mapbin import MapBin, Tile
from porymap_mcp.parsers.mapgroups import MapGroups
from porymap_mcp.parsers.projectconfig import ProjectConfig
from porymap_mcp.project import Project

# --- Helpers ---------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


MIN_CFG = "base_game_version=pokeemerald\n"

# Two layouts and two maps, one group, so write_map_bin can be exercised.
LAYOUTS_JSON = """\
{
  "layouts_table_label": "gMapLayouts",
  "layouts": [
    {
      "id": "LAYOUT_LITTLEROOT_TOWN",
      "name": "LittlerootTown_Layout",
      "width": 2,
      "height": 1,
      "primary_tileset": "gTileset_General",
      "secondary_tileset": "gTileset_LittlerootTown",
      "border_filepath": "data/layouts/LittlerootTown/border.bin",
      "blockdata_filepath": "data/layouts/LittlerootTown/map.bin"
    },
    {
      "id": "LAYOUT_ROUTE_101",
      "name": "Route101_Layout",
      "width": 1,
      "height": 1,
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
    "Route101"
  ]
}
"""


def _build_project(root: Path) -> Project:
    """Lay down a minimal project at ``root`` and return a :class:`Project`."""
    _write(root / "porymap.project.cfg", MIN_CFG)
    _write(root / "data" / "layouts" / "layouts.json", LAYOUTS_JSON)
    _write(root / "data" / "maps" / "map_groups.json", MAP_GROUPS_JSON)
    # Layout 1: 2x1 = 4 bytes. Tile values arbitrary.
    _write_bytes(
        root / "data" / "layouts" / "LittlerootTown" / "map.bin",
        b"\x01\x00\x02\x00",
    )
    # 2x2 default border = 8 bytes.
    _write_bytes(
        root / "data" / "layouts" / "LittlerootTown" / "border.bin",
        b"\x00\x00" * 4,
    )
    # Layout 2: 1x1 = 2 bytes.
    _write_bytes(root / "data" / "layouts" / "Route101" / "map.bin", b"\x03\x00")
    _write_bytes(
        root / "data" / "layouts" / "Route101" / "border.bin", b"\x00\x00" * 4
    )
    return Project(root)


# --- Construction ---------------------------------------------------------


class TestConstruction:
    def test_accepts_existing_directory(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        assert proj.root == tmp_path.resolve()

    def test_rejects_nonexistent_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError, match="not a directory"):
            Project(tmp_path / "does_not_exist")

    def test_rejects_file_instead_of_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "afile"
        f.write_text("")
        with pytest.raises(ProjectError, match="not a directory"):
            Project(f)


# --- Path helpers ---------------------------------------------------------


class TestPathHelpers:
    def test_default_paths_under_root(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        assert proj.config_path == tmp_path.resolve() / "porymap.project.cfg"
        assert (
            proj.layouts_json_path == tmp_path.resolve() / "data/layouts/layouts.json"
        )
        assert (
            proj.map_groups_json_path
            == tmp_path.resolve() / "data/maps/map_groups.json"
        )

    def test_resolve_path_normalizes_posix_separators(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        assert (
            proj.resolve_path("data/layouts/Foo/map.bin")
            == tmp_path.resolve() / "data" / "layouts" / "Foo" / "map.bin"
        )

    def test_resolve_path_rejects_empty(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match="non-empty"):
            proj.resolve_path("")


# --- Config ---------------------------------------------------------------


class TestConfig:
    def test_loads_supported_base_game(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", MIN_CFG)
        proj = Project(tmp_path)
        assert proj.config.base_game_version == "pokeemerald"

    def test_lazy_load_is_cached(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", MIN_CFG)
        proj = Project(tmp_path)
        first = proj.config
        # Mutate the file on disk — cached value must not refresh.
        _write(
            tmp_path / "porymap.project.cfg", "base_game_version=pokeruby\n"
        )
        assert proj.config is first
        assert proj.config.base_game_version == "pokeemerald"

    def test_missing_config_raises(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match=r"porymap\.project\.cfg not found"):
            _ = proj.config

    def test_unsupported_base_game_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", "base_game_version=pokecrystal\n")
        proj = Project(tmp_path)
        with pytest.raises(UnsupportedBaseGameError):
            _ = proj.config

    def test_save_config_round_trip(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", MIN_CFG)
        proj = Project(tmp_path)
        # Force-load and re-save; the file content must be byte-stable.
        _ = proj.config
        proj.save_config()
        assert (tmp_path / "porymap.project.cfg").read_text(encoding="utf-8") == MIN_CFG

    def test_save_without_load_raises(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match="save_config"):
            proj.save_config()

    def test_config_setter_then_save(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        proj.config = ProjectConfig(entries={"base_game_version": "pokeemerald"})
        proj.save_config()
        assert (tmp_path / "porymap.project.cfg").read_text(encoding="utf-8") == MIN_CFG


# --- Layouts --------------------------------------------------------------


class TestLayouts:
    def test_load_and_list(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        assert proj.list_layout_ids() == [
            "LAYOUT_LITTLEROOT_TOWN",
            "LAYOUT_ROUTE_101",
        ]

    def test_get_layout_by_id(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        entry = proj.get_layout("LAYOUT_ROUTE_101")
        assert entry.width == 1
        assert entry.height == 1

    def test_get_layout_missing_raises(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        with pytest.raises(ProjectError, match="layout not found"):
            proj.get_layout("LAYOUT_NOWHERE")

    def test_missing_layouts_json_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", MIN_CFG)
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match=r"layouts\.json not found"):
            _ = proj.layouts

    def test_save_layouts_round_trip(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        _ = proj.layouts
        proj.save_layouts()
        assert (
            (tmp_path / "data/layouts/layouts.json").read_text(encoding="utf-8")
            == LAYOUTS_JSON
        )


# --- Map groups -----------------------------------------------------------


class TestMapGroups:
    def test_list_map_names_in_canonical_order(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        assert proj.list_map_names() == ["LittlerootTown", "Route101"]

    def test_group_of_returns_group_symbol(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        assert proj.group_of("Route101") == "gMapGroup_TownsAndRoutes"

    def test_group_of_unknown_returns_none(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        assert proj.group_of("Nowhere") is None

    def test_missing_map_groups_raises(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", MIN_CFG)
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match=r"map_groups\.json not found"):
            _ = proj.map_groups

    def test_save_map_groups_round_trip(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        _ = proj.map_groups
        proj.save_map_groups()
        assert (
            (tmp_path / "data/maps/map_groups.json").read_text(encoding="utf-8")
            == MAP_GROUPS_JSON
        )


# --- Map / border binary I/O ---------------------------------------------


class TestMapBinIO:
    def test_read_map_bin_uses_declared_dimensions(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        layout = proj.read_map_bin("LAYOUT_LITTLEROOT_TOWN")
        assert layout.width == 2
        assert layout.height == 1
        assert layout.get(0, 0).metatile_id == 0x001
        assert layout.get(1, 0).metatile_id == 0x002

    def test_read_border_bin_uses_default_2x2(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        border = proj.read_border_bin("LAYOUT_LITTLEROOT_TOWN")
        assert border.width == 2
        assert border.height == 2

    def test_write_map_bin_round_trip(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        original = proj.read_map_bin("LAYOUT_LITTLEROOT_TOWN")
        proj.write_map_bin("LAYOUT_LITTLEROOT_TOWN", original)
        reloaded = proj.read_map_bin("LAYOUT_LITTLEROOT_TOWN")
        assert reloaded == original

    def test_write_map_bin_persists_changes(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        new_layout = MapBin(
            width=2, height=1,
            tiles=((Tile(0x42, 1, 0), Tile(0x99, 0, 2)),),
        )
        proj.write_map_bin("LAYOUT_LITTLEROOT_TOWN", new_layout)
        reloaded = proj.read_map_bin("LAYOUT_LITTLEROOT_TOWN")
        assert reloaded.get(0, 0).metatile_id == 0x42
        assert reloaded.get(0, 0).collision == 1
        assert reloaded.get(1, 0).elevation == 2

    def test_write_map_bin_rejects_dimension_mismatch(self, tmp_path: Path) -> None:
        proj = _build_project(tmp_path)
        wrong = MapBin(width=1, height=1, tiles=((Tile(0, 0, 0),),))
        with pytest.raises(ProjectError, match="dimension mismatch"):
            proj.write_map_bin("LAYOUT_LITTLEROOT_TOWN", wrong)

    def test_uses_custom_border_size_when_set(self, tmp_path: Path) -> None:
        # Drop a tiny project with a custom 3x3 border.
        _write(
            tmp_path / "porymap.project.cfg",
            "base_game_version=pokefirered\nuse_custom_border_size=1\n",
        )
        proj = Project(tmp_path)
        proj.layouts = LayoutsJson(
            layouts_table_label="gMapLayouts",
            layouts=(
                LayoutEntry(
                    id="LAYOUT_X",
                    name="X_Layout",
                    width=1,
                    height=1,
                    border_width=3,
                    border_height=3,
                    primary_tileset="gTileset_General",
                    secondary_tileset="gTileset_X",
                    border_filepath="data/layouts/X/border.bin",
                    blockdata_filepath="data/layouts/X/map.bin",
                ),
            ),
        )
        _write_bytes(tmp_path / "data/layouts/X/map.bin", b"\x00\x00")
        _write_bytes(tmp_path / "data/layouts/X/border.bin", b"\x00\x00" * 9)
        border = proj.read_border_bin("LAYOUT_X")
        assert border.width == 3
        assert border.height == 3


# --- Setters round-trip ---------------------------------------------------


class TestSetters:
    def test_map_groups_setter_then_save(self, tmp_path: Path) -> None:
        _write(tmp_path / "porymap.project.cfg", MIN_CFG)
        proj = Project(tmp_path)
        proj.map_groups = MapGroups(
            group_order=("gMapGroup_TownsAndRoutes",),
            groups={"gMapGroup_TownsAndRoutes": ("LittlerootTown", "Route101")},
        )
        proj.save_map_groups()
        text = (tmp_path / "data/maps/map_groups.json").read_text(encoding="utf-8")
        assert "LittlerootTown" in text
        assert "Route101" in text

    def test_save_map_groups_without_load_raises(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match="save_map_groups"):
            proj.save_map_groups()

    def test_save_layouts_without_load_raises(self, tmp_path: Path) -> None:
        proj = Project(tmp_path)
        with pytest.raises(ProjectError, match="save_layouts"):
            proj.save_layouts()
