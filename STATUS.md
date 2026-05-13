# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** **Phase 3 (L2 — Live Porymap) abandoned. Phase 4 (L3 — Vision) is now active.** Two static-source audits of Porymap master established that the original L2 exit criteria ("Porymap reloads within ~500 ms of an L1 mutation, no human action, no spurious modal prompts") are not achievable: Porymap's `QFileSystemWatcher` deliberately excludes the files we mutate (`map.bin`, `border.bin`, `map.json`), its JS engine is a bare `QJSEngine` with zero file-read primitives (no `readFile`, no sockets, no `XMLHttpRequest`, `overlay.addImage` returns `void`), and there is no `map.reload()` Q_INVOKABLE. The only feasible "workaround" — touch `layouts.json` after every mutation to fire Porymap's modal reload prompt — has negative ROI given L3 makes Porymap's live presence strategically redundant (the agent will see its own renders inline). [ADR-0009](docs/decisions/0009-abandon-l2-live-porymap.md) records the decision and the four rejected alternatives. Phase 3 doc is marked Abandoned with the full investigation in its session log. Phase 4 doc promoted to Active. Versioning: `v0.2.0` is intentionally skipped; next ship is `v1.0.0` once L3 lands. **300 passing tests** still green at HEAD; no code changes this session.

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
- [ ] **Renderer design (ADR-0010).** Open. Must lock: image library (Pillow vs numpy-backed alt), tile/metatile cache strategy, palette source of truth (.pal vs C tileset structs vs both), how to read the existing PNG tilesets in `data/tilesets/*/tiles.png`, and the MCP `image` content-block emission format. Resolve **before** writing any code under `src/porymap_mcp/render/`.

Resolved decisions live under [`docs/decisions/`](docs/decisions/).

---

## Next session pickup (for L3 — Vision)

1. **Read `docs/phases/phase-4-l3-vision.md`** end-to-end. Exit criteria pin down what "done" means; §3 sketches the renderer module layout (`src/porymap_mcp/render/`).
2. **Investigation first** (delegate, don't code yet):
   - `porymap-format-expert` — exact decode pipeline from `data/tilesets/<tileset>/tiles.png` + `palettes/*.pal` + `metatiles.bin` + `metatile_attributes.bin` to a 16×16 RGBA image. Confirm palette indexing, transparency (palette index 0), bottom/top layer composition, attribute-driven flips, animated-tile quirks (Phase 4 OQ2 — render first frame, defer animation).
   - `map-renderer` — Pillow-based pipeline design vs alternatives (raw numpy + PIL only at encode), in-call cache keying, performance targets from `.claude/agents/map-renderer.md` ("30×20 < 100 ms").
   - Use a real `rh-hideout/pokeemerald-expansion` tileset as the reference, plus a vanilla pokeemerald town for the byte-identical golden test.
3. **Lock the design in ADR-0010** before any code lands. Cover: image library, palette source, layer composition order, cache scope, MCP `image` block emission, the `return_render: bool = False` parameter conventions for L1 tools.
4. **Then implement** in this order (per phase-4 §3): `tile.py` (decode tile + palette) → `metatile.py` (compose 16×16) → `layout.py` (assemble W×H, regions, border) → `overlays.py` → `encode.py` → wire `render_map`, `render_map_region`, `render_metatile` as new tools, then add `return_render` to L1 mutations.
5. **Visual fidelity gate**: every render must pixel-match Porymap's own PNG export for the 5 reference maps listed in phase-4 §7. Golden files under `tests/fixtures/renders/`.

Useful project state for the next session:
- Pillow is already declared as an optional extra in `pyproject.toml` — promote to a required dep when render lands (or keep optional and gate `render_*` tools behind it; decide in ADR-0010).
- The `tileset` parser already reads metatile + attribute data; the *graphics* side (tiles.png + .pal) is not yet wired. Adding that is part of L3.
- Integration host stays WSL2 + Windows. Path handling already works for L1; render output is bytes, so cross-platform concerns are limited to encoding.

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
