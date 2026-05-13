# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** **Phase 3 abandoned, Phase 4 (L3 — Vision) opened, design locked, and the first two implementation slices shipped.** First third of the session: static-source audit established L2 is not achievable (no JS file-read primitives, native `QFileSystemWatcher` excludes `map.bin`/`map.json`, no `map.reload()` Q_INVOKABLE); abandoned in [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). Versioning: `v0.2.0` intentionally skipped; next ship is `v1.0.0`. Second third: two parallel audits of the L3 decode pipeline and the Python rendering stack produced [ADR-0010](docs/decisions/0010-l3-renderer-design.md) — **numpy + Pillow** under the `render` extra; read `tiles.png` + JASC `.pal` (skip compiled `.4bpp`/`.gbapal`); apply **GBA 5-bit palette quantization** (`& 0xF8`); always compose 3 metatile layers, filling the missing one in dual-layer mode from `unused_tile_{normal,covered,split}`; pixel-identical RGBA fidelity (not byte-identical PNG); MCP shape `ToolResult(content=[Image(...)], structured_content={...})`; no connection rendering in v1.0; `tile.py` + `metatile.py` merged into `compose.py`. Last third: **shipped two implementation slices** — (1) L3 foundation: numpy added to the `render` extra, ProjectConfig extended with `transparency_color`, `unused_tile_{normal,covered,split}` (commit `c3a5121`, +8 tests); (2) `compose.py` slice 1 — `decode_tile_bank` and `decode_palette_bank` with GBA 5-bit quantization, palette-0 transparency rule, and full edge-case coverage (commit `2304bf8`, +22 tests). New error classes `TilesPngFormatError` and `PaletteFormatError`. **330 passing tests** (was 300 at session start), ruff + ruff format + mypy --strict all clean. Branch `claude/continue-project-Bqrxp` has 4 commits ahead of `main`; PR open for merge.

---

## Current phase

**Phase 4 — L3: Vision** (active).
Active doc: [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md)

L3 closes the project's quality loop (`paint → render → critique → fix → re-render`) by rendering maps to PNG server-side and returning them as MCP `image` content blocks. This is what `CLAUDE.md` §3 calls "the reason the project exists in its final form". Investigation of the GBA tileset / metatile rendering pipeline is the immediate next task (delegate to `map-renderer` + `porymap-format-expert`); the design will be locked in ADR-0010 before any code lands under `src/porymap_mcp/render/`.

PyPI publish (Phase 5) remains deferred per owner directive: publish only once L3 ships and there is real visual value to demonstrate. `v0.1.0` stays a GitHub tag, not a PyPI release.

---

## What exists in the repo today

- `MCP_PORYMAP.md` — strategic vision (FR).
- `CLAUDE.md` — operating manual.
- `STATUS.md` — this file.
- `.claude/agents/` — 7 sub-agents.
- `.claude/settings.json`, `.gitignore`.
- `docs/phases/` — phase 1 closed, phase 2 closed (v0.1.0 shipped), phase 3 abandoned (ADR-0009), phase 4 active, phase 5 deferred.
- `docs/decisions/` — ADRs 0001–0010 (0009 abandons L2, 0010 locks the L3 renderer design).
- `pyproject.toml`, `LICENSE`, `README.md` (with "first map in 5 minutes"), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`. `render` optional extra carries `Pillow>=10.0` + `numpy>=1.26` (ADR-0010); mypy override added for `numpy.*` and `PIL.*`.
- `src/porymap_mcp/` — L1 surface (parsers, project, tools, prefabs, 21 L1 tools) plus the new `render/` package: `__init__.py` re-exports + `compose.py` with `decode_tile_bank` and `decode_palette_bank` (ADR-0010 §"Source files read" #1 + #2). `ProjectConfig` now reads `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`. Errors gain `TilesPngFormatError` and `PaletteFormatError`.
- `tests/` — 330 passing cases (308 L1 + 22 new for compose). Synthetic PNG + JASC `.pal` fixtures are built in-test, no checked-in binaries.

**Not yet for L3** (next slices): `compose.decode_metatile_bank` with the 3-layer `unused_tile_*` fill rule; `layout.py` (W×H assembly + border); `encode.py` (palette-vs-RGBA + FastMCP `ToolResult` packaging); `tools/rendering.py` (`render_map`, `render_map_region`, `render_metatile`); `overlays.py` + bundled icon assets; `return_render` parameter on L1 mutation tools; 5-map fidelity corpus under `tests/fixtures/renders/`; `examples/04_render_loop/`.

**Verified locally + in CI:** `python -m pytest --no-cov` → 330 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 25 source files.

**Integration-tested:** `rh-hideout/pokeemerald-expansion` (L1 only — no L3 integration test yet; the fidelity corpus is the next big chunk).

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | ✅ Closed | `v0.1.0` tagged 2026-05-13. |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | ❌ Abandoned | See [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). `v0.2.0` skipped. |
| 4 — L3 (Vision) | Server renders maps to PNG | **Active** | Read [phase-4 doc](docs/phases/phase-4-l3-vision.md); investigate GBA tile/palette/metatile decode pipeline (`map-renderer` + `porymap-format-expert`); lock the renderer design in ADR-0010 before coding. |
| 5 — Release | Publish to PyPI + community announcement | Deferred | Publish only when L3 ships and there's real visual value to demonstrate. No work until then. |

---

## Open decisions (blocking next work)

- [x] **Poryscript vs raw `.inc`** — resolved by ADR-0007: poryscript default, `.inc` fallback when `use_poryscript=0`.
- [x] **Prefab auto-import** — resolved by ADR-0008: reject on tileset mismatch, no auto-import.
- [x] **Typed event dataclasses** — deferred to v0.2.0 per ADR-0007 §"Decision"; raw-dict events suffice for L1.
- [x] **L2 (Live Porymap) feasibility** — resolved by ADR-0009: abandoned. Pivot to L3.
- [x] **Renderer design** — resolved by ADR-0010: numpy + Pillow, artist-source files (`tiles.png` + JASC `.pal`), GBA 5-bit palette quantization, 3-layer composition with `unused_tile_*` fill, pixel-identical fidelity, FastMCP `ToolResult` + `Image` return shape, no connection rendering in v1.0.

Resolved decisions live under [`docs/decisions/`](docs/decisions/). No open decisions block the next session.

---

## Next session pickup (L3 implementation in progress)

Branch with this session's work: `claude/continue-project-Bqrxp`. 4 commits ahead of `main`; PR open. Start by merging that PR, then check out `main` fresh.

**Done in last session** (don't redo):
- ✅ ADR-0009: abandon L2. ADR-0010: lock L3 renderer design.
- ✅ Phase 3 doc marked Abandoned; phase 4 doc marked Active with the renderer spec.
- ✅ `pyproject.toml`: `render` extra now `["Pillow>=10.0", "numpy>=1.26"]`. mypy overrides for `numpy.*` and `PIL.*`.
- ✅ `ProjectConfig`: 4 new typed accessors (`transparency_color`, `unused_tile_{normal,covered,split}`) + `_parse_rgb` helper.
- ✅ `src/porymap_mcp/render/compose.py`: `decode_tile_bank` (tiles.png → `uint8[num_tiles, 8, 8]` palette indices, `& 0x0F` mask, row-major slicing) and `decode_palette_bank` (JASC `.pal` → `uint8[num_palettes, 16, 4]` RGBA with GBA `& 0xF8` quantization and palette-0 alpha-0).
- ✅ New error classes: `TilesPngFormatError`, `PaletteFormatError`.
- ✅ 22 new tests under `tests/unit/render/test_compose.py`. Total 330 passing. ruff + format + mypy --strict clean.

**Up next, in order:**

1. **`compose.decode_metatile_bank`** — the third decoder. Reads `metatiles.bin` (16 bytes/metatile dual-layer, 24 bytes/metatile triple-layer; auto-detected from file size against `num_metatiles`) and `metatile_attributes.bin` (already parsed by `parsers/attributes.py` for the LayerType bits). For each metatile, compose a `16×16×4` RGBA image:
   - Triple-layer mode: 3 layers from disk (tiles 0–3 / 4–7 / 8–11).
   - Dual-layer mode: 2 layers from disk + 1 fill layer from `ProjectConfig.unused_tile_{normal,covered,split}` based on the metatile's LayerType (table in ADR-0010 §"Metatile composition").
   - Apply tile xflip/yflip from the 2-byte tile entry (bits 10/11; ADR-0010 §"Metatile composition").
   - Apply palette index 0 transparency on the **upper two** layers; the **bottom** layer fills its palette-0 pixels with the `transparency_color` config value when set, else palette-0-of-palette-0's RGB.
   - Signature suggestion: `decode_metatile_bank(metatiles_bytes, attributes, tile_bank, palette_bank, *, layers, unused_tile_normal, unused_tile_covered, unused_tile_split, transparency_color) -> np.ndarray[num_metatiles, 16, 16, 4]`.
   - Tests: 4-metatile synthetic tileset; cover each LayerType branch; cover xflip+yflip; cover triple-layer; cover unused-tile fill; cover transparency_color fallback.

2. **`render/layout.py`** — `assemble_layout(metatile_bank, metatile_grid)` via numpy advanced indexing: `out[y*16:(y+1)*16, x*16:(x+1)*16] = metatile_bank[grid[y, x]]`. Add the same path for `border.bin`. Crop / region support for `render_map_region` belongs here too.

3. **`render/encode.py`** — palette mode for area ≤ 4096 metatiles and no overlays; RGBA otherwise. FastMCP `ToolResult(content=[Image(data=png_bytes, format="png").to_image_content()], structured_content={...})` per ADR-0010 §"MCP return shape".

4. **`tools/rendering.py`** (new module) — wire `render_map`, `render_map_region`, `render_metatile` per phase-4 §4. Register in `server.py`'s `build_server()`; update the "all-N-tools-registered" assertions in the existing tool tests.

5. **`render/overlays.py`** — `collision`, `elevation`, `grid`, `events`. Forces RGBA output. Bundle 12×12 PNG icons under `src/porymap_mcp/render/assets/icons/` (warp, object, sign, trigger, heal). Update `pyproject.toml` `[tool.hatch.build.targets.wheel]` to include the assets dir.

6. **`return_render: bool = False` on L1 mutation tools** — phase-4 §4 requires this on every paint/event tool. When `True`, the response carries the `Image` content block in addition to the existing structured dict.

7. **5-map fidelity corpus** under `tests/fixtures/renders/`. Each entry has: (a) a project state (synthetic, or a tiny vendored vanilla-pokeemerald slice), (b) a Porymap reference PNG produced with **scale 1×, show connections = off, no overlays, include border per case**. CI compares `np.array_equal(decoded(ours), decoded(reference))`. A `--update-golden` flag regenerates them.

8. **`examples/04_render_loop/`** — paint → render → critique (map-design-critic agent) → fix → re-render. Score must improve measurably.

9. **Tag `v1.0.0`** when phase-4 §2 exit criteria are all checked.

Useful current state:
- `parsers/attributes.py` already decodes `metatile_attributes.bin` and exposes the `LayerType` enum. `decode_metatile_bank` consumes that output unchanged.
- `parsers/tileset.py` already enumerates tileset directories and produces `TilesetEntry` with paths to `tiles.png`, `palettes/`, `metatiles.bin`, `metatile_attributes.bin`. The render code chains: discover tilesets → load tile bank + palette bank + metatile bank per tileset pair → assemble layout.
- `Project.iter_maps` / `Project.get_map_entry` / layout parser already give us `MapLayout` with `metatile_grid`, `collision_grid`, `elevation_grid`. The `render_map` tool composes existing parsers + the new renderer.
- Mypy in CI runs in an isolated `uv tool` env that does not see numpy/PIL; the override in `pyproject.toml` keeps `mypy --strict` clean. Don't remove it without adding stub packages.
- The synthetic-PNG / synthetic-JASC test helpers in `tests/unit/render/test_compose.py` (`_write_indexed_png`, `_make_jasc`, `_identity_palette`) are reusable for the metatile-bank tests — promote them to a shared `conftest.py` under `tests/unit/render/` if they get used in 3+ files.

## Outstanding chores (not blocking L3)

- **PyPI publish** (Phase 5). Deferred per owner directive: publish with L3, not before. No action required this phase.
- **`gTileset_LittlerootTown` example in README.** The README's "first map" example uses `gTileset_LittlerootTown` as a placeholder, which does NOT exist in `rh-hideout/pokeemerald-expansion` (real label: `gTileset_Petalburg`). Vanilla pokeemerald *does* have `gTileset_LittlerootTown` though. Decision: leave the README as-is (vanilla is the documented baseline), or note both? Pure docs change.

---

## Quick links

- Vision: [`MCP_PORYMAP.md`](MCP_PORYMAP.md)
- Operating manual: [`CLAUDE.md`](CLAUDE.md)
- Current phase: [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md)
- ADRs: [`docs/decisions/`](docs/decisions/)

---

## Session handoff convention

**Starting a session:**
1. Read this file.
2. Read the current phase doc (linked above under "Current phase").
3. Check the open decisions section — if your task touches one, resolve it first (write an ADR).

**Ending a session:**
1. Update the phase doc's task checklist and "Session log" section.
2. Update this file's "Last session" line and any phase that changed status.
3. If you took a non-reversible decision, write an ADR in `docs/decisions/`.
4. Commit all three (phase doc + STATUS.md + optional ADR) together — never split them.
