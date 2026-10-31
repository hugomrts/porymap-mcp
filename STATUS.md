# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-14
**Last session:** **Fidelity corpus 5/5 pass — phase-4 §2 fully closed, project is `v1.0.0`-ready.** PR #12 on `claude/continue-project-ax6Mm` now carries slices 10, 10b, 11, and 11b. Validating against real Porymap exports of Littleroot Town, Route 101, Granite Cave 1F (vanilla maps from a pokeemerald-expansion checkout) and Battle Frontier Outside East (expansion triple-layer map) surfaced **four** latent bugs in the renderer: (1) `& 0xF8` GBA quantization on palette decode — wrong, Porymap propagates JASC bytes verbatim — removed; (2) border-tile phase anchored on the output's top-left, not the map's — fixed; (3) border frame default was symmetric 7x7 but Porymap uses asymmetric `7 horizontal x 5 vertical` — split constants; (4) `unused_tile_*` config keys are packed tile-entry words (palette + flips + tile_id), not bare tile_ids — added decoder. After all four fixes: **all 5 corpus cases pass pixel-identical** vs Porymap. Suite: 460 → **465 passing**, 0 skipped. ADR-0010 gains four "Empirical corrections". Per-slice writeups in [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md) §9.

---

## Current phase

**Phase 4 — L3: Vision** (effectively closed; tagging `v1.0.0` is the next housekeeping step).
Active doc: [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md)

L3 closes the project's quality loop (`paint → render → critique → fix → re-render`) by rendering maps to PNG server-side and returning them as MCP `image` content blocks. The full surface ships: 3 render tools, `return_render` on every L1 mutation, all 4 overlays, asymmetric border framing, and a 5-case fidelity corpus that matches Porymap's own export pixel-for-pixel. The renderer design lives in [ADR-0010](docs/decisions/0010-l3-renderer-design.md) (with a 4-bullet "Empirical corrections" addendum from the corpus validation).

PyPI publish (Phase 5) remains deferred per owner directive: `v1.0.0` ships as a GitHub tag first; the PyPI announcement waits for a deliberate communication push.

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
- `tests/` — **465 passing cases**, 0 skipped (308 L1 + 43 in `test_compose.py` + 39 in `test_layout.py` + 18 in `test_encode.py` + 13 in `test_overlays.py` + 39 in `test_rendering.py` + **5 in `tests/integration/test_fidelity.py`**). Synthetic PNG + JASC `.pal` + in-memory tile/palette/metatile/grid banks are built in-test where possible; the fidelity corpus is the only place that ships committed binary fixtures (5 small reference PNGs ≈ 700 KB total + vendored project slices for cases 1-4 ≈ a few MB).
- `examples/04_render_loop/` — `run_demo.py` (≈ 400 LOC bootstrapping a synthetic project + driving the iter-1/iter-2 loop via `porymap_mcp.tools.{maps,rendering}`), `README.md` (loop concept + prompt template + 12-axis scoring table + cross-refs), and two committed render artefacts `renders/iter{1,2}.png` showing the score jump from 7/36 to 21/36. `_demo_project/` is gitignored — regenerated each run.
- `tests/fixtures/renders/` — fidelity corpus (5 cases, all green): `case_01_littleroot_town`, `case_02_route_101`, `case_03_granite_cave_1f`, `case_04_expansion_layered` (Battle Frontier Outside East), `case_05_synthetic_edge`. Each carries `description.md`, `reference.png`, and a `project/` slice (cases 1-4 vendored from a pokeemerald-expansion checkout via `vendor_case.py`; case 5 generated by `build_project.py`). `HOW_TO_EXPORT.md` documents the maintainer's Porymap export procedure for adding/regenerating cases. The `--update-golden` pytest flag (in `tests/conftest.py`) overwrites case-5's `reference.png`; cases 1-4 are regenerated by re-exporting from Porymap + re-running `vendor_case.py`.

**Future enhancement** (deferred, optional): replace overlay event squares with 12x12 PNG icons under `src/porymap_mcp/render/assets/icons/` + font-based elevation labels — both require committing binary assets.

**Verified locally + in CI:** `python -m pytest --no-cov` → 465 passed, 0 skipped; `python -m pytest tests/integration/test_fidelity.py -v` → 5/5 pixel-identical vs Porymap; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 29 source files.

**Integration-tested:** `rh-hideout/pokeemerald-expansion` (L1 + L3 — fidelity corpus exercises 4 maps from a real expansion checkout, all matching Porymap export pixel-for-pixel).

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | ✅ Closed | `v0.1.0` tagged 2026-05-13. |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | ❌ Abandoned | See [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). `v0.2.0` skipped. |
| 4 — L3 (Vision) | Server renders maps to PNG | ✅ Effectively closed | Tag `v1.0.0` once PR #13 lands. Optional: formalize the perf budget via `tests/integration/test_perf.py` (informally well within budget on every corpus case). |
| 5 — Release | Publish to PyPI + community announcement | Deferred | `v1.0.0` ships as a GitHub tag first per the long-standing owner directive. PyPI publish remains deferred until there's a deliberate communication push. |

---

## Open decisions (blocking next work)

- [x] **Poryscript vs raw `.inc`** — resolved by ADR-0007: poryscript default, `.inc` fallback when `use_poryscript=0`.
- [x] **Prefab auto-import** — resolved by ADR-0008: reject on tileset mismatch, no auto-import.
- [x] **Typed event dataclasses** — deferred to v0.2.0 per ADR-0007 §"Decision"; raw-dict events suffice for L1.
- [x] **L2 (Live Porymap) feasibility** — resolved by ADR-0009: abandoned. Pivot to L3.
- [x] **Renderer design** — resolved by ADR-0010 + 4 empirical corrections (2026-05-14, in ADR-0010 §"Empirical corrections"): numpy + Pillow, artist-source files (`tiles.png` + JASC `.pal`), **NO GBA quantization** (Porymap propagates JASC values verbatim — original ADR was wrong), 3-layer composition with `unused_tile_*` fill (decoded as packed tile-entry words, NOT bare tile_ids), asymmetric border frame `7 horizontal x 5 vertical`, border-tile phase anchored on the map's top-left, pixel-identical fidelity (verified on 5 cases), FastMCP `ToolResult` + `Image` return shape, no connection rendering in v1.0.

Resolved decisions live under [`docs/decisions/`](docs/decisions/). No open decisions block the next session.

---

## Next session pickup (post-L3, `v1.0.0` ready to tag)

**Branch / PR state.** PR #12 (slice 10 + 10b: example loop + README/CHANGELOG refresh) is **merged into `main`** at commit `c3437e9`. PR #13 (slice 11 + 11b: fidelity corpus + 4 renderer bug fixes) is **open** on `claude/continue-project-ax6Mm`, head `32257f6`, 11 commits, no conflicts. **Before starting work**: verify PR #13 is merged, then `git checkout main && git pull` for a clean tree. If PR #13 is still open, the next session's job is *just to land it* (review CI, fix any drift) — do not start the v1.0.0 release slice on a stale base.

**Done in this session** (don't redo):

- ✅ Slice 10 (`d560b33`, in PR #12 merged): `examples/04_render_loop/` — runnable demo + walkthrough README + two committed render PNGs (iter 1/2, score 7→21/36).
- ✅ Slice 10b (`d156881`, in PR #12 merged): `README.md` + `CHANGELOG.md` refreshed for the L3 surface.
- 📒 Handoff commit `c3437e9` (in PR #12 merged): STATUS + phase-4 doc folded slice 10b into the session log.
- ✅ Slice 11 (commits `bfd9a72` … `a872ead`, in PR #13 open):
  - `tests/fixtures/renders/HOW_TO_EXPORT.md` (incl. `pip install -e .` + PowerShell shell-syntax notes), `vendor_case.py` (copies a minimum project slice for one map from a source pokeemerald checkout, reusing the L1 parsers), and 5 case directories (`case_NN/description.md`).
  - `case_05_synthetic_edge/build_project.py` — deterministic builder for the regression-only synthetic project (30x20 with custom 4x4 border, all `unused_tile_*` slots exercised, primary tileset with < 512 metatile slots to force the bank-padding code path).
  - `tests/integration/test_fidelity.py` — single parametrized test iterating all 5 cases, auto-skipping when project/ or reference.png is missing. Failure messages quote first-mismatch coordinate + percent of diffing pixels.
  - `conftest.py` — maintainer-only `--update-golden` pytest CLI flag.
  - **3 renderer bug fixes** uncovered while validating cases 1-3 against real Porymap exports of Littleroot Town, Route 101, Granite Cave 1F (all from a pokeemerald-expansion checkout):
    1. **No GBA `& 0xF8` quantization.** Porymap propagates JASC bytes verbatim; our masking was wrong. Removed every quantization site in `render/compose.py`.
    2. **Border-tile phase anchored on the map's top-left, not the output's.** `border[0][0]` lands at output pixel `(fw_px, fh_px)`; tiles outside the map cycle backwards via modulo. One-line fix in `render/layout.py::tile_border_around`.
    3. **Asymmetric border frame.** Porymap uses **7 metatiles horizontal × 5 vertical** (matching half the GBA visible 240x160 screen), not symmetric 7x7. Constants split into `DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL=7` / `DEFAULT_BORDER_FRAME_METATILES_VERTICAL=5`. `structured_content["border_frame_metatiles"]` is now a `{"horizontal": int, "vertical": int}` dict.
- ✅ Slice 11b (commits `20fe606` … `32257f6`, in PR #13 open):
  - Vendored case 04 (Battle Frontier Outside East from pokeemerald-expansion).
  - **4th renderer bug fix**: `unused_tile_*` config keys are packed tile-entry words (palette + flips + tile_id), not bare tile_ids. The expansion's `unused_tile_normal=0x3014` decodes as `(tile_id=20, palette=3)`; our code was passing `0x3014=12308` straight as a tile_id, way over the 1024-tile cap, silently exposing `transparency_color=0x000000`. Added `_decode_unused` helper in `render/compose.py`, three call sites.
  - ADR-0010 gains a 4-bullet "Empirical corrections (2026-05-14, after corpus validation)" section. Phase-4 §2 fidelity exit-criterion ticked at 5/5.

**End-state.**
- `server.build_server()` registers 24 tools (21 L1 + 3 render).
- Fidelity corpus: **5/5 cases pass pixel-identical** vs Porymap reference exports (cases 1-2: 0/261120 diff; case 3: 0/161280; case 4: 0/1805312; case 5: 0/385088 vs our own previous render).
- Suite: **465 passing**, 0 skipped (308 L1 + 43 `test_compose.py` + 39 `test_layout.py` + 18 `test_encode.py` + 13 `test_overlays.py` + 39 `test_rendering.py` + 5 `test_fidelity.py`).
- `ruff check .` + `ruff format --check .` + `mypy --strict src/porymap_mcp` (29 source files) all clean.

**Up next, in order:**

1. **Tag `v1.0.0`** (after PR #13 merges). `CHANGELOG.md` already has the `[Unreleased] — v1.0.0 candidate` section; bump heading to `[1.0.0] — <date>`, append a one-line note at the top of the section pointing at the four bug fixes (with their commit shas), then `git tag v1.0.0 && git push --tags`. PyPI publish is still deferred per the long-standing owner directive — `v1.0.0` ships as a GitHub tag first.

2. **Perf benchmarks** (the only exit-criterion item still formally unmeasured). Add `tests/integration/test_perf.py` that times `render_map` on case 1 (small town), case 5 (30x20 synthetic), and a synthetic 60x120, asserting each falls inside the targets in `.claude/agents/map-renderer.md` §"Performance targets". Not blocking `v1.0.0` — informal measurements during fidelity work showed every case well under budget (case 04 = 1376x1312 px renders in ~250 ms cold) — but useful as a CI guard. Use the in-repo synthetic project from `case_05_synthetic_edge/build_project.py` for the 60x120 case (extend `MAP_WIDTH/HEIGHT` constants).

3. *Optional enhancement, deferred:* swap overlay event squares for 12×12 PNG icons + bundle a small bitmap font for elevation labels. Both need committed binary assets and a `pyproject.toml` wheel-include change.

**Useful current state for the next session:**

- **Fidelity corpus shape.** `tests/fixtures/renders/case_NN_*/` — each contains `description.md`, `reference.png` (Porymap-exported, except case 5 which is our own render), `VENDOR.md` (auto-generated by `vendor_case.py`, records the source checkout + source map for provenance), and `project/` (vendored slice).  Case 5 has `build_project.py` + a generated `project/` instead. Run `python -m pytest tests/integration/test_fidelity.py -v` to validate; pass `--update-golden` to overwrite goldens (only meaningful for case 5).
- **Adding a new corpus case.** Add a `case_NN_<slug>/` directory + `description.md`, append a `Case(...)` row in `tests/integration/test_fidelity.py::CASES`, then either run `vendor_case.py` (if it's vendored from a real project) or write a `build_project.py` (if synthetic). Test runner auto-discovers.
- **`render/compose.py` post-fix invariants.** `decode_palette_bank` propagates JASC RGB verbatim — NO `& 0xF8` masking. `decode_metatile_bank`'s `transparency_color` fill is also unquantized. `unused_tile_normal` / `unused_tile_covered` / `unused_tile_split` from `ProjectConfig` are full packed tile-entry words; `_decode_unused` decomposes them into `(tile_id, xflip, yflip, palette)`. Don't reintroduce raw-id treatment without re-checking the corpus.
- **`render/layout.py::tile_border_around`** anchors the modulo phase on the map's top-left (output pixel `(fw_px, fh_px)`), so tiles outside the map cycle BACKWARDS through `border_rgba` — `ys = (np.arange(total_h) - fh_px) % bh`. Same for `xs`. Don't anchor on `(0, 0)` — that breaks every multi-metatile border.
- **`tools/rendering.py`** uses `DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL = 7` and `DEFAULT_BORDER_FRAME_METATILES_VERTICAL = 5`. Rendering with `include_border=True` widens the area-metatiles count by `2 * H` horizontally and `2 * V` vertically, separately, so the palette-vs-RGBA mode threshold in `encode_png` still applies correctly.
- **`tools/rendering.py` exposes `render_map`, `render_map_region`, `render_metatile`** as plain Python functions (testable without FastMCP). Helpers `_build_combined_{tile,palette,metatile}_bank` produce per-render banks; they lazy-import numpy + render submodules so `import porymap_mcp.tools.rendering` works without the `render` extra.
- **The metatile bank** is composed twice (once per tileset half) and concatenated; primary is padded to slot 512 with zero metatiles so secondary lands at index 512 even when the primary tileset declares fewer metatiles. Confirmed by case 04 (BattleFrontierOutsideEast secondary tileset has 510 metatiles → slots 512..1021).
- **`render/overlays.py::apply_overlays(rgba, overlays, *, map_bin, map_json, frame_offset_px)`** is the overlay dispatcher; `SUPPORTED_OVERLAYS` is the canonical tuple of names. `frame_offset_px` is now `(fv_px, fh_px) = (5*16, 7*16)` when `include_border=True`; for region renders it stays asymmetric.
- **`tools/_common.py::maybe_attach_render(response, *, project_path, map_name, return_render)`** is the mutation-tool wrap; late-imports FastMCP + `tools.rendering.render_map`. Default returns `response` unchanged so existing dict-shape callers and tests still pass.
- **`tests/unit/tools/test_rendering.py`** builds a complete synthetic project under `tmp_path` (primary + secondary tilesets each with 13 `.pal` files, a 3x2 `map.bin`, `metatiles.bin` + `metatile_attributes.bin`, `layouts.json` + `map_groups.json` + `map.json` + `porymap.project.cfg`). Fixture helpers (`_solid_metatile`, `_tile_word`, `_build_tileset`, `_build_project`) — promote to a shared `conftest.py` if a third caller ever wants them.
- **Stale code paths to NOT reintroduce:**
  - `& 0xF8` quantization on palette decode.
  - Symmetric border `DEFAULT_BORDER_FRAME_METATILES = 7` constant — replaced by HORIZONTAL/VERTICAL pair.
  - `border[0][0]` at output `(0, 0)` in `tile_border_around`.
  - Treating `unused_tile_*` as a bare `tile_id`.

**Stable infrastructure pointers (still accurate post-corpus):**

- `tools/_common.py::maybe_attach_render(response, *, project_path, map_name, return_render)` is the mutation-tool wrap; late-imports FastMCP + `tools.rendering.render_map`. Default returns `response` unchanged so existing dict-shape callers and tests still pass.
- `parsers/attributes.py` decodes `metatile_attributes.bin` into a tuple of `MetatileAttributes` (`.layer_type: int`). The `metatile_layer_type_mask` is config-driven (vanilla `0x6000`, expansion `0xF000`).
- `parsers/tileset.py` enumerates tileset directories and produces `TilesetEntry` with paths to `tiles.png`, `palettes/`, `metatiles.bin`, `metatile_attributes.bin`.
- `parsers/mapbin.py::MapBin` is the in-memory layout shape; `render/layout.py::mapbin_to_metatile_grid(mb)` adapts it to the numpy grid.
- `ProjectConfig` reads `enable_triple_layer_metatiles`, `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`. `tools/rendering.py` passes `layers=3 if enabled else 2` into `decode_metatile_bank`.
- Mypy in CI runs in an isolated `uv tool` env that does not see numpy/PIL; the override in `pyproject.toml` keeps `mypy --strict` clean. Don't remove it without adding stub packages.

## Outstanding chores (not blocking `v1.0.0`)

- **PyPI publish** (Phase 5). Deferred per owner directive — `v1.0.0` ships as a GitHub tag first; PyPI announcement waits for a deliberate communication push.
- **Perf benchmarks**. Add a `tests/integration/test_perf.py` that asserts `render_map` hits the targets in `.claude/agents/map-renderer.md` §"Performance targets" on case 1, case 5, and a synthetic 60x120. Informally well within budget on every corpus case; formal CI guard would catch a future regression.
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
