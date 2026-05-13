# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** **`v0.1.0` shipped.** Phase 2 (L1 Filesystem) is closed. End-to-end integration test passed against `rh-hideout/pokeemerald-expansion` opened in Porymap on Windows (WSL2 + Claude Code CLI setup). Two interop bugs surfaced during the test and fixed in PR #7: (1) `mapjson._read_connections` is now permissive on non-list values (matches Porymap; needed for the 60+ FRLG map.json files in pokeemerald-expansion that have `"connections": 0`); (2) `Project.find_bare_by_map_id` swallows `PorymapMCPError` from malformed siblings so a single corrupt map.json doesn't block `create_map` elsewhere. Shipped `CHANGELOG.md`. **Tag `v0.1.0` published** to https://github.com/hugomrts/porymap-mcp/releases/tag/v0.1.0. **300 passing tests**, ruff/format/mypy --strict clean, CI matrix green across Python 3.11–3.13 × Ubuntu/macOS on every merged PR (#5, #6, #7).

---

## Current phase

**Phase 3 — L2: Live Porymap** (not started).
Active doc: [`docs/phases/phase-3-l2-live-porymap.md`](docs/phases/phase-3-l2-live-porymap.md)

Phase 2 is closed (v0.1.0 tagged 2026-05-13). The next big piece of work is L2: detect when files change on disk and signal Porymap to reload, so the agent's edits appear live in the editor without the user re-opening the project. Start the next session by reading the phase-3 doc, then deciding the inotify/Watchdog/native-API approach.

Phase 5 (PyPI publish) is technically unblocked too — v0.1.0 is a tag, not yet a release. Either order works; L2 is more impactful to users than the PyPI publish itself.

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
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | **Next** | Read [phase-3 doc](docs/phases/phase-3-l2-live-porymap.md); pick a file-watcher strategy (watchdog vs inotify vs polling); decide if Porymap exposes any IPC. |
| 4 — L3 (Vision) | Server renders maps to PNG | Not started | Wait for L2; uses `Pillow` (already an optional extra in `pyproject.toml`). |
| 5 — Release | Publish to PyPI + community announcement | Tag exists, publish pending | Build wheel/sdist with `uv build`, `uv publish` with the project owner's PyPI token. No new code needed. |

---

## Open decisions (blocking next work)

- [x] **Poryscript vs raw `.inc`** — resolved by ADR-0007: poryscript default, `.inc` fallback when `use_poryscript=0`.
- [x] **Prefab auto-import** — resolved by ADR-0008: reject on tileset mismatch, no auto-import.
- [x] **Typed event dataclasses** — deferred to v0.2.0 per ADR-0007 §"Decision"; raw-dict events suffice for L1.

Resolved decisions live under [`docs/decisions/`](docs/decisions/). No open decisions block the next session.

---

## Next session pickup (for L2 — Live Porymap)

1. **Read `docs/phases/phase-3-l2-live-porymap.md`** end-to-end. The exit criteria pin down what "done" means.
2. **The first decision is the file-watcher strategy.** Three options to evaluate (consult `mcp-tool-designer` + `rom-hack-domain` for the trade-offs):
   - **`watchdog`** (cross-platform Python lib, well-maintained, easy install). Probably the default.
   - **Raw `inotify` (Linux) / `kqueue` (macOS) / `ReadDirectoryChangesW` (Windows)** — more code, no extra dependency.
   - **Polling** — last resort if file events are too unreliable across WSL2 mount points (note: the project owner's setup is WSL2 paths read from Windows Porymap; watchdog handles this but inotify will NOT see Windows-side reloads — relevant for L2's "is Porymap connected" question).
3. **The second decision is whether Porymap exposes IPC** that lets us push a "reload this map" signal directly, vs relying on Porymap's own filesystem watcher. Look at Porymap's source (`huderlem/porymap`); the existing CLI is `porymap --help`. If no IPC, the bridge becomes one-way (we touch the file, Porymap's own watcher picks up).
4. **Write ADR-0009** capturing the chosen strategy before coding.
5. **Implementation order suggested by the phase doc:** detect Porymap presence → file watcher → debounce → integration test against a headless Porymap → tag `v0.2.0`.

Useful project state for the next session:
- `Project` already has all atomic writes going through `_atomic.write_atomic`, so any file change can be hooked without changing tool code. The bridge sits *between* `Project.save_*` and the filesystem.
- The integration test ran on **WSL2 + Windows Porymap** — that's our worst-case for file-watcher reliability. Whatever L2 strategy is picked, it has to work for this setup.

## Outstanding chores (not blocking L2)

- **PyPI publish** (Phase 5). The tag `v0.1.0` exists; `uv build` + `uv publish` is all that's left. ~10 minutes when the project owner is ready with a PyPI token.
- **`gTileset_LittlerootTown` example in README.** The README's "first map" example uses `gTileset_LittlerootTown` as a placeholder, which does NOT exist in `rh-hideout/pokeemerald-expansion` (real label: `gTileset_Petalburg`). Vanilla pokeemerald *does* have `gTileset_LittlerootTown` though. Decision: leave the README as-is (vanilla is the documented baseline), or note both? Pure docs change.

---

## Quick links

- Vision: [`MCP_PORYMAP.md`](MCP_PORYMAP.md)
- Operating manual: [`CLAUDE.md`](CLAUDE.md)
- Current phase: [`docs/phases/phase-2-l1-filesystem.md`](docs/phases/phase-2-l1-filesystem.md)
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
