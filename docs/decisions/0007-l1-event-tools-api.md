# ADR-0007: L1 event-mutation tools — MCP API surface

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** project owner (drafted from phase doc §3, §8 OQ3)

---

## Context

Phase 2 (L1 Filesystem) is in progress. ADR-0005 froze the seven read-only discovery tools; ADR-0006 froze the eight map/structure mutation tools. The remaining mutation tools listed in `docs/phases/phase-2-l1-filesystem.md` §3 are the **event mutators**:

- `add_warp(project_path, map_name, x, y, dest_map, dest_warp_id)` — returns the new warp's id.
- `add_object_event(project_path, map_name, x, y, gfx, movement, script="")` — NPC.
- `add_sign(project_path, map_name, x, y, text)` — sign with inline text. Generates a script stub.
- `add_trigger(project_path, map_name, x, y, var, value, script)` — coord-based trigger.
- `remove_event(project_path, map_name, event_id)` — removes any event by its synthesized `_event_id` (ADR-0005 §7 / OQ-A).

The phase doc §8 OQ3 (Poryscript vs `.inc`) is resolved here: default direction is poryscript.

Two prerequisite questions:

1. **Typed event dataclasses (`parsers/events.py`).** ADR-0005 OQ-A and the phase doc both flagged this as "deferred until the first event-mutation tool needs them". Now the tools are landing — do we need typed events?
2. **Script generation file.** `add_sign` / `add_object_event` / `add_trigger` may emit a script stub. Where does it go and in what language?

---

## Decision

We ship the five event-mutation tools in `src/porymap_mcp/tools/events.py`, registered on the FastMCP server. Each tool is a thin orchestrator over `Project.get_map_entry` + `mapjson.write`.

**Typed event dataclasses are deferred to v0.2.0.** Rationale: the tools need to *construct* event dicts (validated against per-class shape) and *append* them to `MapJson.{object,warp,coord,bg}_events`. The construction validators live in `tools/events.py` as small helpers (`_build_warp_event`, `_build_object_event`, etc.) and produce plain `dict[str, object]` matching what Porymap writes. The existing `parsers/mapjson.py` round-tripping covers serialization. A future `parsers/events.py` can typedef these dicts without breaking the tool layer.

**Poryscript is the default script language.** When `use_poryscript=1` in `porymap.project.cfg` (the default for pokeemerald-expansion and all modern forks), we emit `data/maps/<bare>/scripts.pory`. When `use_poryscript=0`, we emit `data/maps/<bare>/scripts.inc` with the equivalent macro-based stub. We detect by reading `ProjectConfig.use_poryscript`.

**Stubs append to existing script files.** The tools never overwrite. If the target script symbol already exists in the file, we error rather than producing a duplicate definition (the model should `remove_event` first or pick a different symbol).

---

## Per-tool spec

### Convention (shared with ADR-0005/0006)

- `project_path: str` first. `map_name` is the MAP_* constant.
- Coordinates `(x, y)` top-left. Validated against the layout's `width × height` — out of bounds → `CoordinatesOutOfBoundsError`.
- Mutation responses include `summary`, `project_path`, `map_name`, the new/removed event's id, and `files_modified`.
- Idempotence: `add_*` tools are **not** idempotent in the strict "same args → no-op" sense — repeated calls append new events. This matches Porymap's GUI semantics. (Strict idempotence would require a deduplication key and is out of scope for v0.1.0.) `remove_event` is idempotent: removing an already-absent id is a no-op success.

### 1. `add_warp(project_path, map_name, x, y, dest_map, dest_warp_id)`

```python
def add_warp(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    dest_map: str,
    dest_warp_id: int,
    elevation: int = 0,
) -> dict[str, Any]:
```

Appends a `warp_events` entry to the target map. Returns `{summary, project_path, map_name, event_id ("warp_events:N"), x, y, dest_map, dest_warp_id, files_modified}`.

Files modified: `data/maps/<bare>/map.json`.

Errors: `MapNotFoundError`, `CoordinatesOutOfBoundsError`.

### 2. `add_object_event(project_path, map_name, x, y, graphics_id, movement_type="MOVEMENT_TYPE_NONE", script="", flag="0", elevation=3)`

```python
def add_object_event(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    graphics_id: str,
    movement_type: str = "MOVEMENT_TYPE_NONE",
    script: str = "",
    flag: str = "0",
    elevation: int = 3,
    movement_range_x: int = 0,
    movement_range_y: int = 0,
    trainer_type: str = "TRAINER_TYPE_NONE",
    trainer_sight_or_berry_tree_id: str = "0",
) -> dict[str, Any]:
```

Builds an `object_events` entry with the standard pokeemerald keys.

When `script` is empty, the entry has `"script": "0"` (matches `pret/pokeemerald` convention for "no script"). When `script` is non-empty and matches a Python identifier-shaped string (e.g. `"LittlerootTown_EventScript_Mom"`), we *do not* generate a stub — we trust the caller has authored or will author the script separately. (Stubs are only generated by `add_sign`; object events are too varied for boilerplate.)

Returns `{summary, project_path, map_name, event_id ("object_events:N"), x, y, graphics_id, files_modified}`.

### 3. `add_sign(project_path, map_name, x, y, text, player_facing_dir="BG_EVENT_PLAYER_FACING_ANY", elevation=0)`

```python
def add_sign(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    text: str,
    player_facing_dir: str = "BG_EVENT_PLAYER_FACING_ANY",
    elevation: int = 0,
) -> dict[str, Any]:
```

Appends a `bg_events` entry with `"type": "sign"` AND generates a script stub that displays `text`. Stub script symbol: `<bare>_EventScript_Sign_<N>` where `<N>` is the next free index.

Script content (poryscript variant):

```
script <bare>_EventScript_Sign_<N> {
    msgbox("<escaped-text>", MSGBOX_SIGN)
}
```

Script content (`.inc` variant, when `use_poryscript=0`):

```
<bare>_EventScript_Sign_<N>::
    msgbox <bare>_EventText_Sign_<N>, MSGBOX_SIGN
    end

<bare>_EventText_Sign_<N>:
    .string "<escaped-text>$"
```

The script file (`scripts.pory` or `scripts.inc`) is created if missing; the stub is appended on a fresh line. If the symbol already exists in the file, the call errors (`ProjectError`) so the model can pick a new sign or `remove_event` first.

Returns `{summary, project_path, map_name, event_id, x, y, script_symbol, script_file, files_modified}`.

Files modified: `data/maps/<bare>/map.json`, `data/maps/<bare>/scripts.{pory,inc}`.

### 4. `add_trigger(project_path, map_name, x, y, var, value, script, elevation=0)`

```python
def add_trigger(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    var: str,
    value: int,
    script: str,
    elevation: int = 0,
) -> dict[str, Any]:
```

Appends a `coord_events` entry. We do NOT generate a script stub for triggers because the script name is required and might already exist; if the caller wants a stub, they call `add_sign`-like dedicated tooling in a future release.

Returns `{summary, project_path, map_name, event_id, x, y, var, value, script, files_modified}`.

### 5. `remove_event(project_path, map_name, event_id)`

```python
def remove_event(project_path: str, map_name: str, event_id: str) -> dict[str, Any]:
```

`event_id` follows ADR-0005 §7 format: `"<class>:<index>"`, e.g. `"warp_events:1"`. Parses the class and index, drops the entry from the corresponding array, shifts subsequent ids implicitly. Idempotent: removing an already-absent id (out-of-range index OR map already has no events of that class) is a no-op success with `files_modified: []`.

**Does NOT delete script files.** A removed sign's script stub stays in `scripts.pory`/`scripts.inc` — the model can edit the script file via the OS or a future `remove_script` tool. Rationale: scripts may have been edited by the user; auto-deletion is destructive.

Returns `{summary, project_path, map_name, event_id, removed_event, files_modified}`. `removed_event` is the dict that was removed (so the model can undo).

Errors: `MapNotFoundError`, `ProjectError` (malformed `event_id`).

---

## Cross-cutting decisions

### CC-1. Script-file detection

We check `project.config.use_poryscript` once per call. The script-file path is `data/maps/<bare>/scripts.pory` (poryscript) or `data/maps/<bare>/scripts.inc` (legacy). We do not fall back: if a project has `use_poryscript=0` but has a `scripts.pory` on disk, we still write to `scripts.inc` because that's what `use_poryscript=0` declares. The user is expected to keep these consistent.

### CC-2. Stub idempotence

Stub generation is **not** idempotent: each `add_sign` call appends a *new* sign script with a fresh `_Sign_<N>` symbol. The `<N>` is computed as `max(existing_sign_indices) + 1` (or 0 if none exist). This matches Porymap's GUI: every "Add Sign" click is a new event, even at the same `(x, y)`.

### CC-3. Text escaping

The `text` argument to `add_sign` is escaped for poryscript / `.inc` string syntax: double quotes become `\"`, newlines become `\n`. Control characters and non-ASCII pass through (poryscript and pret both UTF-8 everywhere).

### CC-4. Atomicity

Map.json + scripts.{pory,inc} write order:

1. Write/append script stub (file created if missing).
2. Append event to `map.json`.

A crash between steps leaves a script-symbol-without-event — harmless (the symbol is unreferenced; the build still passes; the next `add_sign` will pick a higher `<N>`).

### CC-5. event_id stability

Inherited from ADR-0005 §7: `event_id` is synthesized as `<class>:<index>` and is **not stable across mutations**. The model must call `list_events` again after any `add_*` or `remove_event` to refresh ids. Documented in every tool's docstring.

---

## Alternatives considered

### Alternative 1 — Build typed event dataclasses first
- **Upside:** Validators are tighter; mypy catches more bugs.
- **Downside:** Adds 300+ LOC of parser work for the 6 event sub-types (object, warp, coord, sign, hidden_item, secret_base) before any tool ships.
- **Why not:** The tool-layer construction validators are smaller (per-tool, ~10 lines each) and the existing raw-dict round-trip in `parsers/mapjson.py` already guarantees byte-stability. Defer the typed-events parser to v0.2.0 alongside any deeper event tooling.

### Alternative 2 — Always write `.inc` (skip poryscript)
- **Upside:** No conditional.
- **Downside:** Modern projects (pokeemerald-expansion, every rh-hideout fork) use poryscript. Forcing `.inc` would generate dead-on-arrival code for the target audience.
- **Why not:** Defaulting to poryscript respects the modern decomp ecosystem.

### Alternative 3 — Generate stubs for object events too
- **Upside:** One-call NPC creation including a "Hello, world" script.
- **Downside:** Object-event scripts vary enormously (trainer battles, item gives, cutscenes). A generic "say hello" stub is almost never what the caller wants; useful only as scaffolding.
- **Why not:** Keep stub generation focused on signs (where the text is the whole point). Object-event scripts are the caller's responsibility.

### Alternative 4 — `remove_event` deletes the associated script symbol
- **Upside:** Cleaner; no dead script symbols.
- **Downside:** Destructive on user-edited script content. Hard to detect "this script was generated by us" vs. "the user edited it heavily after generation".
- **Why not:** Conservative default. We document that script cleanup is the caller's responsibility.

---

## Consequences

- **Positive:**
  - Five tools ship without a new parser; the tool-layer construction validators are small and testable.
  - Poryscript default matches the modern decomp ecosystem; `.inc` fallback covers legacy projects.
  - `remove_event` honors the synthesized `event_id` from ADR-0005, closing the discovery → mutation → re-discovery loop.

- **Negative:**
  - No typed event dataclasses → tool-layer validators must be kept in sync with `parsers/mapjson.py`'s known-key sets. Mitigated by tests on per-event-class round trips.
  - Script files may accumulate dead stubs from `remove_event`. The model must clean up manually.

- **Neutral:**
  - One new module: `tools/events.py`. No `Project` additions; the existing `get_map_entry` / `iter_maps` machinery covers everything.

---

## Open questions (deferred)

- **OQ-A — Typed event dataclasses.** When? Probably v0.2.0 alongside connection-mutation tools that need richer event manipulation.
- **OQ-B — `remove_script_symbol`.** A future tool to clean up dead stubs after `remove_event`. Defer until requested.
- **OQ-C — Hidden item / secret base / weather trigger as separate tools.** Currently the model has to hand-build these via `add_object_event` or `add_sign`-like patterns. Phase doc lists `add_object_event` only; hidden items and secret bases are forks/feature-flag features. Defer to a follow-up ADR that surveys the feature-flag matrix.
- **OQ-D — Script stub generation for `add_object_event`.** Defer (see Alternative 3).

---

## References

- Related ADRs: ADR-0005 (discovery), ADR-0006 (map mutation).
- Phase doc: `docs/phases/phase-2-l1-filesystem.md` §3 (frozen tool list), §8 OQ3 (poryscript decision, resolved here).
- Parser: `src/porymap_mcp/parsers/mapjson.py` (raw-dict event round-trip).
- Poryscript reference: https://github.com/huderlem/poryscript
