# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** **Phase 3 (L2) abandoned, Phase 4 (L3 — Vision) opened and design locked.** First half of the session: static-source audit of Porymap master established that autonomous live-reload is not achievable (no JS file-read primitives, native `QFileSystemWatcher` excludes `map.bin`/`map.json`, no `map.reload()` Q_INVOKABLE); abandoned in [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md). Versioning: `v0.2.0` is intentionally skipped; next ship is `v1.0.0`. Second half: two parallel audits of the L3 decode pipeline and the Python rendering stack produced [ADR-0010](docs/decisions/0010-l3-renderer-design.md), which locks: **numpy + Pillow** (both under the `render` extra); read `tiles.png` + JASC `.pal` as the artist-source files (skip compiled `.4bpp` / `.gbapal`); apply **GBA 5-bit palette quantization** (`& 0xF8`) on every palette decode; always compose 3 metatile layers, filling the missing one in dual-layer mode from `unused_tile_{normal,covered,split}` config keys (read from `porymap.project.cfg`); fidelity criterion is **pixel-identical decoded RGBA**, not byte-identical PNG (Pillow and Qt cannot match deflate output); MCP return shape is `ToolResult(content=[Image(...)], structured_content={...})`. Connection rendering deferred to v1.1. Module structure simplified: `tile.py` + `metatile.py` merged into `compose.py`. **No code yet** — implementation begins next session. **300 passing tests** still green at HEAD.

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
- `docs/phases/` — phase 1 closed, phases 2–5 active or pending.
- `docs/decisions/` — ADRs 0001–0008.
- `pyproject.toml`, `LICENSE`, `README.md` (with "first map in 5 minutes"), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- `src/porymap_mcp/` — eight parsers (`mapbin`, `projectconfig`, `layoutsjson`, `mapgroups`, `mapjson`, `tileset`, `metatiles`, `attributes`), the `Project` class with `iter_maps` / `get_map_entry` / `get_map_json` / `find_bare_by_map_id` / `write_border_bin`, four tool modules (`discovery`, `maps`, `projects`, `events`) implementing all 21 L1 tools, and the `prefabs` package (library + `Prefab`/`PrefabTile` types).
- `tests/` — 298 passing cases across the parsers, project, four tool modules, and the prefab library.
- `tests/fixtures/README.md` — hand-crafted fixture documentation.

**Not yet (post-L1, deferred to L2/L3 or v0.2.0):** typed event dataclasses, on-disk extensible prefab JSON library, L3 metatile graphic decoding for PNG rendering, L2 file-watcher → Porymap-reload signaling.

**Verified locally + in CI:** `pytest` → 300 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 23 source files. CI matrix green on Python 3.11/3.12/3.13 × Ubuntu/macOS at every merged PR.

**Integration-tested:** `rh-hideout/pokeemerald-expansion` (WSL2 path opened in Porymap on Windows). Agent created `MAP_LAKESIDE_TOWN`, painted a rectangle, added a sign with poryscript stub, Porymap loaded it cleanly. See README "First map in 5 minutes" and `docs/phases/phase-2-l1-filesystem.md` session log.

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

## Next session pickup (L3 implementation — design is locked)

1. **Re-read [`docs/phases/phase-4-l3-vision.md`](docs/phases/phase-4-l3-vision.md) §3, §7, and the 2026-05-13 session log entry** + **[ADR-0010](docs/decisions/0010-l3-renderer-design.md)**. Together they specify the renderer end-to-end.
2. **Add the `render` extra to `pyproject.toml`** with `Pillow>=10.0` and `numpy>=1.26`. Pillow was already listed as optional — add numpy alongside.
3. **Extend `ProjectConfig` parser** (`src/porymap_mcp/parsers/projectconfig.py`) to read the new keys: `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`, `enable_triple_layer_metatiles`, plus the attribute mask overrides (`metatile_layer_type_mask`, etc.). These are needed before any render code can run correctly. Unit tests against a fixture `porymap.project.cfg`.
4. **Implement renderer in dependency order** (per phase-4 §3 module layout):
   - `compose.py` — decode `tiles.png` (mask `& 0x0F`), decode `palettes/*.pal` (apply GBA `& 0xF8` quantization, set palette-index-0 alpha 0), build `MetatileBank` with the 3-layer rule (table in ADR-0010). Unit tests with a hand-crafted 4-metatile tileset.
   - `layout.py` — `assemble_layout(MetatileBank, metatile_grid)` via numpy fancy indexing; border rendering by reusing the same code on `border.bin` data.
   - `encode.py` — palette-vs-RGBA selection (palette mode when area ≤ 4096 and no overlays); FastMCP `ToolResult(content=[Image(...).to_image_content()], structured_content={...})` packaging.
   - Wire as MCP tools: `render_map`, `render_map_region`, `render_metatile` (in `tools/rendering.py`, new module). `is_porymap_connected` is gone — L2 abandoned.
   - `overlays.py` — `collision`, `elevation`, `grid`, `events`. Bundle the 5 icons under `src/porymap_mcp/render/assets/icons/`.
   - Add `return_render: bool = False` to every L1 mutation tool's signature. When `True`, the tool's response carries the same `Image` content block.
5. **Fidelity corpus**. Assemble the 5-map test corpus under `tests/fixtures/renders/`. Each map has: (a) the project state (probably synthetic, possibly a tiny vendored vanilla-pokeemerald slice), (b) the Porymap reference PNG produced with **scale 1×, show connections = off, no overlays, include border per case**. CI compares `np.array_equal(decoded(ours), decoded(reference))`.
6. **End-to-end loop** (`examples/04_render_loop/`). Last deliverable. The agent paints a town, renders, runs `map-design-critic`, applies fixes, re-renders. Score must improve measurably.
7. **Tag `v1.0.0`** when phase-4 §2 exit criteria are all checked.

Useful project state:
- Pillow is already declared as an optional extra. Numpy must be added to the same extra.
- The `tileset` parser already exposes metatiles and attributes (incl. `LayerType` enum). L3 only needs to add the *graphics* side (`tiles.png` + `.pal`) and consume the existing attribute output.
- `porymap.project.cfg` parser is **NOT YET** reading the new render-relevant keys — adding them is step #3 above.
- Integration host stays WSL2 + Windows. Renderer output is bytes; cross-platform concerns are limited to encoding (PNG mode selection) and font/icon assets (bundled, deterministic).

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
