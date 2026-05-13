"""The built-in prefab library (ADR-0008).

v0.1.0 ships three demonstration prefabs with metatile IDs targeting
vanilla pokeemerald conventions (typical ``gTileset_General`` /
``gTileset_LittlerootTown`` pair). Forks may need to retarget the
metatile IDs — register replacement prefabs by mutating :data:`LIBRARY`
before calling :func:`build_server`.

The metatile IDs below are documented in-line. They are *placeholders*
chosen to be visually meaningful in the typical pokeemerald case; we
do NOT guarantee they match every fork's tileset layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from porymap_mcp.errors import ProjectError


@dataclass(frozen=True, slots=True)
class PrefabTile:
    """One cell of a prefab: metatile id + collision + elevation.

    Values are validated when :func:`paint_prefab` constructs a
    :class:`Tile` from each cell — see :mod:`porymap_mcp.parsers.mapbin`.
    """

    metatile_id: int
    collision: int = 0
    elevation: int = 0


@dataclass(frozen=True, slots=True)
class Prefab:
    """A named metatile stamp.

    ``primary_tileset`` and ``secondary_tileset`` are optional
    requirements — ``None`` means the prefab is tileset-agnostic and
    can be stamped onto any map. When set, ``paint_prefab`` checks
    that the target map's layout uses the named C-label tileset and
    errors on mismatch (no auto-import; see ADR-0008 §"Decision").

    ``tiles`` is row-major: ``tiles[y][x]`` with origin top-left.
    """

    name: str
    width: int
    height: int
    description: str
    primary_tileset: str | None
    secondary_tileset: str | None
    tiles: tuple[tuple[PrefabTile, ...], ...]


# --- v0.1.0 demonstration prefabs ----------------------------------------
#
# Metatile IDs below target vanilla pokeemerald's gTileset_General +
# gTileset_LittlerootTown combo. Most forks share these tilesets at the
# same IDs; non-vanilla forks may need to retarget.

_SINGLE_TREE: Final = Prefab(
    name="single_tree",
    width=1,
    height=1,
    description="One tall-tree stamp.",
    primary_tileset=None,
    secondary_tileset=None,
    tiles=((PrefabTile(metatile_id=0x1, collision=1, elevation=0),),),
)

_FLOWER_PATCH: Final = Prefab(
    name="flower_patch",
    width=2,
    height=2,
    description="A 2x2 patch of decorative flowers — walkable.",
    primary_tileset=None,
    secondary_tileset=None,
    tiles=tuple(
        tuple(PrefabTile(metatile_id=0x2, collision=0, elevation=0) for _ in range(2))
        for _ in range(2)
    ),
)


def _house_small_tiles() -> tuple[tuple[PrefabTile, ...], ...]:
    """A 3x3 house footprint: roof on top row, walls in middle, doorway at center bottom."""
    # IDs are illustrative; the README explains retargeting.
    return (
        (
            PrefabTile(0x10, collision=1, elevation=3),
            PrefabTile(0x11, collision=1, elevation=3),
            PrefabTile(0x12, collision=1, elevation=3),
        ),
        (
            PrefabTile(0x13, collision=1, elevation=0),
            PrefabTile(0x14, collision=1, elevation=0),
            PrefabTile(0x15, collision=1, elevation=0),
        ),
        (
            PrefabTile(0x16, collision=1, elevation=0),
            PrefabTile(0x17, collision=0, elevation=0),  # doorway: walkable
            PrefabTile(0x18, collision=1, elevation=0),
        ),
    )


_HOUSE_SMALL: Final = Prefab(
    name="house_small",
    width=3,
    height=3,
    description="A 3x3 small-house footprint with a walkable doorway at the center bottom.",
    primary_tileset=None,
    secondary_tileset=None,
    tiles=_house_small_tiles(),
)


LIBRARY: Final[dict[str, Prefab]] = {
    "single_tree": _SINGLE_TREE,
    "flower_patch": _FLOWER_PATCH,
    "house_small": _HOUSE_SMALL,
}


def get(name: str) -> Prefab:
    """Resolve a prefab by name. Raises :class:`ProjectError` if unknown."""
    if name not in LIBRARY:
        available = ", ".join(sorted(LIBRARY.keys()))
        raise ProjectError(
            f"prefab {name!r} not found. Available prefabs: {available}. "
            "Use list_prefabs for details."
        )
    return LIBRARY[name]
