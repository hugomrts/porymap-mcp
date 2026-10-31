# Changelog

All notable changes to `porymap-mcp` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com); the project adheres to
[Semantic Versioning](https://semver.org).

## [Unreleased]

## [1.0.1] — 2026-10-31

### Changed

- README: lead with real-tileset renders (Littleroot Town, Route 101) instead of the synthetic demo.

## [1.0.0] — 2026-10-31

First stable release. L3 — Vision: server-side map rendering with self-critique loop, validated pixel-for-pixel against Porymap's own export on a 5-map corpus. Phase 4 of the roadmap (see [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md)).

`v0.2.0` is intentionally skipped — L2 (Live Porymap) was abandoned per [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). The roadmap jumps from `v0.1.0` (L1) straight to `v1.0.0` (L1 + L3).

### Added

**Render pipeline** (`src/porymap_mcp/render/`, behind the `render` optional extra — `pip install porymap-mcp[render]`):

- `compose.py` — `decode_tile_bank`, `decode_palette_bank`, `decode_metatile_bank`. Decodes `tiles.png` (4-bpp indexed), JASC `.pal` files (colours propagated verbatim, as Porymap does), and dual-/triple-layer metatiles; fills missing layers per `unused_tile_{normal,covered,split}` × `LayerType` per [ADR-0010](docs/decisions/0010-l3-renderer-design.md).
- `layout.py` — `assemble`, `assemble_region`, `clip_region`, `mapbin_to_metatile_grid`, `tile_border_around`. Pure-numpy fancy-index assembly of metatile grids into pixel buffers; modulo-tiled border framing.
- `overlays.py` — `apply_{collision,elevation,grid,events}_overlay` + dispatcher. Alpha-blended translucent overlays for the four supported modes.
- `encode.py` — `encode_png` (palette-vs-RGBA selection per ADR-0010 §"PNG encoding": palette mode iff opaque, ≤ 4096 metatiles, ≤ 256 distinct RGB), `package_render_result` (FastMCP `ToolResult` + `ImageContent` packaging).

**New MCP tools (3):**

- `render_map(project_path, map_name, *, overlays=[], include_border=False, scale=1)` — returns the full map as a PNG `ImageContent` block.
- `render_map_region(project_path, map_name, x1, y1, x2, y2, *, overlays=[], scale=1)` — partial render for big maps.
- `render_metatile(project_path, tileset_name, metatile_id, *, scale=4)` — single-metatile preview.

**`return_render: bool = False` on every map and event mutation tool** (12 tools — 7 in `maps.py`, 5 in `events.py`). When `True`, the response includes a render of the post-mutation map; default `False` preserves the historical `dict` contract.

**Extended `ProjectConfig`** reads `transparency_color`, `unused_tile_{normal,covered,split}` from `porymap.project.cfg` — required by the L3 metatile composer.

**Worked example** at [`examples/04_render_loop/`](examples/04_render_loop/) — runnable demo of the full `paint → render → critique → fix → re-render` loop with two committed render PNGs showing iter-1 → iter-2 score improvement.

**Fidelity corpus** under `tests/fixtures/renders/`: Littleroot Town, Route 101, Granite Cave 1F and Battle Frontier Outside East (vendored from a `pokeemerald-expansion` checkout, with Porymap-exported reference PNGs) plus a synthetic edge case. `tests/integration/test_fidelity.py` asserts pixel-identical output on all 5; `pytest --update-golden` regenerates the synthetic reference.

**New errors:** `TilesPngFormatError`, `PaletteFormatError`, `MetatilesBinFormatError`, `LayoutAssemblyError`, `PngEncodeError`.

### Fixed

Four renderer bugs surfaced by validating against real Porymap exports (corrections recorded in [ADR-0010](docs/decisions/0010-l3-renderer-design.md) §"Empirical corrections"):

- **Palette colours are no longer quantized.** The `& 0xF8` GBA 5-bit mask on JASC palette values was wrong: Porymap uses the `.pal` bytes verbatim. (`8dd6028`)
- **Border tiles are phased on the map's top-left, not the image's.** `border[0][0]` now lands on the first map tile, and tiles outside the map cycle backwards from there. (`8dd6028`)
- **The border frame is asymmetric: 7 metatiles horizontally, 5 vertically**, matching Porymap (half the GBA's 240×160 screen) instead of a symmetric 7×7. `border_frame_metatiles` in the render metadata is now a `{"horizontal", "vertical"}` dict. (`8dd6028`)
- **`unused_tile_*` config values are decoded as packed tile-entry words** (tile id + flips + palette), not bare tile ids. pokeemerald-expansion's `unused_tile_normal=0x3014` previously overflowed the tile bank and exposed the transparency colour. (`71cee3e`)

### Tooling

- `pyproject.toml`: new `render` optional extra (`Pillow>=10.0`, `numpy>=1.26`). Mypy override for `numpy.*` / `PIL.*`.
- Tests: **465 passing** (308 L1 + 152 render unit tests + 5 fidelity cases).
- CI now blocks on `ruff check`, `ruff format --check` and `mypy --strict`; ruff and mypy are pinned to a minor/major range in the `dev` extra.

### Known limitations

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

[Unreleased]: https://github.com/hugomrts/porymap-mcp/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/hugomrts/porymap-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/hugomrts/porymap-mcp/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/hugomrts/porymap-mcp/releases/tag/v0.1.0
