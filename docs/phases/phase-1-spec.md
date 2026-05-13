# Phase 1 — Specification & Environment Setup

> **Status:** ✅ Closed (2026-05-13)
> **Owner:** Hugo + Claude Code sessions
> **Started:** 2026-05-12
> **Closed:** 2026-05-13 — moved to Phase 2 (L1 implementation)

---

## 1. Goal (recap)

Establish enough specification and tooling that a Claude Code session opening this repo for the first time can start implementing Phase 2 in under 10 minutes, without needing the previous session's context.

This phase produced **no Python code**. It produced decisions, specs, and the working environment.

---

## 2. Exit criteria (final)

All checked at phase close:

- [x] Strategic vision document exists (`MCP_PORYMAP.md`)
- [x] `CLAUDE.md` operating manual exists and references all 7 sub-agents
- [x] All 7 sub-agents exist under `.claude/agents/`
- [x] `.claude/settings.json` and `.gitignore` exist
- [x] `STATUS.md` exists and accurately reflects current state
- [x] Phase docs exist for Phases 1–5
- [x] ADR template and first ADRs exist
- [x] **Base-game decision recorded** as ADR-0002 (pokeemerald-expansion as primary)
- [x] **L1 tool surface frozen** — see `phase-2-l1-filesystem.md` §3

**Dropped from the original exit criteria** (with reasoning):

- ~~**POC parse:** read a real `.bin` and dump its metatile grid, manually verifying against Porymap~~
- ~~**POC write:** modify one metatile, save, re-open in Porymap, confirm visible~~

These were de-risking steps justified for a prototype, not a production-ready library. They are replaced by:

1. **Production-grade parsers from day one**, citing Porymap source (`src/core/maplayout.cpp`, `src/core/metatile.cpp`) and the pokeemerald headers as authoritative documentation. The `porymap-format-expert` agent's job is exactly this.
2. **Hand-crafted byte-level golden fixtures** under `tests/fixtures/` — every byte is explained and tested. The fixture *is* the cross-check.
3. **An opt-in integration test** (`@pytest.mark.requires_porymap`) that, on a machine with Porymap installed, opens a real generated project and asserts visual identity. This runs locally and nightly in CI, replacing the manual POC verification.

The "verify against Porymap" requirement does not go away — it moves from a one-shot manual POC into the permanent test suite. Better hygiene, no loss of confidence.

---

## 3. Sub-tasks (final state)

### Documentation
- [x] Write `CLAUDE.md`
- [x] Write 7 sub-agent specs
- [x] Write `STATUS.md`
- [x] Write phase docs 1–5 skeletons
- [x] Write ADR template

### Decisions
- [x] ADR-0001: FastMCP as MCP framework
- [x] ADR-0002: pokeemerald-expansion as primary base game

### Spec finalization
- [x] L1 tool list frozen in `phase-2-l1-filesystem.md` §3
- [x] Synthetic fixture project structure documented in `phase-2-l1-filesystem.md` §6
- [x] Upstream file list documented in `phase-2-l1-filesystem.md` §4

---

## 4. Open questions (resolved)

- **Q1 — Base game default.** Resolved by ADR-0002: pokeemerald-expansion.
- **Q2 — Prefab source of truth.** Carried forward into Phase 2 §8 OQ1 (auto-import vs. reject).
- **Q3 — Path resolution.** Resolved inline: `project_path` is always an absolute `Path`; no implicit CWD resolution. (Will be enforced in the `Project` class.)
- **Q4 — Pokémon-version-specific map.json fields.** Carried forward into Phase 2 §8 (expose all, optional defaults).
- **Q5 — Concurrent edits with Porymap open.** Carried forward into Phase 3 §7 OQ2 (last-write-wins with explicit warning).

---

## 5. Session log

### 2026-05-12 — Strategic vision
- Created `MCP_PORYMAP.md`
- Decided on the 3-level capability ladder (L1/L2/L3)

### 2026-05-13 — Claude environment scaffold
- Created `CLAUDE.md`, 7 sub-agents (`.claude/agents/`), `.claude/settings.json`, `.gitignore`
- Added `map-design-critic` as the 7th agent (quality gate)
- Committed on branch `claude/review-repo-8r7nq`

### 2026-05-13 — Session continuity system
- Created `STATUS.md`, phase docs 1–5, ADR system (`docs/decisions/`)
- Updated `CLAUDE.md` with §0 "Session start & end protocol"

### 2026-05-13 — Phase 1 close
- Dropped manual POC tasks (over-engineering for a prod-ready library)
- ADR-0001 (FastMCP) and ADR-0002 (pokeemerald-expansion target) accepted
- Handed off to Phase 2

---

## 6. References

- Vision: [`../../MCP_PORYMAP.md`](../../MCP_PORYMAP.md)
- Operating manual: [`../../CLAUDE.md`](../../CLAUDE.md)
- Snapshot: [`../../STATUS.md`](../../STATUS.md)
- Next phase: [`phase-2-l1-filesystem.md`](phase-2-l1-filesystem.md)
- Decisions: [`../decisions/`](../decisions/)
