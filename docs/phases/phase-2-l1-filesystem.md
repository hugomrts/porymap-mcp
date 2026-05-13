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
   - [ ] `parsers/mapjson.py`
   - [ ] `parsers/tilesetheaders.py`
   - [ ] `parsers/metatiles.py`
   - [ ] `parsers/attributes.py` (base-game-version branched)
2. **Day 1.5 — Project class + errors + atomic writes.** Foundation for tools.
   - [x] `errors.py`
   - [x] `_atomic.py`
   - [x] `project.py` (`Project` class — lazy loader, config detection)
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

### 2026-05-13 — Parsers: projectconfig + layoutsjson
- Used `porymap-format-expert` to lock down the wire formats for `porymap.project.cfg` and `data/layouts/layouts.json` with Porymap-source citations.
- **`parsers/projectconfig.py`** — pure read/write of `porymap.project.cfg`. Stores entries as an order-preserving `dict[str, str]`; provides typed property accessors for the bootstrap-critical keys (`base_game_version`, `use_poryscript`, `use_custom_border_size`, `enable_triple_layer_metatiles`, `metatile_attributes_size`, four `metatile_*_mask` keys, three `block_*_mask` keys), each with the canonical RSE default when absent. Round-trip is byte-stable for known *and* unknown keys.
- **`parsers/layoutsjson.py`** — pure read/write of `data/layouts/layouts.json`. `LayoutEntry` / `LayoutsJson` dataclasses; emits keys in Porymap's canonical `OrderedJson` order with 2-space indent and trailing LF; conditionally emits `border_width`/`border_height` only when both are set; rejects `null` entries and mismatched border-dim presence.
- Errors: added `ProjectConfigFormatError` and `LayoutsJsonFormatError` subclasses of `FormatError`.
- Tests: `tests/unit/parsers/test_projectconfig.py` (22 cases) + `tests/unit/parsers/test_layoutsjson.py` (27 cases) covering read, write, round-trip, malformed input, key-ordering invariants, conditional border emission, and `bool`-as-`int` rejection. Full suite: 71 / 71 passing locally. `mypy --strict` clean on 9 source files; `ruff` clean across `src/` and `tests/`.

### 2026-05-13 (later) — Parser: mapgroups
- Used `porymap-format-expert` to confirm the top-level key is **`group_order`** (not `group_names`) and that map-name entries are bare names like `"LittlerootTown"`, not `MAP_*` constants. Group symbols are `gMapGroup_*` C identifiers.
- **`parsers/mapgroups.py`** — pure read/write of `data/maps/map_groups.json`. `MapGroups` dataclass stores `group_order: tuple[str, ...]`, `groups: dict[str, tuple[str, ...]]`, and `custom: dict[str, object]` for Porymap's `customMapGroupsData` round-trip. Writer emits `group_order` first, then each group in `group_order` order (not dict insertion order), then preserved custom keys. Missing groups in the dict are emitted as `[]` to match Porymap's "missing key = empty group" behavior.
- Errors: added `MapGroupsFormatError` subclass of `FormatError`.
- Tests: `tests/unit/parsers/test_mapgroups.py` — 22 cases covering read, write, round-trip, malformed input, null/empty rejection, custom-key preservation, and the group-order-vs-dict-order writer invariant. Full suite: 93 / 93 passing locally. `mypy --strict` clean on 10 source files; `ruff` clean.

### 2026-05-13 (even later) — Project class + tileset-headers pivot
- Asked the `porymap-format-expert` agent for the spec of `data/tilesets/headers.json`. **Premise was wrong** — tileset metadata lives in C, not JSON: `src/data/tilesets/headers.h` contains `const struct Tileset gTileset_* = { ... };` definitions, parsed by Porymap via `Project::readTilesetLabels` → `parser.readCStructs(...)` with FRLG-vs-Emerald field-order differences and `.inc` ASM fallbacks for old projects. **Decision deferred** — this is a non-reversible architecture choice (write a small C-struct lexer? add `parsers/tileset.py` as in CLAUDE.md §2?). Next session must write an ADR before touching tilesets.
- Pivoted to the **`Project` class** since the four parsers we have are enough to back most of it. `src/porymap_mcp/project.py`:
  - Constructor validates root is a directory.
  - Lazy-loads `porymap.project.cfg`, `data/layouts/layouts.json`, `data/maps/map_groups.json` on first property access; caches them.
  - Validates `base_game_version` against `SUPPORTED_BASE_GAME_VERSIONS` on first config load (raises `UnsupportedBaseGameError` otherwise).
  - Atomic writers: `save_config` / `save_layouts` / `save_map_groups`. Each `mkdir(parents=True, exist_ok=True)` before calling through `_atomic.write_atomic_text`.
  - Setters (`@config.setter`, etc.) for create-from-scratch flows where you set then save.
  - Layout helpers: `get_layout(id)`, `list_layout_ids()`.
  - Map-group helpers: `list_map_names()`, `group_of(map_name)`.
  - `read_map_bin(id)` / `read_border_bin(id)` / `write_map_bin(id, MapBin)` tying `mapbin.read` / `mapbin.write` to the dimensions declared in `layouts.json`. `write_map_bin` rejects dimension mismatch — silently writing a differently-sized blob would corrupt the project.
  - Border size: respects layout-entry `border_width`/`border_height` when present, else falls back to the canonical 2×2.
  - `resolve_path()` translates POSIX-relative paths from JSON to absolute `Path`s.
- Tests: `tests/unit/test_project.py` — 32 cases covering construction, path helpers, config loading + lazy-cache invariant + base-game validation + setter/save flow, layouts loading + lookup + round-trip save, map-groups listing + group lookup + round-trip save, and map.bin / border.bin I/O including custom-border-size and dimension-mismatch rejection. Full suite: **125 / 125 passing locally**. `mypy --strict` clean across 11 source files; `ruff` clean.

### Next session pickup
- **ADR-0003** to write: tileset-metadata representation. Options: write a minimal C-struct lexer; depend on a Porymap-touched project so the JSON-ish metadata Porymap caches in `porymap.user.cfg` is trusted; defer tileset awareness to L3. Pick one before touching any tileset code.
- After the ADR, the next parsers are:
  - `parsers/mapjson.py` (events + header metadata + connections). The biggest remaining format. Splitting events vs header parsing is recommended (could land across two sessions).
  - `parsers/tileset.py` (per ADR-0003 direction).
  - `parsers/metatiles.py` + `parsers/attributes.py` (branch on `block_*_mask` / `metatile_*_mask` from the config, **not** on `base_game_version` directly).
- Once `mapjson` lands, the discovery tools (`list_maps`, `get_map_info`, `list_events`) can be built on top of `Project` immediately — they need very little beyond what's already there.

---

## 10. References

- Phase 1: [`phase-1-spec.md`](phase-1-spec.md)
- Phase 3 (next): [`phase-3-l2-live-porymap.md`](phase-3-l2-live-porymap.md)
- Agent specs: [`../../.claude/agents/`](../../.claude/agents/)
