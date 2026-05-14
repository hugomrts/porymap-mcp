# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-14
**Last session:** **`tools/rendering.py` shipped — end-to-end wiring of `compose` + `layout` + `encode` (slice 6 of L3).** New branch `claude/continue-project-C4qpo` on top of merged PR #10. Adds three MCP tools per phase-4 §4: `render_map(project_path, map_name, *, overlays=[], include_border=False, scale=1)`, `render_map_region(project_path, map_name, x1, y1, x2, y2, *, overlays=[], scale=1)`, `render_metatile(project_path, tileset_name, metatile_id, *, scale=4)`. All three return the canonical `ToolResult` shape from `package_render_result`. The pipeline reads primary + secondary `tiles.png` + 13 `.pal` files + both `metatiles.bin` + both `metatile_attributes.bin` per call, composes a combined `[1024, 8, 8]` tile bank, a `[13, 16, 4]` palette bank, and an `[N, 16, 16, 4]` metatile bank (primary padded to slot 512, then secondary), then runs `assemble(bank, mapbin_to_metatile_grid(map_bin))` and encodes. **Numpy/Pillow imports are deferred inside each body** so `import porymap_mcp.tools.rendering` works without the `render` extra. Scale is applied as a numpy nearest-neighbor `repeat`; clamped to 1..8 to stop a typo from producing a 50k-pixel-square PNG. Overlays and `include_border=True` raise explicit "not yet implemented" `ProjectError`s — those slices land next per phase-4 §3. Hard-coded vanilla pokeemerald slot counts (`num_tiles_primary=512`, `num_pals_primary=6`, `num_pals_total=13`, implicit `num_metatiles_primary=512`) live as module constants; a future ADR can surface them on `ProjectConfig` when a fork legitimately overrides one. `server.build_server()` now registers 24 tools (21 L1 + 3 render). **+31 tests** in `tests/unit/tools/test_rendering.py` (suite: 401 → **432 passing**). Coverage: full-render pixel content (every metatile cell's centre pixel asserted), structured-content metadata, nearest-neighbor scale invariant (every 4x4 block in `scale=4` equals the matching 1x1 pixel in `scale=1`), every error path (overlays/include_border unsupported, scale bounds × 4, missing palette file, region bounds × 6, mismatched tileset kind, out-of-range metatile_id, metatile not in bank, missing companion tileset, invalid scale), companion-tileset pairing for `render_metatile`, and the registration smoke. `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (28 source files) + `pytest --no-cov` all clean. Previous slice (encode) earlier on this lineage:

Slice 5 — `render/encode.py` (PNG encode + ToolResult packaging): `encode_png(rgba, *, area_metatiles, force_rgba=False) -> (bytes, EncodingName)` picks palette-vs-RGBA per ADR-0010 §"PNG encoding": palette iff `not force_rgba` AND `area_metatiles <= 4096` AND image is fully opaque AND has ≤ 256 distinct RGBs; RGBA otherwise. **Palette mode is lossless** by construction (`np.unique` over packed RGB → indexed image + custom palette, no Pillow quantize, no dithering) — verified by pixel-identical round-trip tests. `package_render_result(png, *, summary, extra=None)` returns the canonical `ToolResult(content=[Image(...)], structured_content={...})` shape; FastMCP types are late-imported inside the function so the `render` package stays FastMCP-free at module-import time. New error class `PngEncodeError`. +18 tests in `tests/unit/render/test_encode.py`. Previous slice (layout) earlier in the same lineage:

Slice 4 — `render/layout.py` (assembly): Builds on the same branch (`claude/continue-project-EPgUS`) right after the `decode_metatile_bank` commit. New module `src/porymap_mcp/render/layout.py` ships the pure-numpy layout primitive (ADR-0010 §"Layout assembly"): `assemble(bank, grid)` does a single fancy-index + reshape + transpose to produce a C-contiguous `uint8[H*16, W*16, 4]` RGBA image; `assemble_region(bank, grid, *, x1, y1, x2, y2)` is the strict half-open metatile-coord slice for partial renders; `clip_region(grid_shape, ...)` clamps a requested region to bounds (raises only when clipped-to-empty); `mapbin_to_metatile_grid(mb)` adapts the L1 parser's `MapBin` into the `uint16[H, W]` grid this module consumes (collision + elevation dropped — overlay concerns). New error class `LayoutAssemblyError`. **+32 tests** in `tests/unit/render/test_layout.py` (suite: 351 → **383 passing**). Coverage: full assemble pixel-by-pixel + within-tile pixel order + C-contiguous output + multi-dtype grids; full validation (bank shape/dtype/empty, grid shape/dtype/empty, out-of-range/negative IDs); region extraction + 6 parametrized invalid-bounds cases; `clip_region` underflow/overrun/engulf/empty; `mapbin_to_metatile_grid` round-trip via assemble. `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` + `pytest --no-cov` all clean. Border framing (Porymap "include border" wrap-around) deferred to the `tools/rendering.py` wiring slice — the primitive already renders any `border.bin` grid since it's just a small `MapBin`.

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
- `src/porymap_mcp/` — L1 surface (parsers, project, tools, prefabs, 21 L1 tools) plus the `render/` package: `__init__.py` re-exports + `compose.py` (`decode_tile_bank`, `decode_palette_bank`, `decode_metatile_bank` — ADR-0010 §"Source files read" + §"Metatile composition") + `layout.py` (`assemble`, `assemble_region`, `clip_region`, `mapbin_to_metatile_grid` — ADR-0010 §"Layout assembly") + `encode.py` (`encode_png`, `package_render_result`, `PALETTE_MODE_MAX_METATILES`, `EncodingName` — ADR-0010 §"PNG encoding" + §"MCP return shape"). `tools/rendering.py` wires the three render tools end-to-end (`render_map`, `render_map_region`, `render_metatile`), bringing the FastMCP surface to 24 tools. `ProjectConfig` reads `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`. Errors gain `TilesPngFormatError`, `PaletteFormatError`, `MetatilesBinFormatError`, `LayoutAssemblyError`, and `PngEncodeError`.
- `tests/` — 432 passing cases (308 L1 + 43 in `test_compose.py` + 32 in `test_layout.py` + 18 in `test_encode.py` + 31 in `test_rendering.py`). Synthetic PNG + JASC `.pal` + in-memory tile/palette/metatile/grid banks are built in-test, no checked-in binaries.

**Not yet for L3** (next slices): the "wrap-around border frame" composition for `include_border=True` (currently raises explicit not-yet-implemented); `overlays.py` + bundled icon assets (currently raises explicit not-yet-implemented); `return_render` parameter on L1 mutation tools; 5-map fidelity corpus under `tests/fixtures/renders/`; `examples/04_render_loop/`.

**Verified locally + in CI:** `python -m pytest --no-cov` → 432 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 28 source files.

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

Branch with the last session's work: `claude/continue-project-C4qpo`. Three render tools now reachable end-to-end through `build_server()`. Open a PR for this branch, land it, then start the next slice on a clean tree.

**Done in last session** (don't redo):
- ✅ Slice 6: `src/porymap_mcp/tools/rendering.py` — wires `compose` + `layout` + `encode` end-to-end. Three tools registered via `register(mcp)`: `render_map`, `render_map_region`, `render_metatile`. All return `ToolResult` via `package_render_result`. Numpy/Pillow imports deferred inside tool bodies so the L1-only install still imports the module cleanly. Hard-coded vanilla pokeemerald slot counts (`NUM_TILES_PRIMARY=512`, `NUM_PALETTES_PRIMARY=6`, `NUM_PALETTES_TOTAL=13`, `NUM_METATILES_PRIMARY=512`) live as module constants — a future ADR can surface them on `ProjectConfig` when a fork legitimately overrides one. Scale is nearest-neighbor numpy `repeat`, clamped to 1..8. Overlays + `include_border=True` raise explicit "not yet implemented" `ProjectError` so the next slices have a clear extension point.
- ✅ `server.build_server()` registers 24 tools (21 L1 + 3 render).
- ✅ +31 tests in `tests/unit/tools/test_rendering.py` (suite: 401 → **432 passing**). Coverage: full-render pixel content via decoded PNG round-trip, structured-content metadata, nearest-neighbor scale invariant, every error path, companion-tileset pairing for `render_metatile`, registration smoke.
- ✅ `ruff check .` + `ruff format --check .` + `mypy --strict src/porymap_mcp` (28 source files) + `pytest --no-cov` all clean.

**Up next, in order:**

1. **Border framing helper** (still small): replace the `include_border=True` "not yet implemented" raise with a real wrap-around frame. Add `tile_border_around(map_rgba, border_rgba, *, frame_width_metatiles, frame_height_metatiles)` in `layout.py` and call it from `tools/rendering.py::render_map` when `include_border=True`. Defer pixel-perfect fidelity until the fidelity corpus is in place. Porymap "border preview" config defaults to 7 metatiles per side.

2. **`render/overlays.py`** — `collision`, `elevation`, `grid`, `events`. Forces RGBA output. Bundle 12×12 PNG icons under `src/porymap_mcp/render/assets/icons/` (warp, object, sign, trigger, heal). Update `pyproject.toml` `[tool.hatch.build.targets.wheel]` to include the assets dir. Wire each overlay name through `tools/rendering.py`'s `overlays` parameter (currently raises).

3. **`return_render: bool = False` on L1 mutation tools** — phase-4 §4 requires this on every paint/event tool. When `True`, the response carries the `Image` content block in addition to the existing structured dict. The render pipeline is now a function call away — each mutation tool can build a `ToolResult` by chaining its existing structured dict into `package_render_result`'s `extra` kwarg.

4. **5-map fidelity corpus** under `tests/fixtures/renders/`. Each entry has: (a) a project state (synthetic, or a tiny vendored vanilla-pokeemerald slice), (b) a Porymap reference PNG produced with **scale 1×, show connections = off, no overlays, include border per case**. CI compares `np.array_equal(decoded(ours), decoded(reference))`. A `--update-golden` flag regenerates them.

5. **`examples/04_render_loop/`** — paint → render → critique (map-design-critic agent) → fix → re-render. Score must improve measurably.

6. **Tag `v1.0.0`** when phase-4 §2 exit criteria are all checked.

Useful current state:
- `tools/rendering.py` exposes `render_map`, `render_map_region`, `render_metatile` as plain Python functions (testable without FastMCP). The `_tool_*` wrappers carry the LLM-facing docstrings.
- Helpers `_build_combined_tile_bank` / `_build_combined_palette_bank` / `_build_combined_metatile_bank` produce the per-render banks. They lazy-import numpy + render submodules so `import porymap_mcp.tools.rendering` works without the `render` extra.
- The metatile bank is composed twice (once per tileset half) and concatenated; primary is padded to slot 512 with zero metatiles so secondary lands at index 512 even when the primary tileset declares fewer metatiles.
- `tests/unit/tools/test_rendering.py` builds a complete synthetic project under `tmp_path` (primary + secondary tilesets each with 13 `.pal` files, a 3x2 `map.bin`, `metatiles.bin` + `metatile_attributes.bin`, `layouts.json` + `map_groups.json` + `map.json` + `porymap.project.cfg`). The fixture helpers (`_solid_metatile`, `_tile_word`, `_build_tileset`, `_build_project`) can be promoted to a shared `conftest.py` when the next slices need them.
- `parsers/attributes.py` decodes `metatile_attributes.bin` into a tuple of `MetatileAttributes` (`.layer_type: int`).
- `parsers/tileset.py` enumerates tileset directories and produces `TilesetEntry` with paths to `tiles.png`, `palettes/`, `metatiles.bin`, `metatile_attributes.bin`.
- `parsers/mapbin.py::MapBin` is the in-memory layout shape; `layout.mapbin_to_metatile_grid(mb)` adapts it to the numpy grid; the original `MapBin` stays available for overlays (collision/elevation read directly off it).
- `ProjectConfig.enable_triple_layer_metatiles` already exists; `tools/rendering.py` passes `layers=3 if enabled else 2` into `decode_metatile_bank`.
- Mypy in CI runs in an isolated `uv tool` env that does not see numpy/PIL; the override in `pyproject.toml` keeps `mypy --strict` clean. Don't remove it without adding stub packages.

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
