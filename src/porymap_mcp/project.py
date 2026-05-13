"""The :class:`Project` class — a lazy-loaded view of a pokeemerald-family
project on disk.

A :class:`Project` is the foothold every MCP tool uses to do its work. It
takes a filesystem root, validates the project shape on first access, and
lazily loads ``porymap.project.cfg``, ``data/layouts/layouts.json``, and
``data/maps/map_groups.json`` as their accessors are touched. Writes go
through :mod:`porymap_mcp._atomic` so a crash mid-write cannot leave a
half-written file.

Project-relative paths stored in JSON (e.g. ``data/layouts/Foo/map.bin``)
are always POSIX with forward slashes; :meth:`Project.resolve_path`
translates them to absolute :class:`pathlib.Path` for I/O.

Cache semantics: a single :class:`Project` instance caches each file on
first read; cross-process invalidation (Phase 3 L2) is not handled here.
For L1, the contract is "Porymap is not running" — our process owns the
files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from porymap_mcp._atomic import write_atomic, write_atomic_text
from porymap_mcp.errors import ProjectError, UnsupportedBaseGameError
from porymap_mcp.parsers import layoutsjson, mapbin, mapgroups, projectconfig
from porymap_mcp.parsers.layoutsjson import LayoutEntry, LayoutsJson
from porymap_mcp.parsers.mapbin import MapBin
from porymap_mcp.parsers.mapgroups import MapGroups
from porymap_mcp.parsers.projectconfig import (
    SUPPORTED_BASE_GAME_VERSIONS,
    ProjectConfig,
)

#: Default project-relative paths for the three index files. These match
#: Porymap's defaults; user-overridable ``path/*`` keys in
#: ``porymap.project.cfg`` will eventually be honored here.
DEFAULT_PROJECT_CONFIG_PATH: Final = "porymap.project.cfg"
DEFAULT_LAYOUTS_JSON_PATH: Final = "data/layouts/layouts.json"
DEFAULT_MAP_GROUPS_JSON_PATH: Final = "data/maps/map_groups.json"

#: Border size used when the project does not declare a custom size
#: (``use_custom_border_size=0`` in ``porymap.project.cfg``). Gen-3 canonical.
DEFAULT_BORDER_SIZE: Final = (2, 2)


class Project:
    """Lazy-loading view of a pokeemerald-family project on disk."""

    def __init__(self, root: Path) -> None:
        resolved = root.resolve()
        if not resolved.is_dir():
            raise ProjectError(f"project root is not a directory: {resolved}")
        self._root: Path = resolved
        self._config: ProjectConfig | None = None
        self._layouts: LayoutsJson | None = None
        self._map_groups: MapGroups | None = None

    # --- Filesystem helpers --------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    @property
    def config_path(self) -> Path:
        return self._root / DEFAULT_PROJECT_CONFIG_PATH

    @property
    def layouts_json_path(self) -> Path:
        return self._root / DEFAULT_LAYOUTS_JSON_PATH

    @property
    def map_groups_json_path(self) -> Path:
        return self._root / DEFAULT_MAP_GROUPS_JSON_PATH

    def resolve_path(self, relative_posix: str) -> Path:
        """Resolve a POSIX-relative path (as stored in JSON) under the project root."""
        if not relative_posix:
            raise ProjectError("relative_posix must be a non-empty path string")
        return self._root / Path(*relative_posix.split("/"))

    # --- Config --------------------------------------------------------

    @property
    def config(self) -> ProjectConfig:
        """Lazy-loaded :class:`ProjectConfig`. Validates
        ``base_game_version`` against :data:`SUPPORTED_BASE_GAME_VERSIONS`
        on first access."""
        if self._config is None:
            try:
                text = self.config_path.read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                raise ProjectError(
                    f"porymap.project.cfg not found at {self.config_path}. "
                    "Open the project once in Porymap to generate it."
                ) from exc
            cfg = projectconfig.read(text)
            base = cfg.base_game_version  # raises if missing
            if base not in SUPPORTED_BASE_GAME_VERSIONS:
                raise UnsupportedBaseGameError(base, SUPPORTED_BASE_GAME_VERSIONS)
            self._config = cfg
        return self._config

    @config.setter
    def config(self, value: ProjectConfig) -> None:
        self._config = value

    def save_config(self) -> None:
        """Persist the in-memory :class:`ProjectConfig` atomically.

        Raises if no config has been loaded or assigned.
        """
        if self._config is None:
            raise ProjectError("save_config() called before config was loaded or set")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic_text(self.config_path, projectconfig.write(self._config))

    # --- Layouts -------------------------------------------------------

    @property
    def layouts(self) -> LayoutsJson:
        """Lazy-loaded ``layouts.json``."""
        if self._layouts is None:
            try:
                text = self.layouts_json_path.read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                raise ProjectError(
                    f"layouts.json not found at {self.layouts_json_path}"
                ) from exc
            self._layouts = layoutsjson.read(text)
        return self._layouts

    @layouts.setter
    def layouts(self, value: LayoutsJson) -> None:
        self._layouts = value

    def get_layout(self, layout_id: str) -> LayoutEntry:
        """Return the layout entry whose ``id`` is ``layout_id``.

        Raises :class:`ProjectError` if no such layout exists.
        """
        for entry in self.layouts.layouts:
            if entry.id == layout_id:
                return entry
        raise ProjectError(f"layout not found: {layout_id!r}")

    def list_layout_ids(self) -> list[str]:
        """Return every ``LAYOUT_*`` id in the project, in file order."""
        return [entry.id for entry in self.layouts.layouts]

    def save_layouts(self) -> None:
        if self._layouts is None:
            raise ProjectError("save_layouts() called before layouts were loaded or set")
        self.layouts_json_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic_text(self.layouts_json_path, layoutsjson.write(self._layouts))

    # --- Map groups ----------------------------------------------------

    @property
    def map_groups(self) -> MapGroups:
        """Lazy-loaded ``map_groups.json``."""
        if self._map_groups is None:
            try:
                text = self.map_groups_json_path.read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                raise ProjectError(
                    f"map_groups.json not found at {self.map_groups_json_path}"
                ) from exc
            self._map_groups = mapgroups.read(text)
        return self._map_groups

    @map_groups.setter
    def map_groups(self, value: MapGroups) -> None:
        self._map_groups = value

    def list_map_names(self) -> list[str]:
        """Return every map name across all groups, in canonical order."""
        groups = self.map_groups
        out: list[str] = []
        for group in groups.group_order:
            out.extend(groups.groups.get(group, ()))
        return out

    def group_of(self, map_name: str) -> str | None:
        """Return the C-symbol map-group containing ``map_name``, or ``None``
        if the map is not registered in any group."""
        groups = self.map_groups
        for group in groups.group_order:
            if map_name in groups.groups.get(group, ()):
                return group
        return None

    def save_map_groups(self) -> None:
        if self._map_groups is None:
            raise ProjectError(
                "save_map_groups() called before map_groups were loaded or set"
            )
        self.map_groups_json_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic_text(self.map_groups_json_path, mapgroups.write(self._map_groups))

    # --- Map binary I/O -----------------------------------------------

    def read_map_bin(self, layout_id: str) -> MapBin:
        """Read the ``map.bin`` for ``layout_id`` using its declared dimensions."""
        entry = self.get_layout(layout_id)
        data = self.resolve_path(entry.blockdata_filepath).read_bytes()
        return mapbin.read(data, width=entry.width, height=entry.height)

    def read_border_bin(self, layout_id: str) -> MapBin:
        """Read the ``border.bin`` for ``layout_id``.

        Border dimensions come from the layout entry when
        ``use_custom_border_size=1``; otherwise the canonical 2x2 default
        is used.
        """
        entry = self.get_layout(layout_id)
        if entry.border_width is not None and entry.border_height is not None:
            width, height = entry.border_width, entry.border_height
        else:
            width, height = DEFAULT_BORDER_SIZE
        data = self.resolve_path(entry.border_filepath).read_bytes()
        return mapbin.read(data, width=width, height=height)

    def write_map_bin(self, layout_id: str, layout: MapBin) -> None:
        """Atomically write a layout's ``map.bin``.

        Cross-file invariant: ``layout``'s dimensions must match what
        ``layouts.json`` declares for ``layout_id`` — silently writing a
        differently-sized blob would corrupt the project.
        """
        entry = self.get_layout(layout_id)
        if (entry.width, entry.height) != (layout.width, layout.height):
            raise ProjectError(
                f"layout {layout_id!r}: dimension mismatch — "
                f"layouts.json declares {entry.width}x{entry.height}, "
                f"MapBin is {layout.width}x{layout.height}"
            )
        target = self.resolve_path(entry.blockdata_filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, mapbin.write(layout))
