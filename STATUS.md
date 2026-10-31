# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-10-31
**Last session:** **v1.0.0 release slice — phase 4 closed, phase 5 opened.** Four PRs, squash-merged one by one: #14 makes `ruff check`, `ruff format --check` and `mypy` blocking in CI (they had been failing silently behind `continue-on-error`); #15 rewrites the README as a shipped product (renders up top, pip/uvx, MCP registration, 24-tool table, ADR index) and replaces the bogus `gTileset_LittlerootTown` with `gTileset_Petalburg`; #16 is `chore: release v1.0.0` (CHANGELOG `[1.0.0] — 2026-10-31` with the four renderer fixes, version 1.0.0, Production/Stable); #17 adds `.github/workflows/publish.yml` (PyPI trusted publishing on `v*` tags) and absolute README URLs for PyPI. The tag, GitHub Release and PyPI publisher configuration are owner actions. Details in [`docs/phases/phase-5-release.md`](docs/phases/phase-5-release.md) §8.

---

## Current phase

**Phase 5 — Release & community launch** (in progress).
Active doc: [`docs/phases/phase-5-release.md`](docs/phases/phase-5-release.md)

`main` carries the `1.0.0` release commit. What remains before `v1.0.0` is public is all on the owner's side:

1. On pypi.org, add a pending trusted publisher: project `porymap-mcp`, owner `hugomrts`, repo `porymap-mcp`, workflow `publish.yml`, environment `pypi`.
2. Tag `v1.0.0` on `main` and push it → `publish.yml` builds, checks the tag against `pyproject.toml`, and uploads to PyPI.
3. `gh release create v1.0.0` with the CHANGELOG `[1.0.0]` section as notes.
4. Smoke test: `uvx --from "porymap-mcp[render]" porymap-mcp` on a clean machine.

Phase 4 (L3 — Vision) is closed; its only unticked functional item, the formal perf benchmark, is a non-blocking follow-up.

---

## What exists in the repo today

- `MCP_PORYMAP.md` — strategic vision (FR). `CLAUDE.md` — operating manual. `STATUS.md` — this file.
- `.claude/agents/` — 7 sub-agents. `.claude/settings.json`, `.gitignore`.
- `docs/phases/` — phases 1, 2, 4 closed; phase 3 abandoned (ADR-0009); phase 5 in progress.
- `docs/decisions/` — ADRs 0001–0010.
- `pyproject.toml` (version `1.0.0`, `render` extra = Pillow + numpy, `dev` extra pins `ruff>=0.17,<0.18` and `mypy>=2.4,<3`), `uv.lock`, `LICENSE`, `README.md` (v1.0.0, absolute URLs), `CHANGELOG.md` (`[1.0.0] — 2026-10-31`), `.pre-commit-config.yaml` (ruff v0.17.3, mypy v2.4.1).
- `.github/workflows/ci.yml` — Linux + macOS × Python 3.11–3.13; `ruff check`, `ruff format --check`, `mypy`, `pytest`, all blocking. Ruff ignores `*.md`.
- `.github/workflows/publish.yml` — on `v*` tags: tag/version check, `python -m build`, `twine check --strict`, upload via `pypa/gh-action-pypi-publish` with OIDC from the `pypi` environment.
- `src/porymap_mcp/` — 24 MCP tools (21 L1 + 3 render), parsers, `Project`, prefabs, `render/` (compose, layout, overlays, encode).
- `tests/` — **465 passing**, 0 skipped, including the 5-case fidelity corpus (`tests/integration/test_fidelity.py`, pixel-identical vs Porymap).
- `examples/04_render_loop/` — runnable paint → render → critique demo + committed `renders/iter{1,2}.png`.

**Verified locally (2026-10-31):** `ruff check .`, `ruff format --check .`, `mypy` (58 files) clean; `pytest` 465 passed; `uv build` + `twine check --strict` pass on the 1.0.0 wheel and sdist; `actionlint` clean on both workflows.

**Integration-tested:** `rh-hideout/pokeemerald-expansion` (L1 + L3).

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | ✅ Closed | `v0.1.0` tagged 2026-05-13. |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | ❌ Abandoned | See [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). |
| 4 — L3 (Vision) | Server renders maps to PNG | ✅ Closed 2026-10-31 | Optional: `tests/integration/test_perf.py`. |
| 5 — Release | Publish to PyPI + community announcement | 🛠 In progress | Owner: PyPI trusted publisher, tag `v1.0.0`, GitHub Release. Then README `docs-curator` pass, CONTRIBUTING, templates, announcements. |

---

## Open decisions (blocking next work)

- [x] **Poryscript vs raw `.inc`** — resolved by ADR-0007: poryscript default, `.inc` fallback when `use_poryscript=0`.
- [x] **Prefab auto-import** — resolved by ADR-0008: reject on tileset mismatch, no auto-import.
- [x] **Typed event dataclasses** — deferred to v0.2.0 per ADR-0007 §"Decision"; raw-dict events suffice for L1.
- [x] **L2 (Live Porymap) feasibility** — resolved by ADR-0009: abandoned. Pivot to L3.
- [x] **Renderer design** — resolved by ADR-0010 + 4 empirical corrections (2026-05-14, in ADR-0010 §"Empirical corrections"): numpy + Pillow, artist-source files (`tiles.png` + JASC `.pal`), **NO GBA quantization** (Porymap propagates JASC values verbatim — original ADR was wrong), 3-layer composition with `unused_tile_*` fill (decoded as packed tile-entry words, NOT bare tile_ids), asymmetric border frame `7 horizontal x 5 vertical`, border-tile phase anchored on the map's top-left, pixel-identical fidelity (verified on 5 cases), FastMCP `ToolResult` + `Image` return shape, no connection rendering in v1.0.

Resolved decisions live under [`docs/decisions/`](docs/decisions/). No open decisions block the next session.

---

## Next session pickup

**Before starting:** `git checkout main && git pull`. Check whether `v1.0.0` is tagged (`git ls-remote --tags origin`) and whether the `Publish to PyPI` run succeeded. If the publish failed, fix that first.

**Done this session** (don't redo): PRs #14–#17 described in "Last session" above.

**Up next, in order:**

1. **If the owner has tagged:** verify https://pypi.org/project/porymap-mcp/ renders (images, links, badges) and that `uvx --from "porymap-mcp[render]" porymap-mcp` starts.
2. **README pass with `docs-curator`** against its rubric (phase 5 §3 "Docs").
3. **Community readiness** (phase 5 §3): `CONTRIBUTING.md`, issue templates, PR template, code of conduct, security policy.
4. **Examples 01–03 and 05** — only `04_render_loop` exists.
5. *Non-blocking:* perf benchmark `tests/integration/test_perf.py` (see phase 4 §2).

**Owner preferences recorded this session:** one PR per step, conventional-commit titles, squash merge by the owner; commits authored as Hugo Martins, no AI attribution in commits or PRs; `main` is protected (PR + CI required); never edit `MCP_PORYMAP.md`.

## Technical pointers (renderer + corpus)

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

**Stable infrastructure pointers:**

- `tools/_common.py::maybe_attach_render(response, *, project_path, map_name, return_render)` is the mutation-tool wrap; late-imports FastMCP + `tools.rendering.render_map`. Default returns `response` unchanged so existing dict-shape callers and tests still pass.
- `parsers/attributes.py` decodes `metatile_attributes.bin` into a tuple of `MetatileAttributes` (`.layer_type: int`). The `metatile_layer_type_mask` is config-driven (vanilla `0x6000`, expansion `0xF000`).
- `parsers/tileset.py` enumerates tileset directories and produces `TilesetEntry` with paths to `tiles.png`, `palettes/`, `metatiles.bin`, `metatile_attributes.bin`.
- `parsers/mapbin.py::MapBin` is the in-memory layout shape; `render/layout.py::mapbin_to_metatile_grid(mb)` adapts it to the numpy grid.
- `ProjectConfig` reads `enable_triple_layer_metatiles`, `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`. `tools/rendering.py` passes `layers=3 if enabled else 2` into `decode_metatile_bank`.
- CI installs `.[dev]` (which includes Pillow + numpy) before running `mypy`; the `numpy.*` / `PIL.*` `ignore_missing_imports` override in `pyproject.toml` keeps `mypy --strict` clean in environments without the `render` extra (e.g. the pre-commit hook). Don't remove it without adding stub packages.

## Outstanding chores (not blocking `v1.0.0`)

- **Perf benchmarks** — `tests/integration/test_perf.py` asserting the targets in `.claude/agents/map-renderer.md` §"Performance targets" on case 1, case 5 and a synthetic 60x120.
- **Overlay icons** — 12×12 PNG event icons + bitmap font for elevation labels (needs committed binary assets + wheel-include change).
- ~~`gTileset_LittlerootTown` in README~~ — resolved in PR #15. The earlier note here was wrong: vanilla `pokeemerald` has no `gTileset_LittlerootTown` either; Littleroot uses `gTileset_Petalburg` in both.

---

## Quick links

- Vision: [`MCP_PORYMAP.md`](MCP_PORYMAP.md)
- Operating manual: [`CLAUDE.md`](CLAUDE.md)
- Current phase: [`docs/phases/phase-5-release.md`](docs/phases/phase-5-release.md)
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
