# Changelog

All notable changes to `porymap-mcp` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com); the project adheres to
[Semantic Versioning](https://semver.org).

## [Unreleased] — `v1.0.0` candidate

L3 — Vision: server-side map rendering with self-critique loop. Phase 4 of the roadmap (see [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md)).

`v0.2.0` is intentionally skipped — L2 (Live Porymap) was abandoned per [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). The roadmap jumps from `v0.1.0` (L1) straight to `v1.0.0` (L1 + L3).

### Added

**Render pipeline** (`src/porymap_mcp/render/`, behind the `render` optional extra — `pip install porymap-mcp[render]`):

- `compose.py` — `decode_tile_bank`, `decode_palette_bank`, `decode_metatile_bank`. Decodes `tiles.png` (4-bpp indexed), JASC `.pal` files (with mandatory GBA 5-bit hardware quantization, `c & 0xF8`), and dual-/triple-layer metatiles; fills missing layers per `unused_tile_{normal,covered,split}` × `LayerType` per [ADR-0010](docs/decisions/0010-l3-renderer-design.md).
- `layout.py` — `assemble`, `assemble_region`, `clip_region`, `mapbin_to_metatile_grid`, `tile_border_around`. Pure-numpy fancy-index assembly of metatile grids into pixel buffers; modulo-tiled border framing.
- `overlays.py` — `apply_{collision,elevation,grid,events}_overlay` + dispatcher. Alpha-blended translucent overlays for the four supported modes.
- `encode.py` — `encode_png` (palette-vs-RGBA selection per ADR-0010 §"PNG encoding": palette mode iff opaque, ≤ 4096 metatiles, ≤ 256 distinct RGB), `package_render_result` (FastMCP `ToolResult` + `ImageContent` packaging).

**New MCP tools (3):**

- `render_map(project_path, map_name, *, overlays=[], include_border=False, scale=1)` — returns the full map as a PNG `ImageContent` block.
- `render_map_region(project_path, map_name, x1, y1, x2, y2, *, overlays=[], scale=1)` — partial render for big maps.
- `render_metatile(project_path, tileset_name, metatile_id, *, scale=4)` — single-metatile preview.

**`return_render: bool = False` on every L1 mutation tool** (12 tools — 7 in `maps.py`, 5 in `events.py`). When `True`, the response includes a render of the post-mutation map; default `False` preserves the historical `dict` contract.

**Extended `ProjectConfig`** reads `transparency_color`, `unused_tile_{normal,covered,split}` from `porymap.project.cfg` — required by the L3 metatile composer.

**Worked example** at [`examples/04_render_loop/`](examples/04_render_loop/) — runnable demo of the full `paint → render → critique → fix → re-render` loop with two committed render PNGs showing iter-1 → iter-2 score improvement.

**New errors:** `TilesPngFormatError`, `PaletteFormatError`, `MetatilesBinFormatError`, `LayoutAssemblyError`, `PngEncodeError`.

### Tooling

- `pyproject.toml`: new `render` optional extra (`Pillow>=10.0`, `numpy>=1.26`). Mypy override for `numpy.*` / `PIL.*`.
- Tests: **460 passing** (308 L1 + 152 new under `tests/unit/render/` + `tests/unit/tools/test_rendering.py`).

### Known limitations

- 5-map fidelity corpus (`tests/fixtures/renders/`) not yet committed — Porymap-exported reference PNGs pending. `v1.0.0` tags when the corpus passes `np.array_equal(decoded(ours), decoded(reference))` in CI.
- Map connections not rendered in `v1.0` (reference Porymap exports use "show connections = off"); a future `v1.1` may add `include_connections: bool`.
- Overlay event squares are coloured rectangles, not icons; a future enhancement bundles 12×12 PNG icons under `src/porymap_mcp/render/assets/icons/`.

## [0.1.0] — 2026-05-13

First public release. L1 Filesystem capability complete: an MCP agent
can author pokeemerald-family maps without Porymap running. Validated
end-to-end against `rh-hideout/pokeemerald-expansion` opened in
Porymap (Windows) — see README "First map in 5 minutes".

### Added

**Tool surface (21 MCP tools, semver-frozen):**

- **Discovery (7)** — `get_project_info`, `list_maps`, `get_map_info`,
  `list_tilesets`, `list_metatiles`, `list_prefabs`, `list_events`.
- **Map mutation (7)** — `paint_metatile`, `paint_rectangle`,
  `flood_fill`, `set_border`, `create_map`, `resize_map`,
  `paint_prefab`.
- **Project structure (2)** — `register_map`, `unregister_map`.
- **Events (5)** — `add_warp`, `add_object_event`, `add_sign` (with
  poryscript / `.inc` stub generation), `add_trigger`, `remove_event`.

**Parsers** for `map.bin`, `border.bin`, `porymap.project.cfg`,
`layouts.json`, `map_groups.json`, `map.json`, tileset discovery,
`metatiles.bin` (counts), and `metatile_attributes.bin`
(config-driven mask decoding, supports 1/2/4-byte attribute words).

**`Project` orchestration class** with lazy loading, atomic writes,
dimension-checked map.bin I/O, MAP_*-constant resolution, and
malformed-file-tolerant scanning.

**Built-in prefab library** with three demo prefabs (`single_tree`,
`flower_patch`, `house_small`) and the `Prefab` / `PrefabTile` types.

**Architecture decision records:** ADR-0001 through ADR-0008 covering
framework choice, target game, single-entrypoint design,
tileset-metadata strategy, and per-tool API surfaces.

### Fixed (interop with pokeemerald-expansion)

- `mapjson._read_connections` is now **permissive on read**: a
  non-list non-null value (e.g. `"connections": 0` as seen in 60+
  FRLG map.json files in `pokeemerald-expansion`) is treated as an
  empty connections list, matching Porymap's tolerance. The writer
  still emits canonical `null` for empty, so a read-then-write
  normalizes the file.

- `Project.find_bare_by_map_id` now swallows `PorymapMCPError` raised
  by individual `map.json` files when scanning for duplicates. A
  single corrupt map.json no longer blocks `create_map` or
  `register_map` for unrelated maps.

### Known limitations

- Typed event dataclasses deferred (raw-dict events round-trip via
  `parsers/mapjson`).
- Built-in prefab metatile IDs target vanilla pokeemerald conventions;
  forks may need to register replacement prefabs.
- L2 (live Porymap hot-reload) was abandoned post-`v0.1.0`
  ([ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md)); L3
  rendering ships in `v1.0.0` instead.

[Unreleased]: https://github.com/hugomrts/porymap-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hugomrts/porymap-mcp/releases/tag/v0.1.0
