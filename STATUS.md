# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** **Phase 2 (L1 Filesystem) code-complete.** Shipped ADR-0006 (8 map/structure mutation tools), ADR-0007 (5 event-mutation tools + poryscript-default for OQ3), ADR-0008 (prefab library + `paint_prefab`). Implemented all 21 MCP tools registered on the FastMCP server: 7 discovery (`get_project_info`, `list_maps`, `get_map_info`, `list_tilesets`, `list_metatiles`, `list_prefabs`, `list_events`), 7 map mutators (`paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`, `create_map`, `resize_map`, `paint_prefab`), 2 structure (`register_map`, `unregister_map`), 5 events (`add_warp`, `add_object_event`, `add_sign`, `add_trigger`, `remove_event`). `add_sign` generates a poryscript stub (or `.inc` when `use_poryscript=0`). Shipped `parsers/metatiles.py` + `parsers/attributes.py` (config-driven mask decoding) and upgraded `list_metatiles` from stub to fully-populated. Built-in prefab library (`single_tree`, `flower_patch`, `house_small`). README updated with the "first map in 5 minutes" walkthrough. Repo total: **298 passing**, ruff + format + mypy clean on 23 source files. **What remains to ship v0.1.0:** integration test against a real Porymap binary (needs a human + a binary), CI matrix verification, PyPI publication, `v0.1.0` tag.

---

## Current phase

**Phase 2 — L1: Filesystem MCP** (implementation in progress).
Active doc: [`docs/phases/phase-2-l1-filesystem.md`](docs/phases/phase-2-l1-filesystem.md)

We are writing production code from day one. The phase ships when all L1 tools work, coverage targets are met, and an integration test against a real Porymap project passes.

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

**Not yet (post-L1):** typed event dataclasses (deferred to v0.2.0), on-disk extensible prefab JSON library (v0.2.0), L3 metatile graphic decoding for rendering, integration test against a real Porymap binary.

**Verified locally:** `pytest` → 298 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 23 source files.

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | Code-complete | All 21 tools shipped + tested. Remaining for tag: integration test against real Porymap, CI matrix verification, then tag `v0.1.0`. |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | Not started | Wait for Phase 2 ship |
| 4 — L3 (Vision) | Server renders maps to PNG | Not started | Wait for Phase 3 ship |
| 5 — Release | Publish to PyPI + community announcement | Not started | Wait for Phase 4 ship |

---

## Open decisions (blocking next work)

- [x] **Poryscript vs raw `.inc`** — resolved by ADR-0007: poryscript default, `.inc` fallback when `use_poryscript=0`.
- [x] **Prefab auto-import** — resolved by ADR-0008: reject on tileset mismatch, no auto-import.
- [x] **Typed event dataclasses** — deferred to v0.2.0 per ADR-0007 §"Decision"; raw-dict events suffice for L1.

Resolved decisions live under [`docs/decisions/`](docs/decisions/). No open decisions block the next session.

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
