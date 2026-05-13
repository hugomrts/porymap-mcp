"""Parser/serializer for ``data/maps/map_groups.json``.

Format (per Porymap source: ``Project::readMapGroups`` and
``Project::saveMapGroups`` in ``porymap/src/project.cpp``):

The file is a JSON object whose first key, ``group_order``, lists the C
symbol names of each map group (e.g. ``"gMapGroup_TownsAndRoutes"``). Each
of those symbols then appears as a sibling key whose value is an array of
**bare** map names (e.g. ``"LittlerootTown"``, not ``"MAP_LITTLEROOT_TOWN"``
— the ``MAP_*`` constant lives in each map's own ``map.json``).

Write order (Porymap uses ``OrderedJson``):

  1. ``group_order`` (array of group C symbols)
  2. One key per group, in the same order as ``group_order``
  3. Any preserved custom sibling keys (Porymap's ``customMapGroupsData``)

A group that is listed in ``group_order`` but missing as a top-level key
is treated as an empty group — Porymap does the same. A top-level key
that is *not* ``group_order`` and is *not* listed in ``group_order`` is
preserved verbatim in :attr:`MapGroups.custom` so round-tripping is
byte-stable.

References:
  - Porymap reader: ``Project::readMapGroups`` in
    ``porymap/src/project.cpp``.
  - Porymap writer: ``Project::saveMapGroups`` (uses ``OrderedJson``).
  - pokeemerald canonical fixture:
    https://github.com/pret/pokeemerald/blob/master/data/maps/map_groups.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Final

from porymap_mcp.errors import MapGroupsFormatError

_GROUP_ORDER_KEY: Final = "group_order"


@dataclass(slots=True)
class MapGroups:
    """The decoded ``data/maps/map_groups.json`` document.

    :attr:`group_order` is the canonical ordering of map-group C symbols.
    :attr:`groups` maps each group symbol to its (ordered) list of bare map
    names. A group listed in :attr:`group_order` but missing from
    :attr:`groups` is treated as empty on write.

    :attr:`custom` preserves any sibling top-level keys that are neither
    ``group_order`` nor a group listed in ``group_order``, so a read/write
    cycle does not lose data Porymap itself preserves via
    ``customMapGroupsData``.
    """

    group_order: tuple[str, ...] = ()
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    custom: dict[str, object] = field(default_factory=dict)


# --- read ------------------------------------------------------------------


def read(text: str) -> MapGroups:
    """Parse ``map_groups.json`` text into a :class:`MapGroups`.

    Raises:
        MapGroupsFormatError: invalid JSON, wrong top-level shape, missing
            ``group_order``, a non-string group symbol or map name, a
            ``null`` entry, or an empty map-name string.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MapGroupsFormatError(f"invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise MapGroupsFormatError(f"top-level value must be an object, got {_typename(raw)}")

    if _GROUP_ORDER_KEY not in raw:
        raise MapGroupsFormatError(f"missing top-level key {_GROUP_ORDER_KEY!r}")

    raw_order = raw[_GROUP_ORDER_KEY]
    if not isinstance(raw_order, list):
        raise MapGroupsFormatError(
            f"{_GROUP_ORDER_KEY!r} must be an array, got {_typename(raw_order)}"
        )

    group_order: list[str] = []
    for i, entry in enumerate(raw_order):
        if not isinstance(entry, str):
            raise MapGroupsFormatError(
                f"{_GROUP_ORDER_KEY}[{i}]: expected string, got {_typename(entry)}"
            )
        if not entry:
            raise MapGroupsFormatError(f"{_GROUP_ORDER_KEY}[{i}]: empty string")
        group_order.append(entry)

    groups: dict[str, tuple[str, ...]] = {}
    for group in group_order:
        if group not in raw:
            # Porymap treats a missing group key as empty; we record it
            # explicitly so the writer round-trips a real "[]" array.
            groups[group] = ()
            continue
        groups[group] = _read_group_array(raw[group], group)

    custom: dict[str, object] = {}
    known: set[str] = {_GROUP_ORDER_KEY, *group_order}
    for key, value in raw.items():
        if key in known:
            continue
        custom[key] = value

    return MapGroups(
        group_order=tuple(group_order),
        groups=groups,
        custom=custom,
    )


def _read_group_array(value: object, group: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise MapGroupsFormatError(f"group {group!r}: expected array, got {_typename(value)}")
    out: list[str] = []
    for i, entry in enumerate(value):
        if entry is None:
            raise MapGroupsFormatError(f"group {group!r}[{i}]: null is not allowed")
        if not isinstance(entry, str):
            raise MapGroupsFormatError(
                f"group {group!r}[{i}]: expected string, got {_typename(entry)}"
            )
        if not entry:
            raise MapGroupsFormatError(f"group {group!r}[{i}]: empty map name")
        out.append(entry)
    return tuple(out)


def _typename(value: object) -> str:
    return type(value).__name__


# --- write -----------------------------------------------------------------


def write(doc: MapGroups) -> str:
    """Serialize a :class:`MapGroups` to canonical Porymap JSON text.

    Produces a 2-space-indented JSON document with a single trailing LF,
    matching what Porymap writes via ``OrderedJson``. Key order: first
    ``group_order``, then each group in that order, then any preserved
    custom keys.
    """
    payload: dict[str, object] = {_GROUP_ORDER_KEY: list(doc.group_order)}
    for group in doc.group_order:
        payload[group] = list(doc.groups.get(group, ()))
    for key, value in doc.custom.items():
        payload[key] = value
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
