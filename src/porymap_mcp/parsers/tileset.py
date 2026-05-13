"""Tileset discovery — filesystem-first, per ADR-0004 stage 1.

This module enumerates the tilesets a pokeemerald-family project ships
without parsing any C source. It walks
``<root>/data/tilesets/{primary,secondary}/`` and reports one
:class:`TilesetEntry` per subdirectory, deriving the C label from the
directory basename via the snake_case → ``gTileset_<PascalCase>``
convention used by every vanilla and pokeemerald-expansion project.

Per ADR-0004:

  - **Stage 1 (this module, v0.1.0)** is purely filesystem-driven. We do
    not open any file. ``c_label`` is marked ``c_label_unverified=True``
    because the convention has not been confirmed against
    ``src/data/tilesets/headers.h``.
  - **Stage 2 (deferred)** will add a minimal C-struct lexer for
    ``headers.h`` plus an ``INCBIN`` / ``INCGFX`` resolver, and clear
    the ``c_label_unverified`` flag (and populate ``is_compressed``).

A directory is recognized as a tileset solely by its location under
``primary/`` or ``secondary/``. We do not validate that ``tiles.png``,
``metatiles.bin``, ``metatile_attributes.bin``, or ``palettes/`` exist —
that's an L1 tool concern (``list_metatiles`` will fail with a clear
error if the assets are missing). Stage 1's contract is "what tilesets
does this project claim to ship?", not "are they internally consistent?".

References:
  - ADR-0004 — `docs/decisions/0004-tileset-metadata-source.md`
  - Conventional asset layout: pokeemerald
    `data/tilesets/{primary,secondary}/<name>/{tiles.png,metatiles.bin,
    metatile_attributes.bin,palettes/}` —
    https://github.com/pret/pokeemerald/tree/master/data/tilesets
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

#: Project-relative roots Porymap looks under for tilesets, in the
#: pokeemerald default layout. Forks that override these via
#: ``path/data_primary_tilesets`` / ``path/data_secondary_tilesets`` in
#: ``porymap.project.cfg`` are not yet honored — see ADR-0004 stage 2.
PRIMARY_TILESETS_DIR: Final = "data/tilesets/primary"
SECONDARY_TILESETS_DIR: Final = "data/tilesets/secondary"

#: Conventional asset basenames inside each tileset directory.
TILES_FILENAME: Final = "tiles.png"
METATILES_FILENAME: Final = "metatiles.bin"
ATTRIBUTES_FILENAME: Final = "metatile_attributes.bin"
PALETTES_DIRNAME: Final = "palettes"

TilesetKind = Literal["primary", "secondary"]


@dataclass(frozen=True, slots=True)
class TilesetEntry:
    """One tileset discovered on disk.

    All ``*_path`` fields are POSIX-style strings relative to the project
    root, matching the convention used by :class:`LayoutEntry` for
    ``blockdata_filepath`` etc. The :class:`Project` layer resolves them
    to absolute paths via :meth:`Project.resolve_path` when needed.

    ``c_label`` is derived by the snake_case → ``gTileset_<PascalCase>``
    convention. It is **unverified** in stage 1 (the convention may not
    hold for arbitrary forks); ADR-0004 stage 2 will verify by parsing
    ``src/data/tilesets/headers.h``.

    ``is_compressed`` is ``None`` in stage 1 — the value lives only in
    the C struct and is not used by any L1 tool. Stage 2 will populate
    it from ``headers.h``.
    """

    name: str
    c_label: str
    c_label_unverified: bool
    kind: TilesetKind
    tiles_path: str
    metatiles_path: str
    attributes_path: str
    palettes_dir: str
    is_compressed: bool | None = None


# --- public API ------------------------------------------------------------


_DISCOVERY_ROOTS: Final[tuple[tuple[TilesetKind, str], ...]] = (
    ("primary", PRIMARY_TILESETS_DIR),
    ("secondary", SECONDARY_TILESETS_DIR),
)


def discover_tilesets(project_root: Path) -> tuple[TilesetEntry, ...]:
    """Enumerate every tileset under ``project_root``.

    Returns entries sorted by ``(kind, name)`` so output is deterministic
    across operating systems with different ``readdir`` orders. Returns
    an empty tuple when neither ``data/tilesets/primary`` nor
    ``data/tilesets/secondary`` exists — a project layout we do not
    treat as an error here (the caller may surface it).
    """
    entries: list[TilesetEntry] = []
    for kind, dir_relative in _DISCOVERY_ROOTS:
        kind_dir = project_root / dir_relative
        if not kind_dir.is_dir():
            continue
        for child in sorted(kind_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            entries.append(_build_entry(child.name, kind, dir_relative))
    return tuple(entries)


def derive_c_label(name: str) -> str:
    """Convert a tileset directory basename to its conventional C label.

    Examples:
        >>> derive_c_label("general")
        'gTileset_General'
        >>> derive_c_label("petalburg_woods")
        'gTileset_PetalburgWoods'
        >>> derive_c_label("rustboro_city")
        'gTileset_RustboroCity'

    Empty segments (from leading/trailing/double underscores) are
    silently dropped; pokeemerald and pokeemerald-expansion never
    produce them, but a fork that does will simply lose the empty
    segment in the derived label — at which point ``c_label_unverified``
    correctly signals the mismatch.
    """
    parts = [segment for segment in name.split("_") if segment]
    pascal = "".join(segment[:1].upper() + segment[1:] for segment in parts)
    return f"gTileset_{pascal}"


# --- internals -------------------------------------------------------------


def _build_entry(name: str, kind: TilesetKind, dir_relative: str) -> TilesetEntry:
    base = f"{dir_relative}/{name}"
    return TilesetEntry(
        name=name,
        c_label=derive_c_label(name),
        c_label_unverified=True,
        kind=kind,
        tiles_path=f"{base}/{TILES_FILENAME}",
        metatiles_path=f"{base}/{METATILES_FILENAME}",
        attributes_path=f"{base}/{ATTRIBUTES_FILENAME}",
        palettes_dir=f"{base}/{PALETTES_DIRNAME}",
        is_compressed=None,
    )
