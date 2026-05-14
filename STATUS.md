# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-14
**Last session:** **`compose.decode_metatile_bank` shipped — slice 3 of L3.** The third decoder lands the full ADR-0010 §"Metatile composition" rule: always 3 stacked 16×16 RGBA layers; triple-layer mode reads all three from disk (tiles 0-3 / 4-7 / 8-11); dual-layer mode fills the missing layer from `unused_tile_{normal,covered,split}` selected by the metatile's `LayerType` (Normal → bottom, Covered → top, Split → middle; unknown values fall back to Normal). Tile entries decoded via vectorized numpy bit-fields (id/xflip/yflip/palette); xflip/yflip via numpy slice reversal. Bottom-layer transparency: canvas pre-filled with `transparency_color` (GBA-quantized via `& 0xF8`) when set, else `palette[0][0]` RGB at alpha 255. Out-of-range tile/palette entries silently skipped — matches Porymap's fallback. Confirmed Porymap's `imageproviders.cpp::getMetatileImage` semantics via WebFetch before coding (bare `Tile(id)` ctor → palette 0, no flips; transparency fallback path). New error class `MetatilesBinFormatError`. **+21 tests** under `tests/unit/render/test_compose.py` (43 in this file, **351 in the suite**, was 330 at session start). `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` + `pytest --no-cov` all clean. Branch `claude/continue-project-EPgUS` carries the work.

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
- `src/porymap_mcp/` — L1 surface (parsers, project, tools, prefabs, 21 L1 tools) plus the `render/` package: `__init__.py` re-exports + `compose.py` with `decode_tile_bank`, `decode_palette_bank`, and now `decode_metatile_bank` (ADR-0010 §"Source files read" #1+#2 and §"Metatile composition"). `ProjectConfig` reads `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`. Errors gain `TilesPngFormatError`, `PaletteFormatError`, and `MetatilesBinFormatError`.
- `tests/` — 351 passing cases (308 L1 + 43 in `tests/unit/render/test_compose.py`). Synthetic PNG + JASC `.pal` + in-memory tile/palette banks are built in-test, no checked-in binaries.

**Not yet for L3** (next slices): `layout.py` (W×H assembly + border); `encode.py` (palette-vs-RGBA + FastMCP `ToolResult` packaging); `tools/rendering.py` (`render_map`, `render_map_region`, `render_metatile`); `overlays.py` + bundled icon assets; `return_render` parameter on L1 mutation tools; 5-map fidelity corpus under `tests/fixtures/renders/`; `examples/04_render_loop/`.

**Verified locally + in CI:** `python -m pytest --no-cov` → 351 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 25 source files.

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

Branch with this session's work: `claude/continue-project-EPgUS`. The previous L3-foundation PR (`claude/continue-project-Bqrxp`) was already merged to `main` (commit `c638595`); this branch builds on top of that. Start by merging this branch's PR, then check out `main` fresh.

**Done in last session** (don't redo):
- ✅ `src/porymap_mcp/render/compose.py::decode_metatile_bank` — full ADR-0010 §"Metatile composition" rule: 3 stacked layers, dual-vs-triple mode selection, `LayerType` → `unused_tile_*` mapping (Normal/Covered/Split with switch-default to Normal), xflip/yflip via numpy slice reversal, GBA-quantized `transparency_color` fill on the canvas, palette[0][0] fallback, out-of-range tile/palette skip. Vectorized tile-entry unpacking via `np.frombuffer(..., "<u2")` and bit-field arithmetic. Helper `_entries_at` and constants `DUAL_LAYER_TILES_PER_METATILE`, `TRIPLE_LAYER_TILES_PER_METATILE`, `_QUAD_POSITIONS`.
- ✅ New error class `MetatilesBinFormatError` in `errors.py`.
- ✅ `render/__init__.py` re-exports the new symbols.
- ✅ +21 tests under `tests/unit/render/test_compose.py` (43 total, 351 in the full suite). Coverage: each LayerType branch + unknown-value fallback, triple-layer ignores layer_type, xflip + yflip + combined, transparency_color set + GBA quantization + None fallback, layer z-order, 2×2 quad position mapping, all four validation paths, out-of-range tile/palette skipping, multiple-metatile decoding.
- ✅ `ruff check .` + `ruff format --check .` + `mypy --strict src/porymap_mcp` + `pytest --no-cov` clean.

**Up next, in order:**

1. **`render/layout.py`** — `assemble_layout(metatile_bank, metatile_grid)` via numpy advanced indexing: `out[y*16:(y+1)*16, x*16:(x+1)*16] = metatile_bank[grid[y, x]]`. Vectorize with a single `metatile_bank[grid.reshape(-1)].reshape(H, W, 16, 16, 4).transpose(0, 2, 1, 3, 4).reshape(H*16, W*16, 4)` if the per-cell loop benches over the 100 ms target. Same path for `border.bin`. Crop / region support for `render_map_region` belongs here too.

2. **`render/encode.py`** — palette mode for area ≤ 4096 metatiles and no overlays; RGBA otherwise. FastMCP `ToolResult(content=[Image(data=png_bytes, format="png").to_image_content()], structured_content={...})` per ADR-0010 §"MCP return shape".

3. **`tools/rendering.py`** (new module) — wire `render_map`, `render_map_region`, `render_metatile` per phase-4 §4. Register in `server.py`'s `build_server()`; update the "all-N-tools-registered" assertions in the existing tool tests.

4. **`render/overlays.py`** — `collision`, `elevation`, `grid`, `events`. Forces RGBA output. Bundle 12×12 PNG icons under `src/porymap_mcp/render/assets/icons/` (warp, object, sign, trigger, heal). Update `pyproject.toml` `[tool.hatch.build.targets.wheel]` to include the assets dir.

5. **`return_render: bool = False` on L1 mutation tools** — phase-4 §4 requires this on every paint/event tool. When `True`, the response carries the `Image` content block in addition to the existing structured dict.

6. **5-map fidelity corpus** under `tests/fixtures/renders/`. Each entry has: (a) a project state (synthetic, or a tiny vendored vanilla-pokeemerald slice), (b) a Porymap reference PNG produced with **scale 1×, show connections = off, no overlays, include border per case**. CI compares `np.array_equal(decoded(ours), decoded(reference))`. A `--update-golden` flag regenerates them.

7. **`examples/04_render_loop/`** — paint → render → critique (map-design-critic agent) → fix → re-render. Score must improve measurably.

8. **Tag `v1.0.0`** when phase-4 §2 exit criteria are all checked.

Useful current state:
- `parsers/attributes.py` decodes `metatile_attributes.bin` into a tuple of `MetatileAttributes` (with `.layer_type: int`). `decode_metatile_bank` consumes that directly via its `attributes: Sequence[MetatileAttributes]` parameter.
- `parsers/tileset.py` enumerates tileset directories and produces `TilesetEntry` with paths to `tiles.png`, `palettes/`, `metatiles.bin`, `metatile_attributes.bin`. The render code chains: discover tilesets → `decode_tile_bank` + `decode_palette_bank` + `decode_metatile_bank` per tileset pair → assemble layout (next slice).
- `Project.iter_maps` / `Project.get_map_entry` / layout parser already give us `MapLayout` with `metatile_grid`, `collision_grid`, `elevation_grid`. The `render_map` tool composes existing parsers + the new renderer.
- `ProjectConfig.enable_triple_layer_metatiles` already exists; pass `layers=3 if enabled else 2` into `decode_metatile_bank`.
- Mypy in CI runs in an isolated `uv tool` env that does not see numpy/PIL; the override in `pyproject.toml` keeps `mypy --strict` clean. Don't remove it without adding stub packages.
- The synthetic test helpers in `tests/unit/render/test_compose.py` (`_solid_tile_bank`, `_two_palette_bank`, `_tile_word`, `_metatile_bytes`, `_attr`) are already reusable for the layout tests — promote them to a shared `conftest.py` under `tests/unit/render/` if they get used in 3+ files.

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
