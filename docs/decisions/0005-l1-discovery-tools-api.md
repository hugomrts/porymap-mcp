# ADR-0005: L1 discovery tools — MCP API surface

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** mcp-tool-designer (drafted), project owner (sign-off)

---

## Context

Phase 2 (L1 Filesystem) parsers are done. `Project` is the single entrypoint per ADR-0003. Phase doc `docs/phases/phase-2-l1-filesystem.md` §3 froze a list of seven read-only **discovery** tools that the LLM agent must be able to call before any mutation. These signatures will ship as part of `v0.1.0` and are **semver-frozen** the moment the tag goes out: their names, parameter shapes, and return JSON schemas become public API.

Two parsers the phase doc references are still TODO: `parsers/metatiles.py` and `parsers/attributes.py`. They affect `list_metatiles` only. `Project` also lacks a `get_map_json(map_name)` helper that wires `parsers/mapjson.py` to a map name; we need one for `get_map_info` and `list_events`.

The agent's expected workflow is *discover → mutate → re-render*. Every mutation tool requires a paired discovery tool so the model can introspect bounds, names, IDs, and tileset compatibility before writing. The discovery surface is therefore not optional fluff — it is the contract that lets the model plan.

---

## Decision

We ship seven discovery tools in `src/porymap_mcp/tools/discovery.py`, registered on the FastMCP server in `server.py`. Each tool is a thin orchestrator over `Project`. Signatures, return shapes, error contracts, and naming are as specified below.

**One small addition to `Project` ships with this batch:** `Project.get_map_json(map_name: str) -> MapJson` plus a cached `_map_jsons: dict[str, MapJson]`. It is required by two of the seven tools and is purely additive.

**`list_metatiles` ships in this batch but in a "header-only" form** that returns `{tileset_name, kind, c_label, c_label_unverified, metatile_count: int | null, metatiles: []}` with `metatile_count` computed from `metatiles.bin` file size and `metatiles=[]` whenever `parsers/metatiles.py` is not yet present. The shape is frozen now; the metatile entries fill in transparently as soon as the parsers land — additive, non-breaking. Rationale below.

**`list_prefabs` ships and returns `[]`.** The tool name is frozen now so `paint_prefab` can reference it in its description without a follow-up rename.

---

## Per-tool spec

### Convention shared by all seven

- First arg is always `project_path: str` (not `pathlib.Path` — FastMCP serializes `str` cleanly across JSON-RPC; `Path` round-trips inconsistently across MCP clients).
- `project_path` accepts: absolute paths, `~`-prefixed paths (expanded via `Path.expanduser()`), and paths relative to the *MCP server's* cwd (rare but well-defined). Documented in each tool's docstring.
- Every return is a plain `dict[str, Any]`, JSON-serializable. Every return includes a `summary: str` field — one short human sentence the model can paraphrase to the user — and a `project_path: str` field with the resolved absolute path, so the model can chain to subsequent tool calls without re-resolving.
- Errors raised are subclasses of `PorymapMCPError`. The tool layer lets them propagate; FastMCP renders them into structured MCP errors. No raw `Exception` crosses the boundary.

A tiny shared helper, `_load_project(project_path: str) -> Project`, lives at the top of `tools/discovery.py` and centralizes path expansion + `ProjectError` mapping.

---

### 1. `get_project_info`

```python
@mcp.tool()
def get_project_info(project_path: str) -> dict[str, Any]:
    """Return a one-shot snapshot of a pokeemerald-family project.

    Use this as the FIRST call when you start working on an unfamiliar
    project — it tells you which decomp base the project targets, how
    many maps and tilesets it contains, and the absolute paths to the
    three index files you may want to inspect with other tools.

    Args:
      project_path: Filesystem path to the project root (the directory
        that contains ``porymap.project.cfg``). Accepts absolute paths,
        ``~``-prefixed paths, and paths relative to the server's cwd.

    Returns: a dict with keys ``summary``, ``project_path``,
      ``base_game_version`` (one of ``"pokeemerald"``, ``"pokefirered"``,
      ``"pokeruby"``), ``map_count``, ``layout_count``, ``tileset_count``,
      ``primary_tileset_count``, ``secondary_tileset_count``,
      ``config_path``, ``layouts_json_path``, ``map_groups_json_path``.
      All paths absolute POSIX strings.

    Common errors:
      - ``ProjectError``: project root is not a directory, or
        ``porymap.project.cfg`` is missing. Fix: point at the project
        root, or open it in Porymap once to generate the config.
      - ``UnsupportedBaseGameError``: the ``base_game_version`` declared
        in the config is not one we yet support. Carries the declared
        value and the supported list.
    """
```

**Return example:**
```json
{
  "summary": "Project at /home/u/pokeemerald (pokeemerald): 220 maps, 4 layouts, 38 tilesets.",
  "project_path": "/home/u/pokeemerald",
  "base_game_version": "pokeemerald",
  "map_count": 220,
  "layout_count": 4,
  "tileset_count": 38,
  "primary_tileset_count": 4,
  "secondary_tileset_count": 34,
  "config_path": "/home/u/pokeemerald/porymap.project.cfg",
  "layouts_json_path": "/home/u/pokeemerald/data/layouts/layouts.json",
  "map_groups_json_path": "/home/u/pokeemerald/data/maps/map_groups.json"
}
```

**Errors:** `ProjectError`, `UnsupportedBaseGameError`, `ProjectConfigFormatError`, `LayoutsJsonFormatError`, `MapGroupsFormatError`.

**Agent workflow:** "User asks me to edit pokeemerald maps. First I call `get_project_info` to confirm it loads cleanly and learn the base game; then I pick a discovery tool to drill in."

**Test:** Fixture project with a known map/tileset count; assert every field. One additional test asserting `~` expansion works.

---

### 2. `list_maps`

```python
@mcp.tool()
def list_maps(project_path: str) -> dict[str, Any]:
    """List every map registered in ``data/maps/map_groups.json``.

    The agent uses this to translate a fuzzy user request like "edit
    Littleroot" into a canonical ``MAP_LITTLEROOT_TOWN`` identifier
    before calling map-specific tools. Maps are returned in the project's
    canonical group order (matching what Porymap shows in its sidebar).

    Args:
      project_path: project root.

    Returns: ``{summary, project_path, maps: list[Map]}`` where each Map
      has ``name`` (e.g. ``"MAP_LITTLEROOT_TOWN"``), ``group`` (e.g.
      ``"gMapGroup_TownsAndRoutes"``), ``layout_id`` (e.g.
      ``"LAYOUT_LITTLEROOT_TOWN"``) or ``null`` if the map has no
      registered layout (corrupt project), and ``dimensions`` —
      ``{width, height}`` from ``layouts.json``, or ``null`` when the
      layout id cannot be resolved.

    Common errors:
      - ``ProjectError``: missing/unreadable ``map_groups.json`` or
        ``layouts.json``.
      - ``MapJsonFormatError``: per-map ``map.json`` is malformed.
        Carries the map name in the message.
    """
```

**Return example:**
```json
{
  "summary": "Project has 2 maps across 1 group.",
  "project_path": "/home/u/pokeemerald",
  "maps": [
    {
      "name": "MAP_LITTLEROOT_TOWN",
      "group": "gMapGroup_TownsAndRoutes",
      "layout_id": "LAYOUT_LITTLEROOT_TOWN",
      "dimensions": {"width": 20, "height": 20}
    },
    {
      "name": "MAP_ROUTE101",
      "group": "gMapGroup_TownsAndRoutes",
      "layout_id": "LAYOUT_ROUTE101",
      "dimensions": {"width": 30, "height": 20}
    }
  ]
}
```

**Implementation note:** `list_maps` reads each map's `map.json` to recover `layout_id`. `map_groups.json` does not store the layout binding directly. This is one `Project.get_map_json` call per map; cached after first use.

**Errors:** `ProjectError`, `MapJsonFormatError`.

**Agent workflow:** "User says 'put a sign in Littleroot' — I scan `list_maps` results, find the exact constant `MAP_LITTLEROOT_TOWN`, then call `get_map_info`."

**Test:** Fixture with two maps in one group; assert order, names, layout dims.

---

### 3. `get_map_info`

```python
@mcp.tool()
def get_map_info(project_path: str, map_name: str) -> dict[str, Any]:
    """Return full metadata for a single map.

    Call this immediately before any map-mutation tool. It gives the
    map's dimensions (needed to validate ``(x, y)`` for ``paint_*``),
    its tilesets (needed to decide which metatile ids are valid), and
    counts of every event class (so you know whether to follow up with
    ``list_events``). Coordinates inside the map are ``(x, y)`` with
    origin top-left and ``0 <= x < width``, ``0 <= y < height``.

    Args:
      project_path: project root.
      map_name: map constant, e.g. ``"MAP_LITTLEROOT_TOWN"``. Get the
        valid set with ``list_maps``.

    Returns: see ADR-0005. Includes ``dimensions``, ``border_dimensions``,
      ``layout`` (id + tileset refs + on-disk paths), ``header`` (subset of
      ``map.json`` header fields), and ``event_counts``.

    Common errors:
      - ``MapNotFoundError``: ``map_name`` does not appear in any group.
        Fix: call ``list_maps`` for the canonical spelling.
      - ``ProjectError``: layout id referenced by the map is not in
        ``layouts.json``.
      - ``MapJsonFormatError``: this map's ``map.json`` is malformed.
    """
```

**Return example:**
```json
{
  "summary": "MAP_LITTLEROOT_TOWN: 20x20, layout LAYOUT_LITTLEROOT_TOWN, 3 warps, 5 objects.",
  "project_path": "/home/u/pokeemerald",
  "map_name": "MAP_LITTLEROOT_TOWN",
  "group": "gMapGroup_TownsAndRoutes",
  "dimensions": {"width": 20, "height": 20},
  "border_dimensions": {"width": 2, "height": 2},
  "layout": {
    "id": "LAYOUT_LITTLEROOT_TOWN",
    "name": "Littleroot_Town_Layout",
    "primary_tileset": "gTileset_General",
    "secondary_tileset": "gTileset_LittlerootTown",
    "blockdata_filepath": "data/layouts/LittlerootTown/map.bin",
    "border_filepath": "data/layouts/LittlerootTown/border.bin"
  },
  "header": {
    "music": "MUS_LITTLEROOT",
    "region_map_section": "MAPSEC_LITTLEROOT_TOWN",
    "weather": "WEATHER_SUNNY",
    "map_type": "MAP_TYPE_TOWN",
    "requires_flash": false,
    "show_map_name": true,
    "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
    "allow_cycling": true,
    "allow_escaping": false,
    "allow_running": true,
    "floor_number": null
  },
  "event_counts": {
    "object_events": 5,
    "warp_events": 3,
    "coord_events": 0,
    "bg_events": 2,
    "total": 10
  },
  "connection_count": 2,
  "inherits_events_from": null,
  "inherits_scripts_from": null
}
```

**Granularity rule:** `get_map_info` returns event **counts**, never the event arrays themselves. Rationale: a busy map can easily have 50+ events with verbose script fields; a single tool returning everything makes every "what map is this?" call expensive in context. The model calls `list_events(map_name)` when it wants details. This split matches the phase doc.

**Errors:** `ProjectError`, `MapNotFoundError`, `MapJsonFormatError`, `LayoutsJsonFormatError`.

**Agent workflow:** "I'm about to paint at (3,4) — first call `get_map_info` to confirm the map is 20x20 (in bounds) and which tilesets are loaded."

**Test:** Fixture map with a known mix of events; assert dimensions, tileset c-labels, every count, and `inherits_events_from` populated on an inherited map.

---

### 4. `list_tilesets`

```python
@mcp.tool()
def list_tilesets(project_path: str) -> dict[str, Any]:
    """List every tileset discovered on disk.

    Returns both primary (background-shared) and secondary (map-specific)
    tilesets. The agent uses this to pick a ``primary_tileset`` /
    ``secondary_tileset`` pair when calling ``create_map``, or to look up
    a tileset's metatile count before ``list_metatiles``.

    Note on ``c_label_unverified``: per ADR-0004 stage 1, the C symbol
    is derived from the directory name via convention and may not match
    a fork's actual ``headers.h``. Treat ``c_label_unverified=true`` as
    "probably right, but cross-check with ``layouts.json`` before using
    in mutation tools".

    Args:
      project_path: project root.

    Returns: ``{summary, project_path, tilesets: list[Tileset]}`` —
      each Tileset has ``name`` (directory basename), ``c_label``
      (e.g. ``"gTileset_General"``), ``c_label_unverified`` (bool),
      ``is_primary`` (bool), ``kind`` (``"primary"`` | ``"secondary"``),
      ``metatile_count`` (int) or ``null`` if ``metatiles.bin`` is
      missing, and ``paths`` (``tiles``, ``metatiles``, ``attributes``,
      ``palettes`` — POSIX relative to project root).

    Common errors:
      - ``ProjectError``: ``data/tilesets/`` is missing entirely.
    """
```

**Return example:**
```json
{
  "summary": "Project has 38 tilesets (4 primary, 34 secondary).",
  "project_path": "/home/u/pokeemerald",
  "tilesets": [
    {
      "name": "general",
      "c_label": "gTileset_General",
      "c_label_unverified": true,
      "is_primary": true,
      "kind": "primary",
      "metatile_count": 512,
      "paths": {
        "tiles": "data/tilesets/primary/general/tiles.png",
        "metatiles": "data/tilesets/primary/general/metatiles.bin",
        "attributes": "data/tilesets/primary/general/metatile_attributes.bin",
        "palettes": "data/tilesets/primary/general/palettes"
      }
    }
  ]
}
```

**Metatile count source:** Until `parsers/metatiles.py` lands, `metatile_count` is computed from `metatiles.bin` file size — every metatile is 16 bytes regardless of base game (8 tile-words × 2 bytes). This is a cheap stat-and-divide; no parser needed. If `metatiles.bin` is missing the value is `null` (not an error — a fork might omit it).

**Errors:** `ProjectError`.

**Agent workflow:** "I'm calling `create_map` — need to pick a primary/secondary pair. `list_tilesets` gives me valid `c_label` strings I can pass through verbatim."

**Test:** Fixture with 1 primary + 1 secondary tileset; assert both appear, sort order is `(kind, name)`, `metatile_count` correctly computed from synthetic `metatiles.bin`.

---

### 5. `list_metatiles`

```python
@mcp.tool()
def list_metatiles(project_path: str, tileset_name: str) -> dict[str, Any]:
    """List the metatiles in a single tileset.

    Returns one entry per metatile id in the tileset, with the metatile's
    decoded attributes (behavior, layer type, encounter type, terrain
    type — exact set depends on ``base_game_version``). Does NOT return
    rendered images; that's a Phase 4 (L3) capability.

    Pagination: not paginated. A primary tileset has at most 512
    metatiles, a secondary at most ~1024 in expansion projects, payload
    well under 100 KB — within MCP comfort.

    Args:
      project_path: project root.
      tileset_name: directory basename (NOT C label). Get the valid set
        with ``list_tilesets``. Example: ``"general"``, not
        ``"gTileset_General"``.

    Returns: ``{summary, project_path, tileset_name, kind, c_label,
      metatile_count, metatiles: list[Metatile]}`` where each Metatile is
      ``{id: int, attributes: {behavior, layer_type, encounter_type,
      terrain_type, ...}}``. Attribute keys present depend on what the
      project's masks expose — every key is non-null when present.
      During the L1 prerelease (``parsers/metatiles.py`` not yet
      shipped), ``metatiles`` is an empty list and ``metatile_count``
      is the file-size-derived count; this is forward-compatible.

    Common errors:
      - ``ProjectError``: ``tileset_name`` does not match any directory
        under ``data/tilesets/{primary,secondary}/``. Fix: call
        ``list_tilesets`` to enumerate valid names.
      - ``FormatError``: ``metatiles.bin`` or
        ``metatile_attributes.bin`` is corrupt (wrong size, etc.).
    """
```

**Return example (after metatile parsers land):**
```json
{
  "summary": "Tileset 'general' (primary): 512 metatiles.",
  "project_path": "/home/u/pokeemerald",
  "tileset_name": "general",
  "kind": "primary",
  "c_label": "gTileset_General",
  "metatile_count": 512,
  "metatiles": [
    {
      "id": 0,
      "attributes": {
        "behavior": "MB_NORMAL",
        "layer_type": "METATILE_LAYER_TYPE_NORMAL",
        "encounter_type": "TILE_ENCOUNTER_NONE",
        "terrain_type": "TILE_TERRAIN_NORMAL"
      }
    }
  ]
}
```

**Prerelease return (before parsers):** identical shape, with `metatiles: []`. The model can still discover the count via this tool — useful for picking valid id ranges.

**Argument naming:** `tileset_name` (directory basename), not `tileset_label` (C symbol). Reason: filesystem names are stable and verified; C labels are heuristic per ADR-0004 stage 1. We accept name throughout this tool; if the model has only a c_label from `layouts.json`, it can map via `list_tilesets`.

**Errors:** `ProjectError`, `FormatError` (specifically a future `MetatileFormatError` / `AttributesFormatError`).

**Agent workflow:** "I want to paint grass. `list_metatiles('general')` shows me the id with `behavior=MB_TALL_GRASS`. I copy the id into `paint_metatile`."

**Test:** Fixture tileset with 4 metatiles of known attributes; assert ids 0-3, exact attribute values. Plus a "no parsers yet" path test that asserts `metatiles=[]` and `metatile_count=4`.

---

### 6. `list_prefabs`

```python
@mcp.tool()
def list_prefabs(project_path: str) -> dict[str, Any]:
    """List named metatile-stamp prefabs available to ``paint_prefab``.

    A prefab is a small 2D block of metatiles (e.g. a generic house, a
    Pokémon Center) that ``paint_prefab`` stamps onto a map. In v0.1.0
    no prefabs ship; this tool returns ``{"prefabs": []}`` for now.
    The tool exists so ``paint_prefab`` has a discovery pair from day
    one, and so the v0.1.0 → v0.2.0 transition adds prefabs without
    introducing a new tool name.

    Args:
      project_path: project root.

    Returns: ``{summary, project_path, prefabs: list[Prefab]}`` — each
      Prefab has ``name``, ``width``, ``height``,
      ``tileset_requirements: {primary: str|null, secondary: str|null}``,
      and ``description`` (one-sentence prose). v0.1.0 returns an empty
      list.

    Common errors: none for v0.1.0 (always succeeds with an empty list).
    """
```

**Return example (v0.1.0):**
```json
{
  "summary": "No prefabs are bundled in this version of porymap-mcp.",
  "project_path": "/home/u/pokeemerald",
  "prefabs": []
}
```

**Why ship empty rather than defer:** ergonomically, an empty list with a clear `summary` teaches the model "this server has no prefabs, do not call `paint_prefab`". Deferring would mean `paint_prefab` has no discovery pair when it ships, violating the discovery-before-mutation principle. The cost of shipping an empty list now is zero.

**Errors:** `ProjectError` (only if `project_path` itself is invalid — propagated by `_load_project`).

**Agent workflow:** "User says 'add a Pokémon Center'. I call `list_prefabs`. Empty list → I fall back to `paint_rectangle` with raw metatile ids from `list_metatiles`."

**Test:** Call against any valid fixture; assert `prefabs == []` and `summary` mentions "no prefabs".

---

### 7. `list_events`

```python
@mcp.tool()
def list_events(project_path: str, map_name: str) -> dict[str, Any]:
    """List every event on a map, grouped by class.

    Returns all four event classes Porymap recognizes: ``object_events``
    (NPCs, items, statics), ``warp_events`` (teleports), ``coord_events``
    (script triggers fired by stepping on a tile), and ``bg_events``
    (signs + hidden items). Each event is returned as its raw map.json
    dict — keys depend on event ``type`` and on project feature flags.

    Event ids: each event gets a stable ``_event_id`` field assigned by
    this tool (NOT stored in ``map.json``). The id has the form
    ``"<class>:<index>"`` (e.g. ``"object_events:3"``). Event-mutation
    tools (``remove_event``) accept this id verbatim. Note: ids shift
    when events are inserted/removed — call ``list_events`` again after
    any mutation; do not cache ids across mutations.

    Args:
      project_path: project root.
      map_name: map constant. Get from ``list_maps``.

    Returns: ``{summary, project_path, map_name, inherits_events_from,
      object_events, warp_events, coord_events, bg_events}``. When the
      map inherits its events (``shared_events_map`` set in map.json),
      ``inherits_events_from`` is the source map name and the four
      event arrays are empty.

    Common errors:
      - ``MapNotFoundError``: ``map_name`` not registered. Fix:
        ``list_maps`` for the canonical spelling.
      - ``MapJsonFormatError``: malformed ``map.json``.
    """
```

**Return example:**
```json
{
  "summary": "MAP_LITTLEROOT_TOWN: 5 objects, 3 warps, 0 coord, 2 bg.",
  "project_path": "/home/u/pokeemerald",
  "map_name": "MAP_LITTLEROOT_TOWN",
  "inherits_events_from": null,
  "object_events": [
    {"_event_id": "object_events:0", "graphics_id": "OBJ_EVENT_GFX_MOM",
     "x": 8, "y": 5, "elevation": 3, "movement_type": "MOVEMENT_TYPE_LOOK_AROUND",
     "movement_range_x": 0, "movement_range_y": 0,
     "trainer_type": "NONE", "trainer_sight_or_berry_tree_id": "0",
     "script": "LittlerootTown_EventScript_Mom",
     "flag": "FLAG_HIDE_LITTLEROOT_TOWN_MOM"}
  ],
  "warp_events": [
    {"_event_id": "warp_events:0", "x": 2, "y": 3, "elevation": 0,
     "dest_map": "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F",
     "dest_warp_id": "0"}
  ],
  "coord_events": [],
  "bg_events": []
}
```

**Why raw dicts:** `parsers/events.py` (typed event dataclasses) is deliberately deferred until the first event-*mutation* tool needs them. For discovery, raw dicts are honest: they round-trip feature-flag-gated fields the model may legitimately need to see (`local_id`, `quantity`, `underfoot`). When typed events land, this tool's contract is "every key currently in the raw dict is still present" — additive.

**Errors:** `ProjectError`, `MapNotFoundError`, `MapJsonFormatError`.

**Agent workflow:** "User says 'delete the sign in front of the house'. I call `list_events`, find the `bg_events` entry at the right coords, grab its `_event_id`, and pass it to `remove_event` (Phase 2 mutation tool, not part of this batch)."

**Test:** Fixture map with one event of each class; assert all four arrays populated, every `_event_id` formatted correctly, inherited-map case returns empty arrays + populated `inherits_events_from`.

---

## Path handling

We accept `project_path: str` everywhere, normalize via `Path(project_path).expanduser().resolve()` in `_load_project`. Three reasons:

1. **MCP JSON-RPC serializes strings cleanly; `Path` does not.** FastMCP can coerce `Path` from a string, but the resulting JSON schema is opaque to non-Python clients.
2. **`~` expansion is non-negotiable.** Agents routinely receive paths like `~/code/pokeemerald` from users; rejecting them would force the model into a `realpath`-style preamble.
3. **Relative-to-cwd paths** are quietly supported (just `Path(...).resolve()`), but the docstring does not encourage them — users may run the MCP server from anywhere.

We push back on accepting `pathlib.Path` directly: type-hint complexity for JSON-schema generation isn't worth it for one parameter.

---

## Error contract summary

| Tool | Errors raised | Recovery hint embedded in message |
|---|---|---|
| `get_project_info` | `ProjectError`, `UnsupportedBaseGameError`, `ProjectConfigFormatError` | "Open the project once in Porymap to generate `porymap.project.cfg`." |
| `list_maps` | `ProjectError`, `MapJsonFormatError` | Format error message includes offending map name. |
| `get_map_info` | `MapNotFoundError`, `ProjectError`, `MapJsonFormatError`, `LayoutsJsonFormatError` | `MapNotFoundError` → "Call `list_maps` for valid names." |
| `list_tilesets` | `ProjectError` | "`data/tilesets/` missing." |
| `list_metatiles` | `ProjectError`, future `MetatileFormatError` | "Call `list_tilesets` for valid `tileset_name` values." |
| `list_prefabs` | `ProjectError` (only if project itself bad) | — |
| `list_events` | `MapNotFoundError`, `MapJsonFormatError` | "Call `list_maps` for valid names." |

**No new error classes are required.** Existing hierarchy (`ProjectError`, `UnsupportedBaseGameError`, `FormatError` family, `MapNotFoundError`) covers every failure mode. `CoordinatesOutOfBoundsError` is unused by discovery tools (no coordinate inputs).

`MetatileFormatError` and `AttributesFormatError` (both `FormatError` subclasses) will be added when `parsers/metatiles.py` / `parsers/attributes.py` land — out of scope for this ADR.

---

## Naming sanity check

Tested each name against the principles in `mcp-tool-designer`'s mandate (verb-first, unambiguous, matches Porymap's vocabulary):

| Name | Verdict |
|---|---|
| `get_project_info` | Keep. `describe_project` was considered but `get_*` is the established MCP idiom for "fetch this resource as a dict" and pairs naturally with future `get_map_info`. |
| `list_maps` | Keep. Matches Porymap's "Maps" sidebar. |
| `get_map_info` | Keep. Symmetric with `get_project_info`; "info" honestly signals "metadata, not contents". |
| `list_tilesets` | Keep. |
| `list_metatiles` | Keep. Note `tileset_name` (basename) vs `tileset_label` (C symbol) ambiguity is resolved in-docstring. |
| `list_prefabs` | Keep. Empty-now, populated-later. |
| `list_events` | Keep. Matches Porymap's "Events" panel. |

No renames. The `list_*` / `get_*` split is consistent: `list_*` returns a collection, `get_*` returns one rich record.

---

## Alternatives considered

### Alternative 1 — Defer `list_metatiles` until parsers land
- **Upside:** No "header-only stub" awkwardness; tools always return their full contract.
- **Downside:** Forces a v0.1.0 ship without `list_metatiles`, then a tool-addition in v0.2.0 — minor version bump for a tool that should have been in the L1 floor. Also delays freezing the return shape, risking incompatible re-design later.
- **Why not:** The "header-only stub" pattern is strictly additive — `metatile_count` is real and useful (computed from file size), `metatiles: []` is honest. We get the name and shape frozen now, fill in the array later without breaking anyone.

### Alternative 2 — Fold `list_events` into `get_map_info`
- **Upside:** Fewer tools; the model gets everything in one call.
- **Downside:** A single map with 50+ events with multi-line scripts can balloon `get_map_info` to 30+ KB, paid by every call regardless of whether the agent needs event details.
- **Why not:** Cost asymmetry. The phase doc's split is the right one: `get_map_info` is the cheap orientation call; `list_events` is the deep dive.

### Alternative 3 — Pass `project_path: Path` directly
- **Upside:** Slightly nicer Python typing.
- **Downside:** `Path` serialization in JSON-RPC is client-dependent; `~` expansion isn't built into `Path`; the input type matters for MCP clients that aren't Claude.
- **Why not:** `str` + internal normalization is the safer, more portable choice.

### Alternative 4 — Paginate `list_metatiles`
- **Upside:** Headroom for future huge tilesets.
- **Downside:** Pagination adds two parameters and forces the model to chain calls for a payload that, even worst-case (1024 metatiles × ~120 bytes each = ~120KB), is well within MCP comfort.
- **Why not:** Premature optimization. If a real project blows the budget, we add an opt-in `id_range: tuple[int, int]` filter — additive, non-breaking.

### Alternative 5 — Defer `list_prefabs` until prefabs exist
- **Upside:** Don't ship a tool that does nothing.
- **Downside:** When prefabs land in (say) v0.3.0, adding `list_prefabs` is a tool addition, and `paint_prefab` (shipping in v0.1.0) lacks its discovery pair for two minor versions.
- **Why not:** A 3-line tool that returns `[]` is cheap insurance.

---

## Consequences

- **Positive:**
  - All seven tools are spec-frozen and can ship in v0.1.0 alongside the mutation tools.
  - No new error classes required; the existing hierarchy carries every failure mode.
  - Return shapes are forward-compatible: `metatiles: []` fills in transparently when parsers land; `_event_id` is stable across the typed-events migration; `list_prefabs` becomes useful without a rename.
  - Discovery-before-mutation principle is fully honored: every planned L1 mutation tool has a paired discovery tool from day one.

- **Negative:**
  - `list_metatiles` and `list_prefabs` ship in stub form. We must remember to flesh them out without subtly changing the contract — a test asserting the JSON schema today vs. tomorrow would help.
  - `list_events`'s synthesized `_event_id` is not stable across mutations (a remove shifts indices). This is documented but the model can still trip over it if it caches.

- **Neutral:**
  - One `Project` addition: `get_map_json(map_name) -> MapJson` with cache. Pure additive.
  - All seven tools live in `src/porymap_mcp/tools/discovery.py`. Server registration in `server.py`.

---

## Open questions (deferred)

- **OQ-A — Event id stability.** Synthesized `<class>:<index>` ids shift on mutation. Should we instead require every event to carry a real id (synthesizing one and writing it back to `map.json` on first encounter)? Defer to the ADR that introduces the first event mutation tool (`add_warp` / `remove_event`).
- **OQ-B — Attribute key set in `list_metatiles`.** Exact keys depend on the masks in `porymap.project.cfg` and the base game. We commit to a *minimum* set (`behavior`, `layer_type`, `encounter_type`, `terrain_type`) and let other keys come along as the parsers expose them. The "minimum set" contract gets formalized when `parsers/attributes.py` ships.
- **OQ-C — `c_label` verification.** Tools report `c_label_unverified=true` per ADR-0004 stage 1. When stage 2 ships, do we silently flip the flag, or add a `verified_against: "headers.h" | "convention"` field? Defer to ADR-0004 stage 2.
- **OQ-D — `connections` exposure.** `get_map_info` returns `connection_count` but not the connections themselves. If the agent needs them (e.g. to lay out a route adjacent to a town), should we add `list_connections` or fold them into `get_map_info`? Defer until a connection-mutation tool is on the table.
- **OQ-E — Performance of `list_maps`.** Reading every `map.json` for `layout_id` resolution is O(maps). Vanilla pokeemerald has 220 maps; that's 220 small JSON reads, well under a second on any disk. If a fork explodes this, add a `Project.list_maps_lazy()` that skips the layout-id lookup. Not a problem today.
- **OQ-F — `_event_id` prefix collision.** Using `_event_id` (leading underscore) signals "synthesized, not from the file"; a user manually adding an `_event_id` key would collide. Defer; we can rename to `__porymap_mcp_event_id__` if it ever becomes a real problem.

---

## References

- Related ADRs: ADR-0003 (Project class + config-driven format), ADR-0004 (tileset metadata source).
- Phase doc: `docs/phases/phase-2-l1-filesystem.md` §3 (frozen tool surface), §7 step 3.
- Project conventions: `CLAUDE.md` §5 (MCP tool design rules).
- Source surfaces consulted: `src/porymap_mcp/project.py`, `src/porymap_mcp/errors.py`, `src/porymap_mcp/parsers/{mapjson,layoutsjson,tileset,mapgroups,projectconfig}.py`.
