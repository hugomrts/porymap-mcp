# ADR-0004: Tileset metadata is filesystem-first, C-struct lexer is a deferred enrichment

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** Hugo Martins

---

## Context

When integrating an orphan-branch parser session in the previous step, we
discovered that **`data/tilesets/headers.json` does not exist** in
pokeemerald-family decomps. The canonical source of tileset metadata —
which tilesets exist, primary vs. secondary classification, the asset
paths (tiles, palettes, metatiles, attributes), `isCompressed`, and the
init `callback` — lives in C source under
`src/data/tilesets/headers.h` as `const struct Tileset gTileset_* = { ... };`.

Verified facts:

- The `struct Tileset` shape **differs between RSE and FRLG**: in
  pokefirered the `metatileAttributes` field is `const u32 *` (4-byte attrs)
  and the field order swaps `callback` and `metatileAttributes`. All pret
  repos and pokeemerald-expansion use designated initializers
  (`.field = value`), so a parser that keys on field names (not order) is
  portable across the three variants.
- Porymap parses these via `Project::readTilesetLabels` →
  `parser.readCStructs(...)`, and uses **only five fields**: `isSecondary`,
  `tiles`, `palettes`, `metatiles`, `metatileAttributes`. The pointer
  fields are kept as label names then resolved through `INCBIN` / `INCGFX`
  in `data/tilesets/graphics.h` and `data/tilesets/metatiles.h`.
  `isCompressed` and `callback` are read but unused for editing.
- A legacy ASM fallback (`headers.inc`) exists but is dead code in any
  modern (post-2022) project. pokeemerald-expansion ships only `headers.h`.
- Per-tileset assets live under `data/tilesets/{primary,secondary}/<name>/`
  with a conventional layout: `tiles.png`, `metatiles.bin`,
  `metatile_attributes.bin`, `palettes/00.pal`–`15.pal`, optional `anim/`.
  Naming convention from directory basename to C label
  (`petalburg_woods` → `gTileset_PetalburgWoods`) is mechanical in
  vanilla and expansion but **not guaranteed** for arbitrary forks.

The L1 milestone needs to surface tilesets to the agent
(`list_tilesets`, `list_metatiles`) and resolve the `primary_tileset` /
`secondary_tileset` C-symbol references in `layouts.json` to on-disk
asset directories. It does not need to **create** new tilesets — that
stays in Porymap. So the question is: how do we get from a C-symbol like
`gTileset_PetalburgWoods` to the four asset paths and back?

---

## Decision

We adopt a **two-stage strategy**, shipped in two passes:

### Stage 1 (ships in v0.1.0) — filesystem-first discovery

`parsers/tileset.py` provides `discover_tilesets(project: Project) -> tuple[TilesetEntry, ...]`
implemented by globbing:

```
<project_root>/data/tilesets/primary/*/
<project_root>/data/tilesets/secondary/*/
```

Each `TilesetEntry` carries:

- `name: str` — directory basename, e.g. `"petalburg_woods"`.
- `c_label: str` — derived by snake_case → `gTileset_<PascalCase>`
  convention. Marked `unverified=True` in stage 1.
- `kind: Literal["primary", "secondary"]` — from the parent directory.
- `tiles_path: PosixPath`, `metatiles_path: PosixPath`,
  `attributes_path: PosixPath`, `palettes_dir: PosixPath` — derived from
  the conventional layout.
- `is_compressed: bool | None` — `None` in stage 1 (not yet known).

This is enough for `list_tilesets`, `list_metatiles`, and for the
`Project` layer to map `layouts.json`'s `primary_tileset` field
(`"gTileset_*"`) back to a `TilesetEntry` whenever the convention holds.

If the convention does not hold (a tileset whose directory basename
yields a different C label than what `layouts.json` references), the
mapping fails fast with a clear error and the user is told to either
rename the directory or wait for stage 2.

### Stage 2 (ships when mutation tooling needs it) — C-struct lexer enrichment

When stage 1 returns "tileset C-label resolution failed" *or* a tool
needs `is_compressed` / asset paths that diverge from the convention,
we add a minimal C-struct lexer:

`parsers/tilesetheaders.py` parses `src/data/tilesets/headers.h` as a
sequence of `const struct Tileset <ident> = { .field = value, ... };`
declarations. Only enough grammar to recognize designated initializers
keyed by name; values are C identifiers, `TRUE`/`FALSE`/`NULL`, or
integer literals.

A second lexer parses the `INCBIN` / `INCGFX` declarations in
`data/tilesets/graphics.h` and `data/tilesets/metatiles.h` to resolve
each label (`gTilesetTiles_PetalburgWoods`) to a project-relative path.

Stage 2 augments stage 1's `TilesetEntry` with verified `c_label`,
`is_compressed`, and any non-conventional asset path. Stage 1's output
remains correct for projects that follow the convention; stage 2 is
purely additive.

**Stage 2 is not part of v0.1.0.** It ships when a concrete L1 tool
needs information stage 1 cannot provide — most likely `list_metatiles`
once we discover a real expansion fork that names assets unconventionally.

### What we do not do, ever

- We do not modify Porymap to maintain a JSON cache.
- We do not run Porymap headlessly to extract metadata.
- We do not parse the `.inc` ASM fallback. If a project lacks
  `headers.h`, we error out with "open this project once in a recent
  Porymap to migrate". Modern decomps always ship `.h`.
- We do not support **creating** new tilesets in L1. That requires
  writing `headers.h` + `graphics.h` + `metatiles.h` and is a Porymap
  workflow.

---

## Alternatives considered

### Alternative 1 — C-struct lexer from day one

Skip stage 1; ship the lexer immediately as the only metadata source.

- **Upside:** matches Porymap's behavior exactly; no naming-convention
  drift; `is_compressed` always available.
- **Downside:** ~250 LOC of brittle parser (must defend against
  preprocessor `#ifdef` blocks, multi-line macros, comments inside brace
  blocks); needs the `INCBIN`/`INCGFX` resolver too; no production
  tooling needs the data it adds in v0.1.0.
- **Why not:** L1's needs (`list_tilesets`, `list_metatiles`,
  layout→tileset resolution) are met by filesystem inspection for ~99%
  of vanilla and expansion projects. We prefer to ship working
  discovery now and add the lexer when a real user hits its absence,
  rather than carry the maintenance cost speculatively.

### Alternative 2 — Lean on Porymap to maintain a JSON cache

Have the user run a Porymap export to produce a tileset manifest we
read.

- **Upside:** zero parsing on our side.
- **Downside:** Porymap writes no such cache today; getting one upstream
  would take months and break our "Porymap not required" L1 promise;
  even if Porymap added it, we'd depend on the user remembering to
  re-export after every tileset change.
- **Why not:** violates L1's foundational contract.

### Alternative 3 — Defer tileset awareness entirely to L3 (rendering)

Treat tileset names as opaque strings in L1; only L3 resolves them
(because rendering needs the actual tile graphics).

- **Upside:** no tileset code in v0.1.0 at all.
- **Downside:** `list_tilesets` and `list_metatiles` are L1 tools per
  the frozen spec; deferring them breaks Phase 2 exit criteria. Layout
  validation also needs to know primary vs. secondary classification to
  reject obviously broken configurations.
- **Why not:** L1 tool surface already commits to surfacing tileset
  information.

### Alternative 4 — ASM `.inc` parser as a third tier

Parse `headers.inc` for projects that don't ship `headers.h`.

- **Upside:** covers very old pokeruby snapshots.
- **Downside:** zero modern target uses this path; double the parser
  surface for ~0% real-world coverage.
- **Why not:** YAGNI. Document the limitation and tell the user to
  migrate their project (Porymap itself migrates on first save).

---

## Consequences

**Positive:**
- v0.1.0 ships with working tileset discovery and zero new parser
  brittleness. `parsers/tileset.py` is ~80 LOC of `pathlib.glob`.
- Stage 2 is a clean additive upgrade — no API breaks, just richer
  `TilesetEntry` fields.
- Naming-convention violations fail fast with an actionable error
  ("rename this directory or upgrade to porymap-mcp 0.2 with the C
  parser") rather than producing silently-wrong output.
- The lexer, when it lands, is implementable in a focused session with
  the `porymap-format-expert` subagent. Until then, no one carries the
  cognitive load of a half-written C parser.

**Negative:**
- Forks that store tilesets outside `data/tilesets/{primary,secondary}/`
  break in v0.1.0. We accept this — those forks are unusual and will
  push us to ship stage 2.
- `is_compressed` is unavailable in v0.1.0. No L1 tool needs it (it's a
  write-back concern). Documented in `TilesetEntry`.
- Two-stage rollout means contributors must remember which stage we're
  in when adding tileset-touching code. Mitigated by the
  `unverified=True` flag on `c_label` and a clear `TilesetEntry`
  docstring.

**Neutral:**
- The directory-basename → C-label convention
  (`some_name` → `gTileset_SomeName`) is encoded in one helper
  function; if a fork breaks it, only that helper changes when stage 2
  lands.

---

## References

- Related ADRs:
  - [ADR-0002](0002-target-pokeemerald-expansion-first.md) — supported
    base games drive which `headers.h` shapes we may encounter.
  - [ADR-0003](0003-project-class-and-config-driven-format.md) — `Project`
    is the entrypoint; `discover_tilesets` will hang off it as a lazy
    property when implemented.
- Porymap source:
  - `src/project.cpp` — `readTilesetLabels`, `readTilesetPaths`,
    `getTileset` (https://github.com/huderlem/porymap/blob/master/src/project.cpp)
  - `src/parseutil.cpp` — `readCStructs`, `readCIncbin`
- pokeemerald struct definition:
  `include/global.fieldmap.h` (https://github.com/pret/pokeemerald/blob/master/include/global.fieldmap.h)
- pokefirered struct definition (field-order divergence):
  `include/global.fieldmap.h` (https://github.com/pret/pokefirered/blob/master/include/global.fieldmap.h)
- pokeemerald-expansion sample `headers.h`:
  https://github.com/rh-hideout/pokeemerald-expansion/blob/master/src/data/tilesets/headers.h
- Phase doc affected: [`phase-2-l1-filesystem.md`](../phases/phase-2-l1-filesystem.md)
  — unblocks `parsers/tileset.py` (stage 1 only) and the discovery tools
  built on top of it.
