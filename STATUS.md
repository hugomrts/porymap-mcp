# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** Two more production parsers shipped — `parsers/projectconfig.py` (typed accessors over an order-preserving entry dict; round-trips known and unknown keys) and `parsers/layoutsjson.py` (canonical `OrderedJson` write order, conditional border-dim emission). 49 new unit tests. Full suite at 71 passing, `mypy --strict` clean across 9 source files.

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
- `docs/decisions/` — ADRs 0001 (FastMCP), 0002 (pokeemerald-expansion target).
- `pyproject.toml`, `LICENSE`, `README.md` (skeleton), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- `src/porymap_mcp/` — package skeleton + three production parsers: `parsers/mapbin.py`, `parsers/projectconfig.py`, `parsers/layoutsjson.py`.
- `tests/` — pytest skeleton + three production test modules (71 cases total).
- `tests/fixtures/README.md` — hand-crafted fixture documentation.

**Not yet:** `parsers/mapgroups.py`, `parsers/mapjson.py`, `parsers/tilesetheaders.py`, `parsers/metatiles.py`, `parsers/attributes.py`, the `Project` class, all tools, and the full fixture pokeemerald project beyond what the current parsers need.

**Verified locally:** `pytest -q` → 71 passed; `ruff check .` → clean; `mypy --strict src/porymap_mcp` → clean on 9 source files.

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | In progress | Continue parsers: `mapgroups` and `mapjson`, then `tilesetheaders`/`metatiles`/`attributes`; start `Project` once `mapgroups` + `mapjson` land |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | Not started | Wait for Phase 2 ship |
| 4 — L3 (Vision) | Server renders maps to PNG | Not started | Wait for Phase 3 ship |
| 5 — Release | Publish to PyPI + community announcement | Not started | Wait for Phase 4 ship |

---

## Open decisions (blocking next work)

- [ ] **Poryscript vs raw `.inc`** for generated event scripts (Phase 2 §8 OQ3). Default direction: poryscript. ADR to write when implementing `add_sign`/`add_object_event`.
- [ ] **Prefab auto-import** when a prefab requires a tileset the target map doesn't use (Phase 2 §8 OQ1). Default direction: reject. ADR to write when implementing `paint_prefab`.

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
