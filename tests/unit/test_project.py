"""Tests for ``porymap_mcp.project.Project``."""

from __future__ import annotations

from pathlib import Path

import pytest

from porymap_mcp.errors import ProjectError, UnsupportedBaseGameError
from porymap_mcp.parsers.projectconfig import BaseGameVersion
from porymap_mcp.project import (
    PROJECT_CONFIG_FILENAME,
    SUPPORTED_BASE_GAME_VERSIONS,
    Project,
)

MINIMAL_EMERALD_CFG = "base_game_version = pokeemerald\n"


def _write_cfg(root: Path, text: str = MINIMAL_EMERALD_CFG) -> None:
    (root / PROJECT_CONFIG_FILENAME).write_text(text, encoding="utf-8")


class TestLoadHappyPath:
    def test_loads_minimal_emerald_project(self, tmp_path: Path) -> None:
        _write_cfg(tmp_path)
        project = Project.load(tmp_path)
        assert project.root == tmp_path
        assert project.config.base_game_version is BaseGameVersion.POKEEMERALD

    def test_resolved_config_carries_format_parameters(self, tmp_path: Path) -> None:
        _write_cfg(tmp_path)
        project = Project.load(tmp_path)
        # The parser fills defaults; Project exposes them via .config so parsers
        # consuming the config never need to look at base_game_version.
        assert project.config.metatile_id_mask == 0x03FF
        assert project.config.collision_mask == 0x0C00
        assert project.config.elevation_mask == 0xF000


class TestLoadFailureModes:
    def test_root_not_a_directory_raises(self, tmp_path: Path) -> None:
        not_a_dir = tmp_path / "does_not_exist"
        with pytest.raises(ProjectError, match="not a directory"):
            Project.load(not_a_dir)

    def test_root_is_a_file_raises(self, tmp_path: Path) -> None:
        a_file = tmp_path / "file.txt"
        a_file.write_text("hi", encoding="utf-8")
        with pytest.raises(ProjectError, match="not a directory"):
            Project.load(a_file)

    def test_missing_cfg_raises_project_error(self, tmp_path: Path) -> None:
        # Directory exists, but no porymap.project.cfg in it.
        with pytest.raises(ProjectError, match=r"porymap\.project\.cfg not found"):
            Project.load(tmp_path)


class TestSupportedBaseGameVersionGate:
    def test_v0_1_supports_only_pokeemerald(self) -> None:
        # Document the v0.1.0 policy as a test so any change is intentional.
        assert BaseGameVersion.POKEEMERALD in SUPPORTED_BASE_GAME_VERSIONS
        assert len(SUPPORTED_BASE_GAME_VERSIONS) == 1

    def test_pokeruby_project_is_rejected(self, tmp_path: Path) -> None:
        # In v0.1.0 the gate fires at the parser (no defaults populated yet)
        # — when v0.2.0 adds ruby defaults the gate moves to ``Project.load``
        # but the public behavior here stays the same.
        _write_cfg(tmp_path, "base_game_version = pokeruby\n")
        with pytest.raises(UnsupportedBaseGameError) as exc_info:
            Project.load(tmp_path)
        assert exc_info.value.declared == "pokeruby"

    def test_unknown_version_is_rejected(self, tmp_path: Path) -> None:
        _write_cfg(tmp_path, "base_game_version = pokemystery\n")
        with pytest.raises(UnsupportedBaseGameError) as exc_info:
            Project.load(tmp_path)
        assert exc_info.value.declared == "pokemystery"


class TestImmutability:
    def test_project_is_frozen(self, tmp_path: Path) -> None:
        _write_cfg(tmp_path)
        project = Project.load(tmp_path)
        with pytest.raises(AttributeError):
            project.root = tmp_path  # type: ignore[misc]
