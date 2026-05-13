"""Parser/serializer for ``data/maps/<MAP>/map.json``.

Format (per Porymap source: ``Project::loadMapData`` and ``Project::saveMap``
in ``porymap/src/project.cpp``, with the per-event schemas in
``src/core/events.cpp`` and the JSON serializer in ``src/lib/orderedjson.cpp``):

A ``map.json`` is a single JSON object. Top-level keys are written in this
**canonical order** (Porymap uses ``OrderedJson``; insertion order is
preserved on dump):

    1.  id
    2.  name
    3.  layout
    4.  music
    5.  region_map_section
    6.  requires_flash
    7.  weather
    8.  map_type
    9.  allow_cycling                  (only if enable_map_allow_flags)
    10. allow_escaping                 (only if enable_map_allow_flags)
    11. allow_running                  (only if enable_map_allow_flags)
    12. show_map_name
    13. floor_number                   (only if enable_floor_number)
    14. battle_scene
    15. connections                    (array, OR null when empty)
    16. shared_events_map              (only when inheriting events)
    17. shared_scripts_map             (only when inheriting scripts)
    18. object_events                  (omitted when inheriting events)
    19. warp_events                    (omitted when inheriting events)
    20. coord_events                   (omitted when inheriting events)
    21. bg_events                      (omitted when inheriting events)
    + any custom top-level keys, appended verbatim at the tail.

Per-event field shapes vary by event ``type`` and by feature flags in
``porymap.project.cfg`` (``enable_event_clone_object``,
``enable_event_weather_trigger``, ``enable_event_secret_base``,
``enable_hidden_item_quantity``, ``enable_hidden_item_requires_itemfinder``).
This parser stores each event as a plain ``dict[str, object]`` so unknown
fields and feature-flag-gated fields round-trip verbatim. Typed event
dataclasses are intentionally deferred — they will land alongside the L1
mutation tools that need them (``add_warp``, ``add_object_event``, etc.).

Formatting Porymap emits:

    - 2-space indent, ``": "`` after keys, ``,\\n`` between siblings.
    - Insertion-order keys; ``true`` / ``false`` / ``null`` lowercase.
    - Single trailing ``\\n``; LF line endings; UTF-8; no BOM.

Idempotent round-trip: ``write(read(text)) == text`` holds for every
Porymap-emitted ``map.json`` we have seen, including hand-edited files
that omit ``connections`` or use ``connections: []`` (we read both, but
emit ``null`` for empty per Porymap's rule).

References:
  - Porymap reader / writer: ``Project::loadMapData`` and
    ``Project::saveMap`` in ``porymap/src/project.cpp``.
  - Per-event schemas: ``porymap/src/core/events.cpp``.
  - Feature-flag-driven optional fields: ``porymap/src/config.cpp``.
  - pokeemerald canonical fixture:
    https://github.com/pret/pokeemerald/blob/master/data/maps/LittlerootTown/map.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Final

from porymap_mcp.errors import MapJsonFormatError

# --- Canonical key sets ----------------------------------------------------

_REQUIRED_HEADER_KEYS: Final = (
    "id",
    "name",
    "layout",
    "music",
    "region_map_section",
    "requires_flash",
    "weather",
    "map_type",
    "show_map_name",
    "battle_scene",
)

_OPTIONAL_BOOL_HEADER_KEYS: Final = ("allow_cycling", "allow_escaping", "allow_running")

_EVENT_GROUP_KEYS: Final = ("object_events", "warp_events", "coord_events", "bg_events")

_KNOWN_TOP_LEVEL_KEYS: Final = (
    *_REQUIRED_HEADER_KEYS,
    *_OPTIONAL_BOOL_HEADER_KEYS,
    "floor_number",
    "connections",
    "shared_events_map",
    "shared_scripts_map",
    *_EVENT_GROUP_KEYS,
)

_CONNECTION_REQUIRED_KEYS: Final = ("map", "offset", "direction")


# --- Dataclasses -----------------------------------------------------------


@dataclass(slots=True)
class Connection:
    """One entry in the top-level ``connections`` array.

    ``map`` is a destination map *constant* (e.g. ``"MAP_ROUTE101"``).
    ``offset`` is signed: tile offset along the perpendicular axis.
    ``direction`` is the conventional six-value enum
    (``up``/``down``/``left``/``right``/``dive``/``emerge``); Porymap accepts
    any string and so do we.

    ``custom`` preserves any keys outside the canonical three so a read /
    write cycle is byte-stable for hand-edited files.
    """

    map: str
    offset: int
    direction: str
    custom: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MapJson:
    """The decoded ``data/maps/<MAP>/map.json`` document.

    Conditional header fields (``allow_*``, ``floor_number``) are
    ``None`` when absent from the source; the writer emits them only when
    set. Inheritance is modeled the same way: when ``shared_events_map``
    or ``shared_scripts_map`` is set, the corresponding event arrays are
    typically ``None`` (Porymap omits them entirely) — we mirror that
    convention on write.

    Event arrays are stored as ``tuple[dict[str, object], ...]`` to
    round-trip verbatim. Typed event dataclasses will land in a follow-up
    parser when mutation tools need them.

    ``custom`` preserves any unknown top-level keys, appended after the
    canonical block on write.
    """

    id: str
    name: str
    layout: str
    music: str
    region_map_section: str
    requires_flash: bool
    weather: str
    map_type: str
    show_map_name: bool
    battle_scene: str

    # Conditional scalar header fields.
    allow_cycling: bool | None = None
    allow_escaping: bool | None = None
    allow_running: bool | None = None
    floor_number: int | None = None

    # ``connections`` is always present in Porymap output (as ``null`` when
    # empty, as an array otherwise). We accept ``None`` (missing key or
    # JSON null) and an empty tuple as semantically equivalent on input;
    # on output an empty tuple is emitted as ``null`` to match Porymap.
    connections: tuple[Connection, ...] = ()

    # Inheritance + event arrays. ``None`` means "key absent from JSON".
    shared_events_map: str | None = None
    shared_scripts_map: str | None = None
    object_events: tuple[dict[str, object], ...] | None = None
    warp_events: tuple[dict[str, object], ...] | None = None
    coord_events: tuple[dict[str, object], ...] | None = None
    bg_events: tuple[dict[str, object], ...] | None = None

    custom: dict[str, object] = field(default_factory=dict)


# --- read ------------------------------------------------------------------


def read(text: str) -> MapJson:
    """Parse ``map.json`` text into a :class:`MapJson`.

    Permissive on the per-event schema (events are kept as raw dicts) but
    strict on the top-level shape: missing required header keys, wrong
    types on known fields, and malformed connection entries all raise
    :class:`MapJsonFormatError`.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MapJsonFormatError(f"invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise MapJsonFormatError(f"top-level value must be an object, got {_typename(raw)}")

    missing = [k for k in _REQUIRED_HEADER_KEYS if k not in raw]
    if missing:
        raise MapJsonFormatError(f"missing required top-level keys: {', '.join(missing)}")

    doc = MapJson(
        id=_expect_str(raw["id"], "id"),
        name=_expect_str(raw["name"], "name"),
        layout=_expect_str(raw["layout"], "layout"),
        music=_expect_str(raw["music"], "music"),
        region_map_section=_expect_str(raw["region_map_section"], "region_map_section"),
        requires_flash=_expect_bool(raw["requires_flash"], "requires_flash"),
        weather=_expect_str(raw["weather"], "weather"),
        map_type=_expect_str(raw["map_type"], "map_type"),
        show_map_name=_expect_bool(raw["show_map_name"], "show_map_name"),
        battle_scene=_expect_str(raw["battle_scene"], "battle_scene"),
        allow_cycling=_optional_bool(raw, "allow_cycling"),
        allow_escaping=_optional_bool(raw, "allow_escaping"),
        allow_running=_optional_bool(raw, "allow_running"),
        floor_number=_optional_int(raw, "floor_number"),
        connections=_read_connections(raw.get("connections")),
        shared_events_map=_optional_str(raw, "shared_events_map"),
        shared_scripts_map=_optional_str(raw, "shared_scripts_map"),
        object_events=_optional_event_array(raw, "object_events"),
        warp_events=_optional_event_array(raw, "warp_events"),
        coord_events=_optional_event_array(raw, "coord_events"),
        bg_events=_optional_event_array(raw, "bg_events"),
    )

    for key, value in raw.items():
        if key in _KNOWN_TOP_LEVEL_KEYS:
            continue
        doc.custom[key] = value

    return doc


def _read_connections(value: object) -> tuple[Connection, ...]:
    """Parse the ``connections`` field permissively.

    Porymap's own reader silently tolerates non-array values (we have
    observed ``"connections": 0`` in 60+ FRLG map.json files in
    pokeemerald-expansion forks — see CHANGELOG v0.1.0). To stay
    interoperable with Porymap-touched projects, we treat *any*
    non-list, non-null value as an empty connection list. The strict
    writer always emits ``null`` for empty (matching Porymap), so a
    read-then-write cycle normalizes the format.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        # Permissive: an int (``0``) or other scalar means "no connections".
        # Porymap tolerates this; we follow suit. The strict writer will
        # emit ``null`` on the next save, normalizing the file.
        return ()
    out: list[Connection] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise MapJsonFormatError(
                f"connections[{index}]: expected object, got {_typename(entry)}"
            )
        missing = [k for k in _CONNECTION_REQUIRED_KEYS if k not in entry]
        if missing:
            raise MapJsonFormatError(
                f"connections[{index}]: missing required keys: {', '.join(missing)}"
            )
        custom = {k: v for k, v in entry.items() if k not in _CONNECTION_REQUIRED_KEYS}
        out.append(
            Connection(
                map=_expect_str(entry["map"], f"connections[{index}].map"),
                offset=_expect_int(entry["offset"], f"connections[{index}].offset"),
                direction=_expect_str(entry["direction"], f"connections[{index}].direction"),
                custom=custom,
            )
        )
    return tuple(out)


def _optional_bool(raw: dict[str, object], key: str) -> bool | None:
    if key not in raw:
        return None
    return _expect_bool(raw[key], key)


def _optional_int(raw: dict[str, object], key: str) -> int | None:
    if key not in raw:
        return None
    return _expect_int(raw[key], key)


def _optional_str(raw: dict[str, object], key: str) -> str | None:
    if key not in raw:
        return None
    return _expect_str(raw[key], key)


def _optional_event_array(raw: dict[str, object], key: str) -> tuple[dict[str, object], ...] | None:
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, list):
        raise MapJsonFormatError(f"{key!r}: expected array, got {_typename(value)}")
    out: list[dict[str, object]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise MapJsonFormatError(f"{key}[{index}]: expected object, got {_typename(entry)}")
        out.append(entry)
    return tuple(out)


def _expect_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise MapJsonFormatError(f"{key!r}: expected string, got {_typename(value)}")
    return value


def _expect_bool(value: object, key: str) -> bool:
    # ``bool`` must be checked *before* ``int`` (bool is a subclass of int).
    if not isinstance(value, bool):
        raise MapJsonFormatError(f"{key!r}: expected boolean, got {_typename(value)}")
    return value


def _expect_int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MapJsonFormatError(f"{key!r}: expected integer, got {_typename(value)}")
    return value


def _typename(value: object) -> str:
    return type(value).__name__


# --- write -----------------------------------------------------------------


def write(doc: MapJson) -> str:
    """Serialize a :class:`MapJson` to canonical Porymap JSON text.

    Emits keys in Porymap's canonical order, with conditional fields
    skipped when ``None``. ``connections`` is always emitted: as an array
    when non-empty, as JSON ``null`` when empty (matching
    ``Project::saveMap``). 2-space indent, single trailing LF.
    """
    payload: dict[str, object] = {
        "id": doc.id,
        "name": doc.name,
        "layout": doc.layout,
        "music": doc.music,
        "region_map_section": doc.region_map_section,
        "requires_flash": doc.requires_flash,
        "weather": doc.weather,
        "map_type": doc.map_type,
    }
    if doc.allow_cycling is not None:
        payload["allow_cycling"] = doc.allow_cycling
    if doc.allow_escaping is not None:
        payload["allow_escaping"] = doc.allow_escaping
    if doc.allow_running is not None:
        payload["allow_running"] = doc.allow_running
    payload["show_map_name"] = doc.show_map_name
    if doc.floor_number is not None:
        payload["floor_number"] = doc.floor_number
    payload["battle_scene"] = doc.battle_scene
    payload["connections"] = (
        [_connection_to_dict(c) for c in doc.connections] if doc.connections else None
    )
    if doc.shared_events_map is not None:
        payload["shared_events_map"] = doc.shared_events_map
    if doc.shared_scripts_map is not None:
        payload["shared_scripts_map"] = doc.shared_scripts_map
    if doc.object_events is not None:
        payload["object_events"] = list(doc.object_events)
    if doc.warp_events is not None:
        payload["warp_events"] = list(doc.warp_events)
    if doc.coord_events is not None:
        payload["coord_events"] = list(doc.coord_events)
    if doc.bg_events is not None:
        payload["bg_events"] = list(doc.bg_events)
    for key, value in doc.custom.items():
        payload[key] = value

    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _connection_to_dict(conn: Connection) -> dict[str, object]:
    out: dict[str, object] = {
        "map": conn.map,
        "offset": conn.offset,
        "direction": conn.direction,
    }
    for key, value in conn.custom.items():
        out[key] = value
    return out
