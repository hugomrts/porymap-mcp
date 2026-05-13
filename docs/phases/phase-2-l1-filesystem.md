# Phase 2 — L1: Filesystem MCP

> **Status:** Not started (blocked on Phase 1 close)
> **Estimated effort:** 2–3 days
> **Closes when:** an MCP client can create and edit a real pokeemerald map end-to-end, and a human opens it in Porymap to confirm.

---

## 1. Goal

Ship a minimal MCP server that lets an agent author pokeemerald maps **without Porymap running**. The agent reads and writes files directly; the user opens Porymap *after* to visualize.

This is the foundation. L2 and L3 add capabilities on top — they do *not* replace L1.

---

## 2. Exit criteria

- [ ] `pip install porymap-mcp` works locally (editable install)
- [ ] `python -m porymap_mcp` boots a FastMCP server on stdio
- [ ] All L1 tools (frozen list in §3) implemented and tested
- [ ] Unit test coverage ≥ 90% on parsers, ≥ 80% on tools
- [ ] Integration test: create a 10×10 map, paint a 3×4 house prefab, add a warp, save, open in real Porymap, screenshot
- [ ] CI passes on Python 3.11, 3.12, 3.13 × Linux, macOS
- [ ] Tagged `v0.1.0` (not yet published to PyPI — that's Phase 5)
- [ ] `README.md` with the 5-minute "first map" example

---

## 3. Frozen L1 tool surface

> ⚠️ This list is **frozen** at the end of Phase 1. Adding tools = new minor version. Changing signatures = breaking change.
> Current state: **DRAFT** (to be frozen).

### Discovery tools (read-only)

| Tool | Signature | Returns |
|------|-----------|---------|
| `get_project_info` | `(project_path: Path)` | base_game_version, root paths, tileset count, map count |
| `list_maps` | `(project_path: Path)` | list of `{name, group, layout_id, dimensions}` |
| `get_map_info` | `(project_path: Path, map_name: str)` | full map metadata + dimensions + tilesets + event counts |
| `list_tilesets` | `(project_path: Path)` | list of `{name, is_primary, metatile_count}` |
| `list_metatiles` | `(project_path: Path, tileset_name: str)` | list of `{id, attributes}` (no images yet — that's L3) |
| `list_prefabs` | `(project_path: Path)` | list of `{name, width, height, tileset_requirements}` |
| `list_events` | `(project_path: Path, map_name: str)` | warps, object events, signs, triggers |

### Mutation tools — map layout

| Tool | Signature | Notes |
|------|-----------|-------|
| `create_map` | `(project_path, name, group, width, height, primary_tileset, secondary_tileset)` | Creates files + registers in indexes. Idempotent (rejects duplicate names). |
| `resize_map` | `(project_path, map_name, new_width, new_height, anchor="top-left")` | Preserves overlapping content; pads with border tile. |
| `set_border` | `(project_path, map_name, metatile_ids: list[list[int]])` | 2D grid of metatile IDs for the border. |
| `paint_metatile` | `(project_path, map_name, x, y, metatile_id, collision=None, elevation=None)` | Single tile. None = preserve. Idempotent. |
| `paint_rectangle` | `(project_path, map_name, x1, y1, x2, y2, metatile_id, collision=None, elevation=None)` | Inclusive bounds. |
| `flood_fill` | `(project_path, map_name, x, y, metatile_id, collision=None, elevation=None)` | 4-connected. Replaces all matching neighbors. |
| `paint_prefab` | `(project_path, map_name, prefab_name, x, y)` | x,y = top-left anchor. Respects tileset compatibility. |

### Mutation tools — events

| Tool | Signature | Notes |
|------|-----------|-------|
| `add_warp` | `(project_path, map_name, x, y, dest_map, dest_warp_id)` | Returns the new warp's id. |
| `add_object_event` | `(project_path, map_name, x, y, gfx, movement, script="")` | NPC. Script can be empty for placeholder. |
| `add_sign` | `(project_path, map_name, x, y, text)` | Sign with inline text — generates a poryscript stub. |
| `add_trigger` | `(project_path, map_name, x, y, var, value, script)` | Coord-based script trigger. |
| `remove_event` | `(project_path, map_name, event_id)` | Removes any event by id. |

### Project structure tools

| Tool | Signature | Notes |
|------|-----------|-------|
| `register_map` | `(project_path, map_name, map_group)` | Used by `create_map` internally; exposed separately for repair scenarios. |
| `unregister_map` | `(project_path, map_name)` | Removes from indexes; **does not delete files** — that's a separate explicit call. |

### Out of scope for L1 (deferred)

- `render_map` → Phase 4 (L3)
- `notify_porymap_reload` → Phase 3 (L2)
- `generate_town`, `generate_route` → post-1.0 (compositional layer)
- Tileset *editing* (creating new metatiles) → likely never; that stays in Porymap

---

## 4. Upstream files we read/write

Read-only:
- `project_config.cfg` / `porymap.project.cfg` — `base_game_version`, paths
- `data/tilesets/headers.json` — tileset definitions
- `data/tilesets/*/metatiles.bin` — metatile composition
- `data/tilesets/*/metatile_attributes.bin` — attributes
- `data/tilesets/*/tiles.png` — tile graphics (L3 only)
- `data/tilesets/*/palettes/*.pal` — palettes (L3 only)

Read-write:
- `data/layouts/layouts.json` — layout index
- `data/layouts/<MAP>/map.bin` — the actual map data
- `data/layouts/<MAP>/border.bin` — border data
- `data/maps/map_groups.json` — map group index
- `data/maps/<MAP>/map.json` — map metadata + events
- `data/maps/<MAP>/scripts.pory` (or `.inc`) — generated event scripts
- `include/constants/map_groups.h` — sometimes auto-generated, sometimes not (depends on project)

---

## 5. Architecture

```
src/porymap_mcp/
├── __init__.py
├── __main__.py              # python -m porymap_mcp entrypoint
├── server.py                # FastMCP() instance + tool registrations
├── errors.py                # PorymapMCPError hierarchy
├── project.py               # Project class: lazy-loaded project, config detection
├── parsers/
│   ├── mapbin.py
│   ├── borderbin.py
│   ├── mapjson.py
│   ├── layoutsjson.py
│   ├── mapgroups.py
│   ├── tilesetheaders.py
│   ├── metatiles.py
│   ├── attributes.py        # base-game-version branched
│   └── projectconfig.py
├── tools/
│   ├── discovery.py
│   ├── maps.py
│   ├── events.py
│   ├── prefabs.py
│   └── structure.py
├── prefabs/
│   ├── library.py           # built-in prefabs (PC, Mart, generic house)
│   └── data/                # prefab definitions as JSON
└── _atomic.py               # write_atomic helper
```

**Key invariants:**
- `parsers/` is pure (no I/O *outside* the explicit `read()` / `write()` functions). No print, no logging.
- `tools/` orchestrates parsers, never duplicates parsing logic.
- All writes go through `_atomic.write_atomic(path, data)`.
- All paths in JSON output are POSIX, relative to project root.

---

## 6. Synthetic fixture project

Lives at `tests/fixtures/fake_project_emerald/`. See `tests/fixtures/README.md` for the byte-by-byte explanation of every file.

Structure: covers `project_config.cfg`, one tiny tileset (primary `general` + secondary `house`), two layouts (a 5×5 and a 10×10), two maps with one warp linking them, one map_group containing both.

To be created in Phase 2 by the `test-engineer` agent.

---

## 7. Implementation order

Recommended order — each step ends with passing tests:

1. **Day 1 — Parsers.** Implement parsers/ + unit tests + round-trip tests against fixture. Use `porymap-format-expert` heavily.
   - [x] `parsers/mapbin.py` (also covers `border.bin`)
   - [x] `parsers/projectconfig.py`
   - [x] `parsers/layoutsjson.py`
   - [x] `parsers/mapgroups.py`
   - [x] `parsers/mapjson.py` (header + connections typed; events kept as raw dicts for round-trip)
   - [x] `parsers/tileset.py` (ADR-0004 stage 1: filesystem glob; `c_label` derived by snake_case → PascalCase, `c_label_unverified=True`. Wired into `Project` as `tilesets` lazy property + `get_tileset_by_label` / `get_tileset_by_name`. Stage 2 — `headers.h` C-struct lexer — deferred.)
   - [ ] `parsers/events.py` (typed event dataclasses; deferred until the first event-mutation tool needs them — `add_warp`, `add_object_event`)
   - [ ] `parsers/metatiles.py`
   - [ ] `parsers/attributes.py` (consumes masks from `ProjectConfig`, not branched on `base_game_version` — see ADR-0003)
   - [ ] follow-up: refactor `parsers/mapbin.py` to take `metatile_id_mask`/`collision_mask`/`elevation_mask` as keyword args instead of module-level constants (ADR-0003 conformance; currently hardcoded matches the vanilla/expansion defaults so behavior is unchanged for v0.1.0)
2. **Day 1.5 — Project class + errors + atomic writes.** Foundation for tools.
   - [x] `errors.py`
   - [x] `_atomic.py`
   - [x] `project.py` (`Project(root)` class — lazy properties for `config` / `layouts` / `map_groups`, atomic `save_*`, dimension-checked `read_map_bin` / `write_map_bin`; satisfies ADR-0003's "Project is the single entrypoint for tools" with cached-per-instance reads — no state across tool calls)
3. **Day 2 — Discovery tools.** `get_project_info`, `list_maps`, `get_map_info`, `list_tilesets`, `list_metatiles`, `list_events`. Use `mcp-tool-designer` to review signatures before coding.
4. **Day 2 — Simple mutation tools.** `paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`.
5. **Day 2.5 — Create/resize.** `create_map`, `resize_map`, `register_map`, `unregister_map`.
6. **Day 3 — Events.** `add_warp`, `add_object_event`, `add_sign`, `add_trigger`, `remove_event`. Script generation = poryscript snippet stubs.
7. **Day 3 — Prefabs.** Built-in library (PC, Mart, generic house), `list_prefabs`, `paint_prefab`.
8. **Day 3 — Integration test + README.** End-to-end test against real Porymap, write the README example.

---

## 8. Open questions

- **OQ1**: Should `paint_prefab` reject when the target tileset doesn't include the prefab's metatiles, or auto-import them? Default: reject with a clear error. Auto-import is a slippery slope.
- **OQ2**: When `create_map` is called and `include/constants/map_groups.h` is auto-generated by the build (depends on project), do we touch it? Default: detect "auto-generated" header and skip. Document the limitation.
- **OQ3**: Poryscript vs. raw `.inc` scripts — do we generate poryscript by default with a fallback? Probably yes; expansion uses poryscript.

---

## 9. Session log

### 2026-05-13 — Phase 2 scaffolding & first parser
- Created `pyproject.toml` (Python 3.11+, FastMCP, ruff, mypy strict, pytest, hypothesis, Pillow as `[render]` extra)
- Created `LICENSE` (MIT), `README.md` skeleton, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` (matrix: Python 3.11–3.13 × Ubuntu/macOS)
- Created `src/porymap_mcp/` package skeleton:
  - `__init__.py`, `__main__.py` (entry point)
  - `server.py` (FastMCP assembly; no tools registered yet)
  - `errors.py` (typed hierarchy: `PorymapMCPError` → `ProjectError`, `FormatError`, `MapBinFormatError`, `CoordinatesOutOfBoundsError`, `UnsupportedBaseGameError`)
  - `_atomic.py` (atomic write helpers)
  - `parsers/__init__.py`
- **First production parser: `parsers/mapbin.py`** — read/write of `map.bin` and `border.bin` layout files. Pure, side-effect-free, fully typed. Covers `Tile`, `MapBin` dataclasses + `decode_tile`/`encode_tile`/`read`/`write`.
- Tests: `tests/unit/parsers/test_mapbin.py` — 22 test cases covering decode, encode, round-trip, validation, edge cases (0xFFFF, 0x0000, oversized buffers, OOB access).
- Fixture documentation: `tests/fixtures/README.md` with the byte-by-byte table for the 3×2 reference layout.
- Parser sanity-checked manually against the documented fixture (round-trip OK).

### 2026-05-13 — ADR-0003 (Project class + config-driven format)
- Wrote ADR-0003 establishing `Project` as the single entrypoint for tools and committing to config-driven format parameters (no parser-level `base_game_version` branching). Shipped a first cut: `parsers/projectconfig.py` with eager-typed defaults + round-trip preservation, and a frozen `Project.load(path)` class. Merged via PR #2.

### 2026-05-13 — Parsers: projectconfig + layoutsjson + mapgroups (orphan-branch integration)
- Discovered an unmerged sibling session (`claude/continue-project-JR44W`) had shipped three more parsers plus a richer `Project` design. Integrated into the trunk: kept the orphan branch's `parsers/projectconfig.py`, `parsers/layoutsjson.py`, `parsers/mapgroups.py`, and `project.py`; rolled back my ADR-0003-shipped `parsers/projectconfig.py` and `project.py` in favor of theirs (ADR's strategic decisions still hold, only the API surface differs).
- **`parsers/projectconfig.py`** — pure read/write of `porymap.project.cfg`. `ProjectConfig.entries: dict[str, str]` for round-trip; typed property accessors (`base_game_version`, `block_*_mask`, `metatile_*_mask`, booleans), each with canonical RSE defaults when absent.
- **`parsers/layoutsjson.py`** — pure read/write of `data/layouts/layouts.json`. Emits keys in Porymap's canonical `OrderedJson` order, 2-space indent, trailing LF; conditional `border_width`/`border_height`.
- **`parsers/mapgroups.py`** — pure read/write of `data/maps/map_groups.json`. Preserves `group_order`, emits groups in declared order, round-trips Porymap's `customMapGroupsData` keys.
- **`project.py`** — `Project(root)` with lazy properties (`config`, `layouts`, `map_groups`), atomic `save_*`, `get_layout` / `list_layout_ids` / `list_map_names` / `group_of` helpers, and `read_map_bin` / `write_map_bin` that enforce layout-declared dimensions against the on-disk blob.
- Errors: `ProjectConfigFormatError`, `LayoutsJsonFormatError`, `MapGroupsFormatError` added.
- Tests: 22 (projectconfig) + 27 (layoutsjson) + 22 (mapgroups) + 32 (project) = 103 from the orphan branch, all preserved. Repo total: **125 passing**, `mypy --strict` clean on 11 source files, `ruff` clean.

### Tileset-headers pivot (deferred to ADR-0004)
- The orphan session discovered that `data/tilesets/headers.json` **does not exist** — tileset metadata lives in C (`src/data/tilesets/headers.h` with `const struct Tileset gTileset_* = { ... };`), parsed by Porymap via `Project::readTilesetLabels` → `parser.readCStructs(...)`, with FRLG-vs-Emerald field-order differences and `.inc` ASM fallbacks for old projects. This is a non-reversible architecture decision: write a C-struct lexer in `parsers/tileset.py`? Lean on Porymap to maintain a JSON cache? Defer tileset awareness to L3? **Blocks** any tileset work. Numbered as **ADR-0004** because the orphan session's working name was "ADR-0003", which collided with the one already shipped.

### 2026-05-13 — ADR-0004 + parsers/mapjson.py
- **ADR-0004 (tileset-metadata source)** accepted: two-stage strategy. Stage 1 (v0.1.0) is filesystem-first discovery — glob `data/tilesets/{primary,secondary}/*/`, derive the C label from directory basename via the snake_case → `gTileset_<PascalCase>` convention (marked `unverified=True`). Stage 2 (deferred until needed) adds a minimal designated-initializer C-struct lexer over `headers.h` plus an `INCBIN`/`INCGFX` resolver — purely additive. Rejected: lean on Porymap to maintain a JSON cache (no such cache exists upstream and adding it would break L1's "Porymap not required" promise); defer tileset awareness to L3 entirely (would break Phase 2 exit criteria for `list_tilesets` / `list_metatiles`); `.inc` ASM parsing (zero modern projects use it). Sourced from a deep `porymap-format-expert` brief covering RSE-vs-FRLG `struct Tileset` field-order differences, exactly which fields Porymap's `readTilesetLabels` consumes, and the `metatile_attributes_size` config knob.
- **`parsers/mapjson.py`** implemented (~310 LOC). Top-level `MapJson` dataclass with the 14 well-known header fields typed; conditional fields (`allow_cycling`/`allow_escaping`/`allow_running`/`floor_number`) modeled as `T | None` (None = absent from JSON, parser stays pure and never touches `ProjectConfig`). `Connection` dataclass for the connections array with `map`/`offset`/`direction` typed and a `custom: dict[str, object]` for hand-edited extras. Event arrays kept as `tuple[dict[str, object], ...]` so feature-flag-gated fields (`local_id`, `quantity`, `underfoot`, object `type`) round-trip verbatim — typed event dataclasses deferred until the first mutation tool needs them.
- Edge cases handled: `connections: null` and `connections: []` both read as empty; missing `connections` key tolerated for hand-edited files; empty connections always written as `null` to match Porymap's `Project::saveMap`. Inheritance (`shared_events_map`/`shared_scripts_map` set + event arrays absent) round-trips. Custom top-level keys preserved and appended after the canonical block. Booleans rejected for int fields and ints rejected for bool fields (defends against Python's `bool ⊆ int`).
- Output: 2-space indent, single trailing LF, canonical key order, lowercase `null`/`true`/`false`, UTF-8 (`ensure_ascii=False`) — matches Porymap's `OrderedJson` writer byte-for-byte against the `LittlerootTown` reference fixture.
- Tests: `tests/unit/parsers/test_mapjson.py` — 36 cases (read happy paths, every documented edge case, every type-error path, write canonical-order spot-check, round-trip on the reference fixture and the minimal fixture). 99% coverage on the new file.
- Repo health: **161 passing**, `ruff check .` clean, `ruff format --check .` clean, `mypy --strict src/porymap_mcp` clean on 12 source files.

### 2026-05-13 — parsers/tileset.py (ADR-0004 stage 1)
- **`parsers/tileset.py`** implemented (~80 LOC): `TilesetEntry` frozen dataclass (name, derived `c_label` with `c_label_unverified=True`, kind, four POSIX-relative asset paths, `is_compressed=None`), `discover_tilesets(project_root: Path) -> tuple[TilesetEntry, ...]` globbing `data/tilesets/{primary,secondary}/*/`, plus a `derive_c_label(name)` helper for the snake_case → `gTileset_<PascalCase>` convention. Stage 2 (headers.h C-struct lexer) deferred per ADR-0004.
- **Discovery is deterministic**: results sorted by `(kind, name)` regardless of `readdir` order; stray files at the tileset-kind directory level (e.g. a README) are skipped; subdirectories missing asset files are still reported (validation is the L1 tool's job, not discovery's).
- **`Project` wiring**: lazy `tilesets` property (cached per instance), `get_tileset_by_label(c_label)` for resolving `layouts.json`'s `primary_tileset` / `secondary_tileset` C symbols, `get_tileset_by_name(name)` for directory-basename lookup. Both raise `ProjectError` on miss with a message that points users to ADR-0004 stage 2 when the C-label convention fails.
- Tests: 14 new (`tests/unit/parsers/test_tileset.py`) covering `derive_c_label` edge cases (single/multi-word, empty segments) and `discover_tilesets` (empty project, primary-only, secondary-only, scrambled-order sorting, stray files, asset-less directories, POSIX path normalization, frozen-entry contract). Plus 7 new `Project`-level tests covering the lazy property, cache stability, and both lookup methods.
- Repo health: **182 passing**, `ruff check .` clean, `ruff format --check .` clean, `mypy --strict src/porymap_mcp` clean on 13 source files. 100% line + branch coverage on `parsers/tileset.py`.

### Next session pickup
- **Parser layer is done for L1.** Next is tools. Start by spawning `mcp-tool-designer` to sign off on the discovery-tool signatures (`get_project_info`, `list_maps`, `get_map_info`, `list_tilesets`, `list_metatiles`, `list_events`), then implement them in `src/porymap_mcp/tools/discovery.py` on top of `Project`. `Project.tilesets`, `mapjson`, `layouts`, `map_groups` are all in place; tools should be thin orchestrators.
- Defer `parsers/events.py` (typed event dataclasses) until the first event-mutation tool (`add_warp`, `add_object_event`) is being written. The current raw-dict representation in `mapjson.py` is enough for discovery.
- Then `parsers/metatiles.py` + `parsers/attributes.py` (consume `block_*_mask` / `metatile_*_mask` from `project.config`, **not** `base_game_version` directly — per ADR-0003). Needed before `list_metatiles` returns real attribute data.
- Outstanding ADR-0003 follow-up: refactor `parsers/mapbin.py` to accept layout masks as kwargs from `project.config` instead of the module-level constants (current hardcoded values match vanilla/expansion defaults, so behavior is unchanged for v0.1.0).

---

## 10. References

- Phase 1: [`phase-1-spec.md`](phase-1-spec.md)
- Phase 3 (next): [`phase-3-l2-live-porymap.md`](phase-3-l2-live-porymap.md)
- Agent specs: [`../../.claude/agents/`](../../.claude/agents/)
