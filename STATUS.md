# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** Claude environment scaffold + session-continuity system

---

## Current phase

**Phase 1 — Specification & environment setup.**
Active doc: [`docs/phases/phase-1-spec.md`](docs/phases/phase-1-spec.md)

We are *not yet* writing Python code. The current goal is to finish the spec so
Phase 2 (L1 implementation) can start cold from any new session.

---

## What exists in the repo today

- `MCP_PORYMAP.md` — strategic vision (FR), source of truth for *why*.
- `CLAUDE.md` — operating manual for Claude Code sessions.
- `.claude/agents/` — 7 specialized sub-agents (format, MCP design, domain, renderer, design critic, tests, docs).
- `.claude/settings.json` — bash permissions.
- `docs/phases/` — one spec per phase (this directory).
- `docs/decisions/` — ADRs for irreversible decisions.
- `STATUS.md` — this file.

**Not yet:** `pyproject.toml`, `src/porymap_mcp/`, `tests/`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, `LICENSE`.

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | In progress | Run POC parsing on a real pokeemerald project; confirm `.bin` byte layout |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | Not started | Wait for Phase 1 close |
| 3 — L2 (Live Porymap) | Porymap hot-reloads as the agent edits | Not started | Wait for Phase 2 ship |
| 4 — L3 (Vision) | Server renders maps to PNG, agent sees its output | Not started | Wait for Phase 3 ship |
| 5 — Release | Publish to PyPI + community announcement | Not started | Wait for Phase 4 ship |

---

## Open decisions (blocking next phase)

- [ ] **Base game default**: which `base_game_version` is the primary target — `emerald`, `firered`, or `pokeemerald-expansion`? Affects metatile attribute encoding.
- [ ] **First-class tool granularity**: which tools ship in L1 vs. which can wait? Draft list in `docs/phases/phase-2-l1-filesystem.md` §3.
- [ ] **Prefab spec format**: JSON inline in `headers.json`, or a separate `prefabs.json`? Defer to Porymap's native prefab format.

See `docs/decisions/` for already-resolved decisions.

---

## Quick links

- Vision: [`MCP_PORYMAP.md`](MCP_PORYMAP.md)
- Operating manual: [`CLAUDE.md`](CLAUDE.md)
- Current phase: [`docs/phases/phase-1-spec.md`](docs/phases/phase-1-spec.md)
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
