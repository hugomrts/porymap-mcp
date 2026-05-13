# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** Wrote **ADR-0004** (tileset-metadata representation) — adopting a two-stage strategy: filesystem-first discovery in v0.1.0 (glob `data/tilesets/{primary,secondary}/*/`), C-struct lexer enrichment deferred until a tool actually needs it. Then shipped `parsers/mapjson.py` — top-level `MapJson` dataclass with the 14 well-known header fields typed, `Connection` dataclass for the connections array, event arrays kept as `tuple[dict[str, object], ...]` for verbatim round-trip, custom-key preservation at both top level and inside connections. Empty `connections` is read from both `null` and `[]`, always written as `null` per Porymap. 36 new tests, repo total **161 passing**, ruff + mypy clean. Typed event dataclasses (per the format-expert's split recommendation) deferred to the session that ships `add_warp` / `add_object_event`.

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
- `docs/decisions/` — ADRs 0001 (FastMCP), 0002 (pokeemerald-expansion target), 0003 (`Project` class + config-driven format), 0004 (tileset-metadata source: filesystem-first).
- `pyproject.toml`, `LICENSE`, `README.md` (skeleton), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- `src/porymap_mcp/` — five production parsers (`mapbin`, `projectconfig`, `layoutsjson`, `mapgroups`, `mapjson`) and the `Project` class (`project.py`) tying them together with lazy property loading, atomic writes, and `map.bin`/`border.bin` dimension invariants enforced against `layouts.json`.
- `tests/` — pytest skeleton + six production test modules (161 cases total).
- `tests/fixtures/README.md` — hand-crafted fixture documentation.

**Not yet:** `parsers/tileset.py` (per ADR-0004 stage 1), typed event dataclasses (deferred until mutation tools land), `parsers/metatiles.py`, `parsers/attributes.py`, all tools, and the full fixture pokeemerald project beyond inline-text test fixtures.

**Verified locally:** `pytest` → 161 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 12 source files.

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | In progress | Implement `parsers/tileset.py` (ADR-0004 stage 1: filesystem glob), then build the discovery tools (`get_project_info`, `list_maps`, `get_map_info`, `list_tilesets`, `list_metatiles`, `list_events`) on top of `Project`. |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | Not started | Wait for Phase 2 ship |
| 4 — L3 (Vision) | Server renders maps to PNG | Not started | Wait for Phase 3 ship |
| 5 — Release | Publish to PyPI + community announcement | Not started | Wait for Phase 4 ship |

---

## Open decisions (blocking next work)

- [ ] **Poryscript vs raw `.inc`** for generated event scripts (Phase 2 §8 OQ3). Default direction: poryscript. ADR to write when implementing `add_sign`/`add_object_event`.
- [ ] **Prefab auto-import** when a prefab requires a tileset the target map doesn't use (Phase 2 §8 OQ1). Default direction: reject. ADR to write when implementing `paint_prefab`.
- [ ] **Typed event dataclasses** vs. raw-dict events (the format-expert recommended a split into `parsers/events.py` with `Union[ObjectEvent, WarpEvent, ...]` types; current parser keeps events as `dict[str, object]`). Defer until the first event-mutation tool is implemented — that's when typed access actually pays for itself. No ADR until then.

Resolved decisions live under [`docs/decisions/`](docs/decisions/).

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
