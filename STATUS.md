# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-14
**Last session:** **L3 example loop shipped + public-face docs refreshed for L3** (2 commits on `claude/continue-project-ax6Mm`, PR not yet opened). Slice 10 added `examples/04_render_loop/` — a runnable script + walkthrough README that exercises the full `paint → render → critique → fix → re-render` loop end-to-end on a synthetic 8x6 "coastal town" project, with two committed render PNGs (`renders/iter{1,2}.png`, ≈ 2.7 KB total) showing the score jumping from 7/36 to 21/36. Slice 10b refreshed `README.md` (status banner, capability bullets, levels table, new "See your map (L3)" section with both PNGs inline, updated tool surface listing the 3 render tools + `return_render` flag) and `CHANGELOG.md` (new `[Unreleased] — v1.0.0 candidate` section covering the full L3 surface, render extra, new errors, and known limitations). Suite still **460 passing**; `ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (29 source files) all clean. Only the 5-map fidelity corpus remains before `v1.0.0` — blocked on Porymap-exported reference PNGs and is the next session's job (see "Up next"). Per-slice writeup lives in [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md) §9.

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

- `examples/04_render_loop/` — `run_demo.py` (≈ 400 LOC bootstrapping a synthetic project + driving the iter-1/iter-2 loop via `porymap_mcp.tools.{maps,rendering}`), `README.md` (loop concept + prompt template + 12-axis scoring table + cross-refs), and two committed render artefacts `renders/iter{1,2}.png` showing the score jump from 7/36 to 21/36. `_demo_project/` is gitignored — regenerated each run.

**Not yet for L3** (last remaining slice): 5-map fidelity corpus under `tests/fixtures/renders/`. Future enhancement (deferred): replace overlay event squares with 12x12 PNG icons under `src/porymap_mcp/render/assets/icons/` + font-based elevation labels — both require committing binary assets.

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

Branch with the last session's work: `claude/continue-project-ax6Mm` — opened as a PR carrying one commit (slice 10). **Before starting work**: verify the PR is merged, then `git checkout main && git pull` for a clean tree. If the PR is still open, the next session's job is *just to land it* (review CI, fix any drift) — do not start the fidelity-corpus slice on a stale base.

**Done in this session** (don't redo) — one slice on one branch, one commit:

- ✅ Slice 10: `examples/04_render_loop/` — runnable demo (`run_demo.py`) + walkthrough README + two committed render PNGs. Closes the phase-4 §2 self-critique-loop exit criterion. The script uses only the public Python API of `porymap_mcp.tools.{maps,rendering}` and prints an illustrative critique narrative inline; a real Claude session swaps the hardcoded critique for a `Task(subagent_type="map-design-critic")` call against the same PNG. Suite unchanged at 460 passing; the example doesn't add tests (would re-test the synthetic-fixture path already covered by `test_rendering.py`).

**Done in previous session** (don't redo, kept for context) — four slices on the prior branch (merged via PR #11):

- ✅ Slice 6 (commit `a552b10`): `tools/rendering.py` — end-to-end wiring of `compose` + `layout` + `encode`. Three tools registered through `build_server()`: `render_map`, `render_map_region`, `render_metatile`. All return `ToolResult` via `package_render_result`. Numpy/Pillow imports deferred inside each tool body so the L1-only install still imports the module. Hard-coded vanilla pokeemerald slot counts (`NUM_TILES_PRIMARY=512`, `NUM_METATILES_PRIMARY=512`, `NUM_TILES_TOTAL=NUM_METATILES_TOTAL=1024`, `NUM_PALETTES_PRIMARY=6`, `NUM_PALETTES_TOTAL=13`) as module constants. Scale clamped to 1..8 via numpy `repeat`. +31 tests.
- ✅ Slice 7 (commit `f5b335c`): `tile_border_around(map_rgba, border_rgba, *, frame_width_metatiles, frame_height_metatiles)` in `render/layout.py` + wired through `render_map(include_border=True)`. Tiles the small `border.bin` by its pixel dimensions in a single numpy fancy-index pass. New `DEFAULT_BORDER_FRAME_METATILES=7` constant (Porymap's `BorderMetatilesData::DEFAULT_BORDER_SIZE`). Structured content gains `border_dimensions` + `border_frame_metatiles`. `area_metatiles` passed to `encode_png` is widened by the frame so the palette-vs-RGBA threshold still applies. +7 tests.
- ✅ Slice 8 (commit `2ae8882`): `render/overlays.py` — `apply_{collision,elevation,grid,events}_overlay` + `apply_overlays` dispatcher. Each function alpha-blends a translucent visualisation in place via a shared `_blend_rectangle` helper. Collision=red squares (distinct hues for ≥2), elevation=16-colour heat-map, grid=1-px lines at metatile boundaries, events=12x12 outlined squares colour-coded per class. Wired through `render_map` and `render_map_region`; `force_rgba=True` whenever overlays are active. The previous `_check_overlays_supported` raise is now a `SUPPORTED_OVERLAYS` validation. For region renders, events get the unclipped `MapJson` with a negative `frame_offset_px` so out-of-region events clip silently. +15 tests (13 primitive + 2 replaced reject-tests).
- ✅ Slice 9 (commit `149e91f`): `return_render: bool = False` on every L1 mutation tool — 7 in `maps.py` (`paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`, `create_map`, `resize_map`, `paint_prefab`) + 5 in `events.py` (`add_warp`, `add_object_event`, `add_sign`, `add_trigger`, `remove_event`). New `maybe_attach_render(response, *, project_path, map_name, return_render)` helper in `tools/_common.py` centralises the wrap. Default `False` preserves the historical `dict[str, Any]` contract; `True` returns a `ToolResult` with the PNG image block and the mutation's dict merged with render metadata under a nested `"render"` key. The combined `summary` appends the render summary to the mutation summary. No-op branches still render. `register_map`/`unregister_map` deliberately *not* touched (no pixel impact). Phase-4 §2's `return_render` exit-criterion checkbox is now ticked. +6 tests.

**End-state across the four slices:**
- `server.build_server()` registers 24 tools (21 L1 + 3 render).
- Suite: 401 → **460 passing** (308 L1 + 43 in `test_compose.py` + 39 in `test_layout.py` + 18 in `test_encode.py` + 13 in `test_overlays.py` + 39 in `test_rendering.py`).
- `ruff check .` + `ruff format --check .` + `mypy --strict src/porymap_mcp` (29 source files) + `pytest --no-cov` all clean.

**Up next, in order:**

1. **5-map fidelity corpus** under `tests/fixtures/renders/`. Each entry has: (a) a project state (synthetic, or a tiny vendored vanilla-pokeemerald slice), (b) a Porymap reference PNG produced with **scale 1×, show connections = off, no overlays, include border per case**. CI compares `np.array_equal(decoded(ours), decoded(reference))`. A `--update-golden` flag regenerates them. This is the last technical gate before `v1.0.0`. The phase-4 doc's "next slice" note recommends committing the 5 golden PNGs directly (≈ 300 KB total) rather than vendoring a Porymap binary. **Blocker for this session:** Porymap binary not reachable. Unblock path: a human runs Porymap on the 5 designated maps with the documented export flags and commits the PNGs alongside a small fixture description for each.

2. **Tag `v1.0.0`** when phase-4 §2 exit criteria are all checked. Update `CHANGELOG.md` and the README's "first map in 5 minutes" path to show the L3 loop.

3. *Optional enhancement, deferred:* swap overlay event squares for 12x12 PNG icons + bundle a small bitmap font for elevation labels. Both need committed binary assets and a `pyproject.toml` wheel-include change.

**Useful current state for the next session (fidelity-corpus pointers):**

- The synthetic-fixture pattern in `examples/04_render_loop/run_demo.py::bootstrap_project` and `tests/unit/tools/test_rendering.py::_build_project` is the right starting shape for "Case 5: handcrafted edge case (max-size, border edge, multiple elevations)". Promote the shared bits to `tests/fixtures/projects/` once two callers want them.
- Cases 1-4 (Littleroot, Route 101, Granite Cave 1F, expansion-specific layered map) need real-art vanilla / expansion slices. Decide: vendor the minimal slice (data/tilesets + data/layouts + porymap.project.cfg for just that one map, ≈ 200-300 KB per case) under `tests/fixtures/projects/<case>/`, OR keep them out-of-tree and fetch in CI from a pinned commit of `pret/pokeemerald` / `rh-hideout/pokeemerald-expansion`. The phase-4 doc and ADR-0010 do not pre-commit either way.
- Each `tests/fixtures/renders/<case>/` directory holds `reference.png` (Porymap-exported) + `description.md` (project state + export flags). CI test: `_decode_png(our_render) == _decode_png(reference)` via `np.array_equal`.
- `--update-golden` flag: add a `conftest.py` `pytest_addoption("--update-golden")`; tests check the flag and overwrite `reference.png` with our render when set. Guards: only callable by a maintainer with Porymap on the path (refuse to overwrite if Porymap source-of-truth isn't available — defeats the point otherwise).

**Useful current state for the previous session's work:**

- `tools/rendering.py` exposes `render_map`, `render_map_region`, `render_metatile` as plain Python functions (testable without FastMCP). `DEFAULT_BORDER_FRAME_METATILES=7` is the Porymap-matching default. Helpers `_build_combined_{tile,palette,metatile}_bank` produce the per-render banks; they lazy-import numpy + render submodules so `import porymap_mcp.tools.rendering` works without the `render` extra.
- The metatile bank is composed twice (once per tileset half) and concatenated; primary is padded to slot 512 with zero metatiles so secondary lands at index 512 even when the primary tileset declares fewer metatiles.
- `render/layout.py::tile_border_around` is the border-framing primitive — modulo-tiled fancy-index over the output buffer, with the map pasted into the centre. Zero-frame returns an independent copy.
- `render/overlays.py::apply_overlays(rgba, overlays, *, map_bin, map_json, frame_offset_px)` is the overlay dispatcher; `SUPPORTED_OVERLAYS` is the canonical tuple of names. Each overlay calls `_blend_rectangle(rgba, x, y, w, h, colour, alpha)`. Region renders pass a negative `frame_offset_px` for the events overlay so out-of-region events clip silently.
- `tools/_common.py::maybe_attach_render(response, *, project_path, map_name, return_render)` is the mutation-tool wrap; late-imports FastMCP + `tools.rendering.render_map`. Default returns `response` unchanged so existing dict-shape callers and tests still pass.
- `tests/unit/tools/test_rendering.py` builds a complete synthetic project under `tmp_path` (primary + secondary tilesets each with 13 `.pal` files, a 3x2 `map.bin`, `metatiles.bin` + `metatile_attributes.bin`, `layouts.json` + `map_groups.json` + `map.json` + `porymap.project.cfg`). The fixture helpers (`_solid_metatile`, `_tile_word`, `_build_tileset`, `_build_project`) can be promoted to a shared `conftest.py` when the fidelity-corpus slice needs them.
- `parsers/attributes.py` decodes `metatile_attributes.bin` into a tuple of `MetatileAttributes` (`.layer_type: int`).
- `parsers/tileset.py` enumerates tileset directories and produces `TilesetEntry` with paths to `tiles.png`, `palettes/`, `metatiles.bin`, `metatile_attributes.bin`.
- `parsers/mapbin.py::MapBin` is the in-memory layout shape; `render/layout.py::mapbin_to_metatile_grid(mb)` adapts it to the numpy grid.
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
