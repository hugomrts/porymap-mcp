# ADR-0006: L1 mutation tools — MCP API surface

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** mcp-tool-designer (drafted), project owner (sign-off)

---

## Context

Phase 2 (L1 Filesystem) is in progress. The seven read-only discovery tools were frozen in ADR-0005 and ship in `tools/discovery.py`. The phase doc `docs/phases/phase-2-l1-filesystem.md` §3 also lists the *mutation* tools that complete the L1 floor. This ADR freezes the surface for the eight that do not depend on a prefab library or a typed-events parser:

- Map layout mutation: `paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`, `create_map`, `resize_map`.
- Project structure mutation: `register_map`, `unregister_map`.

`paint_prefab` and the four event-mutation tools (`add_warp`, `add_object_event`, `add_sign`, `add_trigger`, `remove_event`) are out of scope and will be specified in a follow-up ADR once their respective prerequisites (a prefab library; `parsers/events.py`) exist.

These signatures will ship as part of `v0.1.0` and are **semver-frozen** the moment the tag goes out: names, parameter shapes, and return JSON schemas become public API. The mandate from CLAUDE.md §5 governs: idempotent where possible, `(x, y)` top-left, `project_path` first, structured returns, side-effects listed, `PorymapMCPError` subclasses only across the boundary.

The `Project` class (ADR-0003) already exposes every primitive these tools need: `read_map_bin` / `write_map_bin`, `read_border_bin`, `get_layout`, `get_map_entry`, `save_layouts`, `save_map_groups`, plus the cached map-json store. The mutation tools are thin orchestrators on top.

---

## Decision

We ship eight mutation tools in two modules, registered on the FastMCP server in `server.py`:

- `src/porymap_mcp/tools/maps.py` — `paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`, `create_map`, `resize_map`.
- `src/porymap_mcp/tools/projects.py` — `register_map`, `unregister_map`.

Each tool is a thin orchestrator over `Project` and the parsers. Signatures, return shapes, error contracts, and naming are as specified below.

**Two small additions to `Project` ship with this batch:**

1. `Project.write_border_bin(layout_id: str, layout: MapBin) -> None` — symmetric with `write_map_bin`, validates border dimensions against the layout entry.
2. `Project.find_bare_by_map_id(map_name: str) -> str | None` — scans `data/maps/*/map.json` for `id == map_name`, *without* requiring the map to be registered in `map_groups.json`. Needed by `register_map`. Pure additive.

No new error classes. The existing hierarchy (`ProjectError`, `MapNotFoundError`, `CoordinatesOutOfBoundsError`, `FormatError` family) covers every failure mode in this batch.

---

## Cross-cutting decisions

These bind every tool in this ADR. Per-tool specs assume them.

### CC-1. Idempotence contract

> **Rule:** "Same args, same starting state → same ending state, no observable side-effect on second call." Phrased operationally: re-running a tool with identical arguments must not modify any file whose content would already be identical after the first run.

- **Implementation:** every mutation tool computes its target byte-stream in memory, then compares against the on-disk bytes (cheap `read_bytes()` vs. `new_bytes` equality for `.bin`; in-memory dataclass equality for parsed JSON). If equal, *skip the write entirely* — `files_modified` is `[]` and `summary` reports "no change".
- **Why skip the write:** file mtime stability matters for L2 (filesystem-watcher hot-reload). A re-painted-identical tile that bumps mtime would force Porymap to reload the layout for no reason.
- **For `create_map`:** duplicate names are a hard error (`ProjectError`), not a no-op. Rationale: creation has many parameters (dimensions, tilesets, fill id); a "create-or-merge" semantics would be ambiguous — does the caller want to update dimensions on an existing map? Clear error is safer.
- **For `register_map`:** if the map is already registered in the *requested* group → no-op success (true idempotence, `files_modified: []`). If registered in a *different* group → `ProjectError` with both group names in the message — never silently move.
- **For `unregister_map`:** if the map is already absent from every group → no-op success (true idempotence).

The `summary` field always tells the truth — "no change" vs. "painted N tiles". The model can detect the no-op via `files_modified == []` for chaining decisions.

### CC-2. `collision=None` / `elevation=None` preserve semantics

`paint_metatile`, `paint_rectangle`, and `flood_fill` accept optional `collision: int | None = None` and `elevation: int | None = None`. `None` means "preserve the existing value at this tile". A concrete int (0..3 / 0..15) means "set to this value".

- **For `paint_rectangle` / `flood_fill`:** `None` preserves each affected tile's *own* prior value (not a single uniform value). The rectangle's tiles keep their pre-existing collision/elevation grid; only `metatile_id` is unified.
- **Validation:** `collision in {0,1,2,3}` and `elevation in {0..15}` (per mapbin format). Out-of-range → `ProjectError` with the valid range.
- **Summary text:** mentions preservation explicitly when relevant, e.g. `"Painted metatile 0x042 at (3, 4) on MAP_LITTLEROOT_TOWN; preserved collision=0, elevation=3."`. Lets the model echo to the user without an extra `get_map_info` call.

### CC-3. `files_modified` response field

Every mutation tool's return dict includes:

```
"files_modified": ["data/layouts/LittlerootTown/map.bin", ...]
```

- **Format:** POSIX-relative paths from the project root. Stable across OSes; matches how `layouts.json` already stores filepaths.
- **Stable order:** lexical sort, so two equivalent calls produce byte-identical responses (helps tests, golden files, and the model's diff reasoning).
- **No-op:** when nothing changed (CC-1 short-circuit), `files_modified: []`.
- **Multi-file calls:** every file actually touched is listed. `create_map`'s typical return is five entries.

We *also* include `project_path: str` (resolved absolute) in every response, matching ADR-0005's convention so the model can chain without re-resolving.

### CC-4. Bounds and validation

- **`(x, y)` validation:** every coordinate input is validated against `layout.width × layout.height` (or `border_width × border_height` for `set_border`). Out of bounds → `CoordinatesOutOfBoundsError`, which already carries the dimensions in its message.
- **Rectangle bounds:** strict — `paint_rectangle` requires `x1 <= x2 and y1 <= y2`. Reversed coordinates raise `ProjectError("paint_rectangle: x1=5 > x2=3; provide coordinates as (top-left, bottom-right) with x1<=x2 and y1<=y2")`. Auto-swapping was rejected because it hides typos.
- **Metatile id:** validated against the *encoding bit field* (0..0x3FF) via `mapbin.Tile.__post_init__`. We do **not** validate that the id is within the project's primary+secondary tileset metatile count. Rationale: validating-against-tileset is parser work that hasn't landed (`parsers/metatiles.py`), and a "high" id can be legitimate for forks that grow their tilesets. The model already has `list_metatiles` to discover the right range. If `Tile.__post_init__` raises, we re-raise as `ProjectError("metatile_id 0x500 out of encoding range 0..0x3FF (10 bits). Use list_metatiles to enumerate the tileset.")`.
- **Collision / elevation:** validated as above (CC-2).
- **`set_border(metatile_ids)`:** must be exactly `border_height` rows of `border_width` cols. Mismatch → `ProjectError("border dimension mismatch: layout declares 2x2, got 3 rows of 2 cols. Use get_map_info to read border_dimensions.")`.

### CC-5. `create_map` conventions

Naming, defaults, and file touches are frozen here so forks can rely on them.

**Naming convention (hard rule).** The `name` argument is the **bare PascalCase** form (e.g. `"LittlerootTown"`). From it we derive:

- MAP constant: `MAP_LITTLEROOT_TOWN` (PascalCase split into SCREAMING_SNAKE).
- Layout id: `LAYOUT_LITTLEROOT_TOWN`.
- Layout `name` field: `LittlerootTown_Layout`.
- Directories: `data/maps/LittlerootTown/`, `data/layouts/LittlerootTown/`.

We accept *only* the bare form, not the `MAP_*` constant, because the bare form is the canonical filesystem name and the constants are derived. Passing a `MAP_*` constant raises `ProjectError("create_map: 'name' must be the bare PascalCase form (e.g. 'LittlerootTown'), not the MAP_* constant.")`. This rule is the single source of truth — every derivation in this tool follows from it.

**File touches (commit order — see CC-7):**

1. `data/layouts/<bare>/map.bin` — `width × height × 2` bytes, every tile = `(fill_metatile_id, 0, 0)`.
2. `data/layouts/<bare>/border.bin` — `border_width × border_height × 2` bytes (default 2×2 unless `use_custom_border_size=1`), every tile = `(fill_metatile_id, 0, 0)`.
3. `data/maps/<bare>/map.json` — minimum-viable header (see defaults below).
4. `data/layouts/layouts.json` — new entry appended.
5. `data/maps/map_groups.json` — `map_name` appended to `group` (created if missing — see below).

**Defaults for `map.json`:**

| Field | Default |
|---|---|
| `id` | `MAP_<SNAKE>` |
| `name` | `<bare>` |
| `layout` | `LAYOUT_<SNAKE>` |
| `music` | `MUS_NONE` |
| `region_map_section` | `MAPSEC_NONE` |
| `requires_flash` | `false` |
| `weather` | `WEATHER_NONE` |
| `map_type` | `MAP_TYPE_TOWN` |
| `allow_cycling` | `true` |
| `allow_escaping` | `false` |
| `allow_running` | `true` |
| `show_map_name` | `true` |
| `floor_number` | `0` |
| `battle_scene` | `MAP_BATTLE_SCENE_NORMAL` |
| `connections` | `[]` |
| `object_events`, `warp_events`, `coord_events`, `bg_events` | `[]` |

Defaults are deliberately bland so the model is encouraged to override them via `header_overrides` (a `dict[str, Any]` kwarg whose keys merge over the defaults). Unknown header keys pass through unchanged so forks with extra fields are not blocked.

**Group handling.** If `group` does not yet exist in `map_groups.json`, it is *created* (appended to `group_order`, fresh empty list). Rationale: creating a single new map in a new group is an extremely common Phase 2 task, and forcing the model to call a separate "create group" tool first is friction without payoff. The behavior is logged in `summary` ("created group 'gMapGroup_NewTown' and added MAP_NEWTOWN").

**`include/constants/map_groups.h`.** Per phase doc §8 OQ2, this file is auto-generated by `pret` build scripts from `map_groups.json`. We do **not** touch it. If a fork has disabled auto-generation, that fork must regenerate manually after `create_map`. This is documented in the tool's docstring with a one-liner.

**Layout `name` collisions.** If `LAYOUT_<SNAKE>` already exists in `layouts.json`, `create_map` errors with `ProjectError("layout id LAYOUT_FOO already exists. Pick a different map name, or use register_map to attach an existing layout to a new map.")`.

### CC-6. `resize_map` design

- **Anchor:** `"top-left"` only in v0.1.0. Other anchors (`"center"`, `"top-right"`, ...) are deferred — the parameter exists so we can extend without a breaking change. Passing any other value raises `ProjectError("resize_map: anchor 'center' not supported in v0.1.0; only 'top-left'")`.
- **New cells fill:** `fill_metatile_id: int = 0`, with `collision=0, elevation=0` always. Picking the actual border tile (border.bin[0][0]) was tempting but couples two concepts (border-frame vs. map-interior fill); cleaner to expose explicit control.
- **Shrinking — events:** if the new dimensions exclude an existing event, **error** (refuse the destructive op). The message lists every orphaned event with class, index, and current `(x, y)`. Rationale: destructive operations need explicit consent. The model can call `remove_event` (future tool) or re-call `resize_map` with larger dims. We do not offer a `force=True` bypass in v0.1.0 — if the use case appears, add it then (additive).
- **Shrinking — connections:** out-of-scope-of-content connections are *not* automatically rewritten; they pass through unchanged. The model is responsible for updating them. (Connection mutation tools are future work; for now this is the honest behavior.)
- **Layout shared by multiple maps.** If the layout being resized is referenced by more than one map (rare but legal in pokeemerald), `resize_map` validates the orphaned-events check against **every** map that references the layout. The error message lists which map each orphaned event belongs to.

### CC-7. Multi-file write atomicity

We adopt **Strategy B**: best-effort sequential atomic writes, in a fixed order designed so that an interrupted run leaves either a fully-applied change or *orphaned content that doesn't break discovery*.

**Order for `create_map`:**

1. `data/layouts/<bare>/map.bin` (new file).
2. `data/layouts/<bare>/border.bin` (new file).
3. `data/maps/<bare>/map.json` (new file).
4. `data/layouts/layouts.json` (appended entry).
5. `data/maps/map_groups.json` (appended entry).

**Why this order:** every file before step 4 is unreferenced by any index, so a crash between any of (1)-(3) leaves orphan files that future calls can detect (`register_map` will see them) but does not corrupt the on-disk indexes. A crash between (4) and (5) leaves a registered layout with no map — the next `list_maps` call surfaces the inconsistency clearly because no group references it. Across the boundary, `Project.save_layouts()` already uses `write_atomic_text` (rename), so each individual step is atomic; the only window is *between* steps.

**Order for `register_map`:** single file (`map_groups.json`) — already atomic.

**Order for `unregister_map`:** single file (`map_groups.json`).

**Order for `resize_map`:** `map.bin` then `border.bin` (if border resized too) then `layouts.json` (new width/height). If a crash happens between `map.bin` write and `layouts.json` update, `Project.read_map_bin` will fail loudly on the next call (size mismatch) — recoverable but visible. We document this and recommend the agent re-run the operation on failure.

A true transactional context manager is deferred. We re-evaluate if we see real corruption in the wild.

### CC-8. Tool layout and shared helpers

- Modules: `tools/maps.py` and `tools/projects.py`. The `_load_project(project_path: str) -> Project` helper from `tools/discovery.py` is extracted to `tools/_common.py` and re-imported by all three modules. Pure refactor, no contract change.
- A new `_summarize_files(paths: Iterable[Path], root: Path) -> list[str]` helper produces the POSIX-relative `files_modified` list, sorted and de-duplicated.
- A new `_resolve_layout_for_map(project, map_name) -> LayoutEntry` helper centralizes the `get_map_entry → layout_id → get_layout` chain that every paint tool needs.

---

## Per-tool spec

See the agent's design notes (full signatures, docstrings, return-shape JSON examples per tool) preserved verbatim below. They are normative.

### 1. `paint_metatile(project_path, map_name, x, y, metatile_id, collision=None, elevation=None)`

Single-tile paint primitive. Idempotent. Returns `{summary, project_path, map_name, x, y, metatile_id, collision, elevation, previous: {metatile_id, collision, elevation}, files_modified}`. Errors: `MapNotFoundError`, `CoordinatesOutOfBoundsError`, `ProjectError`.

### 2. `paint_rectangle(project_path, map_name, x1, y1, x2, y2, metatile_id, collision=None, elevation=None)`

Inclusive bounds; requires `x1<=x2 and y1<=y2` (no auto-swap). Returns `{summary, project_path, map_name, bounds, tile_count, tiles_changed, metatile_id, collision, elevation, files_modified}`.

### 3. `flood_fill(project_path, map_name, x, y, metatile_id, collision=None, elevation=None)`

4-connected, iterative BFS. Source value taken from seed tile's metatile_id (collision/elevation NOT considered for match). Returns `{summary, project_path, map_name, seed, source_metatile_id, target_metatile_id, tiles_changed, files_modified}`.

### 4. `set_border(project_path, map_name, metatile_ids, collision_ids=None, elevation_ids=None)`

`metatile_ids` is a 2-D list `[row][col]` of size `border_height × border_width`. Returns `{summary, project_path, map_name, border_dimensions, cells_changed, files_modified}`.

### 5. `create_map(project_path, name, group, width, height, primary_tileset, secondary_tileset, *, fill_metatile_id=0, border_metatile_ids=None, header_overrides=None)`

`name` is bare PascalCase only (not `MAP_*`). Group created if missing. Returns `{summary, project_path, map_name, layout_id, group, group_created, dimensions, border_dimensions, paths: {map_json, map_bin, border_bin}, files_modified}`.

### 6. `resize_map(project_path, map_name, new_width, new_height, *, anchor="top-left", fill_metatile_id=0)`

Refuses to shrink if any event would be orphaned (lists them in the error). Returns `{summary, project_path, map_name, layout_id, previous_dimensions, new_dimensions, cells_added, cells_removed, files_modified}`.

### 7. `register_map(project_path, map_name, group)`

Scans `data/maps/*/map.json` for `id == map_name` regardless of `map_groups.json` state. Already in requested group → no-op; in different group → error. Returns `{summary, project_path, map_name, bare_name, group, group_created, was_already_registered, files_modified}`.

### 8. `unregister_map(project_path, map_name)`

Removes from `map_groups.json`; preserves all on-disk files. Empties group → group removed. Returns `{summary, project_path, map_name, group, group_removed, was_already_unregistered, orphaned_files, files_modified}`.

---

## Error contract summary

| Tool | Errors | Recovery hint embedded in message |
|---|---|---|
| `paint_metatile` | `MapNotFoundError`, `CoordinatesOutOfBoundsError`, `ProjectError` | OOB carries dims; `ProjectError` carries the valid range. |
| `paint_rectangle` | `MapNotFoundError`, `CoordinatesOutOfBoundsError`, `ProjectError` | Reversed corners: "provide as (top-left, bottom-right)". |
| `flood_fill` | `MapNotFoundError`, `CoordinatesOutOfBoundsError`, `ProjectError` | — |
| `set_border` | `MapNotFoundError`, `ProjectError` | Shape mismatch states both sizes. |
| `create_map` | `ProjectError` | Bare-name rule, duplicate name, missing tileset — each error names the offending input. |
| `resize_map` | `MapNotFoundError`, `ProjectError` | Orphan events listed by class:index and (x,y); points at `remove_event`. |
| `register_map` | `MapNotFoundError`, `ProjectError` | Different-group error names both groups and points at `unregister_map`. |
| `unregister_map` | `MapNotFoundError` | — |

No new exception classes are introduced.

---

## Alternatives considered

(Only cross-cutting choices are reviewed here. Per-tool variants are covered inline.)

### Alternative 1 — "Idempotence = always write, content-stable"
- **Upside:** Simpler implementation (no read-before-write skip).
- **Downside:** File mtime bumps on every identical call. Breaks L2 hot-reload heuristics that watch mtime; forces Porymap to reload layouts pointlessly. Also worsens test golden-file determinism.
- **Why not:** Skipping the write costs one extra `read_bytes`; the mtime stability is worth it.

### Alternative 2 — `create_map` accepts `MAP_*` constant directly
- **Upside:** Symmetric with every other tool (`map_name` is always MAP_*).
- **Downside:** Forces the tool to derive a *new* bare name from the constant (LITTLEROOT_TOWN → LittlerootTown is lossy — multiple bare names can collapse to the same SCREAMING_SNAKE). Or worse, force a separate `bare_name` parameter.
- **Why not:** The bare PascalCase is the canonical filesystem name and the SCREAMING_SNAKE constant is the lossy derivative. Going bare→snake is total; going snake→bare is ambiguous. We accept bare only; the docstring spells this out loudly.

### Alternative 3 — Strategy C: transactional context manager
- **Upside:** Real atomicity across the multi-file write. A crash mid-`create_map` rolls back cleanly.
- **Downside:** Implementation cost is non-trivial — we'd need an undo log of file deletes and rename-back operations, plus its own tests. For v0.1.0 with 5-file writes that complete in milliseconds, the failure window is narrow.
- **Why not:** Premature. Strategy B's failure modes are all *visible* (orphan files or registered-but-missing entries surface on the next discovery call). If we see real corruption, we add Strategy C in a v0.x.

### Alternative 4 — `resize_map` auto-removes orphan events with a `force=True` flag
- **Upside:** One call instead of two; matches Porymap's GUI behavior (it just truncates).
- **Downside:** Destructive default surface area is dangerous for an LLM that may misread "resize" as non-destructive. A force flag with a default of False is conservative but the flag invites misuse.
- **Why not:** Defer. The error message gives the model exactly what it needs to chain `remove_event` calls. If real workflows show the chain is annoying, we add a `force=True` later (additive, non-breaking).

### Alternative 5 — Rectangle / line / circle paint primitives all in one
- **Upside:** A single `paint_shape(kind, ...)` tool with `kind` enum.
- **Downside:** "Mega tool" anti-pattern. Validation, parameters, and errors all diverge by shape.
- **Why not:** Keep them separate. `paint_line`, `paint_circle`, etc. can be added later as needed.

---

## Consequences

- **Positive:**
  - Eight mutation tools are spec-frozen and can ship in v0.1.0 alongside the seven discovery tools.
  - No new error classes; existing hierarchy carries every failure mode.
  - Idempotence + `files_modified` give the model the two signals it needs for safe retry and downstream chaining (especially L2 hot-reload).
  - The bare-name rule for `create_map` is unambiguous and matches the on-disk reality, making future tooling (rename, copy) straightforward.
  - Discovery-before-mutation is preserved: every mutation tool in this batch has an existing discovery pair.

- **Negative:**
  - "Best-effort" multi-file atomicity in `create_map` and `resize_map` can leave orphan files on crash. Mitigated by file ordering (orphans are detectable, not corrupting) but not eliminated.
  - The bare-name convention is opinionated. Forks with non-PascalCase directory names will hit `ProjectError` on `create_map` and must use their existing tooling instead.
  - `unregister_map` leaves orphan files by design; users need to know to clean them up. Made loud in the docstring and the response's `orphaned_files` list.

- **Neutral:**
  - Two `Project` additions: `write_border_bin`, `find_bare_by_map_id`. Pure additive.
  - The `_load_project` helper moves from `tools/discovery.py` to `tools/_common.py`. Pure refactor.

---

## Open questions (deferred)

- **OQ-A — Non-`top-left` resize anchors.** v0.1.0 supports `anchor="top-left"` only. Adding `"center"`, `"top-right"`, etc. is purely additive but requires designing what "center" means for odd new dimensions. Defer until a use case appears.
- **OQ-B — `resize_map` with `force=True` for orphan events.** Defer until the chain `list_events → remove_event → resize_map` proves too painful in practice.
- **OQ-C — Connection rewriting on resize.** Connections to/from a resized map may need their `offset` adjusted; we currently pass them through unchanged. Defer to whichever ADR introduces connection-mutation tools.
- **OQ-D — `delete_map` (true file delete).** `unregister_map` deliberately leaves files. A real "delete the directory" tool is a separate decision (destructive, irreversible) — defer until requested.
- **OQ-E — Validation of metatile_id against the actual tileset metatile count.** Once `parsers/metatiles.py` lands, every paint tool could optionally cross-check the id against the map's primary+secondary metatile count. Defer the precise contract.
- **OQ-F — Bulk paint via array.** A `paint_tiles(tiles: list[{x, y, id, collision, elevation}])` would let the model author dozens of tiles in one call. Defer.
- **OQ-G — Layout id naming for maps that share a layout.** `create_map` currently always allocates a fresh layout id. For maps that share an existing layout (pokeemerald pattern), the model has to manually edit `layouts.json`. Defer.

---

## References

- Related ADRs: ADR-0003 (Project class + config-driven format), ADR-0004 (tileset metadata source), ADR-0005 (L1 discovery tools — sibling ADR).
- Phase doc: `docs/phases/phase-2-l1-filesystem.md` §3 (frozen mutation tool list), §8 (open questions inherited here).
- Project conventions: `CLAUDE.md` §5 (MCP tool design rules).
- Out of scope (deferred to follow-up ADRs): `paint_prefab` (needs prefab library), event-mutation tools (need `parsers/events.py`), `delete_map`.
