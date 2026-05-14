# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-14
**Last session:** **`return_render: bool = False` on every L1 mutation tool (slice 9 of L3).** Same branch `claude/continue-project-C4qpo`. Adds the parameter to all 12 mutation tools — 7 in `maps.py` (`paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`, `create_map`, `resize_map`, `paint_prefab`) and 5 in `events.py` (`add_warp`, `add_object_event`, `add_sign`, `add_trigger`, `remove_event`). Default `False` preserves the historical L1 contract (each tool still returns `dict[str, Any]`); when `True`, the response becomes a FastMCP `ToolResult` whose `content[0]` is a PNG render of the post-mutation map and whose `structured_content` is the mutation's original dict merged with the render's metadata under a nested `"render"` key. The combined `summary` field appends the render summary to the mutation summary so a single line communicates both halves. A new `maybe_attach_render(response, *, project_path, map_name, return_render)` helper in `tools/_common.py` centralises the wrap: it late-imports `fastmcp.tools.base.ToolResult` and `tools.rendering.render_map`, calls render_map (default opts — no overlays, no border, scale=1), extracts the image block + structured content, and returns either the dict (False) or the wrapped ToolResult (True). The no-op branches (`paint_metatile` on an unchanged tile, `remove_event` on a non-existent id, etc.) still render when requested — the agent gets to see the current state regardless of whether anything was written. Per the user's session-start protocol, the helper deliberately keeps render options frozen for v1.0; an agent that wants overlays or border can still call `render_map` explicitly. Tool docstrings updated to document the new parameter. **+6 tests** in `tests/unit/tools/test_rendering.py` (`TestMutationReturnRender` class): default-returns-dict on `paint_metatile`, `return_render=True` attaches the PNG with verified pixel content (the cell just painted to metatile 1 reads back as blue), structured content carries mutation fields at the top level + render metadata nested under `"render"`, `paint_rectangle` same path, no-op `paint_metatile` still renders, `add_warp` and noop `remove_event` both render. Suite: 454 → **460 passing**. `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (29 source files) + `pytest --no-cov` all clean. Previous slice (overlays) earlier on this branch:

Slice 8 — `render/overlays.py`: New module `src/porymap_mcp/render/overlays.py` ships `apply_collision_overlay`, `apply_elevation_overlay`, `apply_grid_overlay`, `apply_events_overlay`, plus the `apply_overlays(rgba, overlays, *, map_bin, map_json, frame_offset_px)` dispatcher. Each overlay alpha-blends a translucent visualisation onto the assembled RGBA in place: collision draws a red square per impassable cell (distinct hues for `collision >= 2`), elevation paints a 16-colour heat-map keyed by the 4-bit field (no text labels — they'd need a bundled font, deferred), grid lays 1-px lines at every metatile boundary, events paints 12x12 outlined squares colour-coded per class (`object`/`warp`/`coord`/`bg`). All overlays accept a `frame_offset_px=(y, x)` so they place correctly when `include_border=True` has wrapped the map in a border frame. Each blend writes through a shared `_blend_rectangle` helper (clips to bounds, restores `alpha=255` since the underlying map is opaque). The previous `_check_overlays_supported` raise in `tools/rendering.py` is replaced by a "validate against `SUPPORTED_OVERLAYS`" check; the actual dispatch runs after the bank decode. `render_map` and `render_map_region` both pass `force_rgba=True` to `encode_png` whenever any overlay is requested — overlays generate many intermediate RGB values, palette mode would lose to the > 256 colour cap (ADR-0010 §"PNG encoding"). For `render_map_region`, events are passed the full unclipped `MapJson` with a negative `frame_offset_px` equal to the region's top-left in source pixels; events outside the region land off-buffer and clip silently. **+15 tests** total: +13 in `tests/unit/render/test_overlays.py` covering pixel-level blend arithmetic per overlay (collision red shift to (185,70,70), elevation distinct-hues invariant, grid line vs off-boundary delta, event class colours, missing-x/y skip, negative-offset clip, the `apply_overlays` dispatcher's unknown-name error + empty-list no-op + every-supported-name smoke), and the prior reject-tests in `test_rendering.py` are replaced with positive `encoding == "png-rgba-8"` assertions on both `render_map` and `render_map_region`. Suite: 439 → **454 passing**. `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (29 source files) + `pytest --no-cov` all clean. Previous slice (border framing) earlier on this branch:

Slice 7 — `tile_border_around` + `render_map(include_border=True)`: one commit on top of the render-tools slice. New primitive `tile_border_around(map_rgba, border_rgba, *, frame_width_metatiles, frame_height_metatiles) -> uint8[H+2*FH, W+2*FW, 4]` in `render/layout.py` wraps the assembled map in a frame of the small `border.bin` tiled by its own pixel dimensions (`border_rgba[y % bH, x % bW]`), anchored at the output's top-left — matches Porymap's "include border" exporter. Vectorized via numpy modulo + fancy-index (single C-level copy). New shared `_validate_rgba(rgba, *, name)` helper enforces uint8 + multiple-of-16 dimensions; reused for both `map_rgba` and `border_rgba`. In `tools/rendering.py::render_map`, the previous `include_border=True` "not yet implemented" raise is replaced by: read `border.bin` → `mapbin_to_metatile_grid` → `assemble` (against the same combined metatile bank) → `tile_border_around(...)` with the new `DEFAULT_BORDER_FRAME_METATILES=7` constant (Porymap's `BorderMetatilesData::DEFAULT_BORDER_SIZE`). The `area_metatiles` passed to `encode_png` is widened by the frame so palette-vs-RGBA mode selection still applies the ADR-0010 threshold correctly. Structured content gains `border_dimensions` and `border_frame_metatiles` when `include_border=True`. **+7 unit tests** in `tests/unit/render/test_layout.py` for the primitive (solid-border wrap, modulo tiling phase, zero-frame copy, asymmetric frame, 3 validation cases), and the existing reject-test in `tests/unit/tools/test_rendering.py` is replaced with a positive end-to-end test that decodes the PNG and asserts the border corner + map centre pixels (suite: 432 → **439 passing**). `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (28 source files) + `pytest --no-cov` all clean. Previous slice (rendering tools) earlier on this branch:

Slice 6 — `tools/rendering.py`: end-to-end wiring of `compose` + `layout` + `encode`. Adds three MCP tools per phase-4 §4: `render_map(project_path, map_name, *, overlays=[], include_border=False, scale=1)`, `render_map_region(project_path, map_name, x1, y1, x2, y2, *, overlays=[], scale=1)`, `render_metatile(project_path, tileset_name, metatile_id, *, scale=4)`. All three return the canonical `ToolResult` shape from `package_render_result`. The pipeline reads primary + secondary `tiles.png` + 13 `.pal` files + both `metatiles.bin` + both `metatile_attributes.bin` per call, composes a combined `[1024, 8, 8]` tile bank, a `[13, 16, 4]` palette bank, and an `[N, 16, 16, 4]` metatile bank (primary padded to slot 512, then secondary), then runs `assemble(bank, mapbin_to_metatile_grid(map_bin))` and encodes. **Numpy/Pillow imports are deferred inside each body** so `import porymap_mcp.tools.rendering` works without the `render` extra. Scale is applied as a numpy nearest-neighbor `repeat`; clamped to 1..8 to stop a typo from producing a 50k-pixel-square PNG. Overlays and `include_border=True` raise explicit "not yet implemented" `ProjectError`s — those slices land next per phase-4 §3. Hard-coded vanilla pokeemerald slot counts (`num_tiles_primary=512`, `num_pals_primary=6`, `num_pals_total=13`, implicit `num_metatiles_primary=512`) live as module constants; a future ADR can surface them on `ProjectConfig` when a fork legitimately overrides one. `server.build_server()` now registers 24 tools (21 L1 + 3 render). **+31 tests** in `tests/unit/tools/test_rendering.py` (suite: 401 → **432 passing**). Coverage: full-render pixel content (every metatile cell's centre pixel asserted), structured-content metadata, nearest-neighbor scale invariant (every 4x4 block in `scale=4` equals the matching 1x1 pixel in `scale=1`), every error path (overlays/include_border unsupported, scale bounds × 4, missing palette file, region bounds × 6, mismatched tileset kind, out-of-range metatile_id, metatile not in bank, missing companion tileset, invalid scale), companion-tileset pairing for `render_metatile`, and the registration smoke. `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (28 source files) + `pytest --no-cov` all clean. Previous slice (encode) earlier on this lineage:

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
- `tests/` — 460 passing cases (308 L1 + 43 in `test_compose.py` + 39 in `test_layout.py` + 18 in `test_encode.py` + 13 in `test_overlays.py` + 39 in `test_rendering.py`). Synthetic PNG + JASC `.pal` + in-memory tile/palette/metatile/grid banks are built in-test, no checked-in binaries.

**Not yet for L3** (next slices): 5-map fidelity corpus under `tests/fixtures/renders/`; `examples/04_render_loop/`. Future enhancement (deferred): replace overlay event squares with 12x12 PNG icons under `src/porymap_mcp/render/assets/icons/` + font-based elevation labels — both require committing binary assets.

**Verified locally + in CI:** `python -m pytest --no-cov` → 460 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 29 source files.

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

1. **5-map fidelity corpus** under `tests/fixtures/renders/`. Each entry has: (a) a project state (synthetic, or a tiny vendored vanilla-pokeemerald slice), (b) a Porymap reference PNG produced with **scale 1×, show connections = off, no overlays, include border per case**. CI compares `np.array_equal(decoded(ours), decoded(reference))`. A `--update-golden` flag regenerates them. This is the last technical gate before `v1.0.0`.

2. **`examples/04_render_loop/`** — paint → render → critique (map-design-critic agent) → fix → re-render. Score must improve measurably. The critique loop is the project's reason to exist (CLAUDE.md §3); without a worked example, the feature exists but the workflow isn't demonstrated.

3. **Tag `v1.0.0`** when phase-4 §2 exit criteria are all checked. Update `CHANGELOG.md` and the README's "first map in 5 minutes" path to show the L3 loop.

4. *Optional enhancement, deferred:* swap overlay event squares for 12x12 PNG icons + bundle a small bitmap font for elevation labels. Both need committed binary assets and a `pyproject.toml` wheel-include change.

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
