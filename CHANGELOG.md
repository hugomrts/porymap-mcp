# Changelog

All notable changes to `porymap-mcp` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com); the project adheres to
[Semantic Versioning](https://semver.org).

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

- Typed event dataclasses are deferred to v0.2.0 (raw-dict events
  round-trip via `parsers/mapjson`).
- Built-in prefab metatile IDs target vanilla pokeemerald conventions;
  forks may need to register replacement prefabs.
- L2 (live Porymap hot-reload) and L3 (PNG rendering) are planned for
  v0.2.0 / v1.0.0 respectively.

[0.1.0]: https://github.com/hugomrts/porymap-mcp/releases/tag/v0.1.0
