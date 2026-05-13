# Phase 1 — Specification & Environment Setup

> **Status:** In progress
> **Owner:** Hugo + Claude Code sessions
> **Started:** 2026-05-12
> **Closes when:** All "Exit criteria" below are checked, Phase 2 can start cold.

---

## 1. Goal

Establish enough specification and tooling that **a Claude Code session opening this repo for the first time can start implementing Phase 2 in under 10 minutes**, without needing the previous session's context.

This phase produces **no Python code**. It produces decisions, specs, and the working environment.

---

## 2. Exit criteria

The phase closes when *all* of these are true:

- [x] Strategic vision document exists (`MCP_PORYMAP.md`)
- [x] `CLAUDE.md` operating manual exists and references all 7 sub-agents
- [x] All 7 sub-agents exist under `.claude/agents/`
- [x] `.claude/settings.json` and `.gitignore` exist
- [x] `STATUS.md` exists and accurately reflects current state
- [x] Phase docs exist for Phases 1–5
- [x] ADR template and first ADR exist
- [ ] **POC parse:** read a real `.bin` map file from a real pokeemerald project and dump its metatile grid, *manually verifying* against Porymap's view
- [ ] **POC write:** modify one metatile, save the `.bin`, re-open in Porymap, confirm the change is visible and persistent
- [ ] **Base-game decision recorded** as an ADR (which `base_game_version` we support first)
- [ ] **L1 tool surface frozen** — the list in `phase-2-l1-filesystem.md` §3 is signed off
- [ ] **Synthetic fixture project** designed (byte layout documented) — actual files created in Phase 2

POC parse/write can be a throwaway Python script under `.scratch/` — it doesn't need to be production code.

---

## 3. Sub-tasks

### Documentation (done)
- [x] Write `CLAUDE.md`
- [x] Write 7 sub-agent specs
- [x] Write `STATUS.md`
- [x] Write phase docs 1–5 skeletons
- [x] Write ADR template

### POC validation (pending)
- [ ] Clone `rh-hideout/pokeemerald-expansion` locally
- [ ] Pick the smallest map (probably `data/layouts/UnknownMap/` or similar) and dump its `map.bin` bytes with `xxd`
- [ ] Write a 50-line Python script that parses the `.bin` → list of `(metatile_id, collision, elevation)` tuples
- [ ] Open the same map in Porymap, manually cross-check
- [ ] Modify one metatile id in the bytes, save, re-open in Porymap
- [ ] Record findings in this doc under "POC learnings"
- [ ] Open ADR for base_game_version default

### Spec finalization (pending)
- [ ] Freeze L1 tool list in `phase-2-l1-filesystem.md` §3
- [ ] Document the synthetic fixture project layout in `phase-2-l1-filesystem.md` §6
- [ ] List all upstream files we'll need to read at runtime (paths only) in `phase-2-l1-filesystem.md` §4

---

## 4. Open questions

Track here, resolve as ADRs once decided.

- **Q1 — Base game default.** Emerald, FireRed, or Emerald-expansion? Expansion is the user's actual target, so likely that. But emerald-vanilla is the safest "smallest test case". Decide.
- **Q2 — Prefab source of truth.** Porymap stores prefabs in its own settings file (`porymap.cfg`-adjacent), not in the project. Do we read Porymap's prefab file, or define our own format? Probably the former for compatibility.
- **Q3 — Path-relative vs. absolute project paths.** Tools take `project_path` — absolute Path? Allow relative? Resolve relative against CWD or against the MCP server's launch dir? Default: absolute Path, no resolution magic.
- **Q4 — Pokémon-version-specific map.json fields.** Some keys differ between FireRed and Emerald. Do we expose all of them or normalize? Probably expose all, with optional defaults.
- **Q5 — Concurrent edits.** If Porymap is open *and* the agent edits, who wins on save conflict? Probably last-write-wins with a warning, but document explicitly.

---

## 5. POC learnings

> Fill this in after each POC iteration.

*(empty)*

---

## 6. Session log

Each session that touches Phase 1 adds one entry.

### 2026-05-12 — Strategic vision
- Created `MCP_PORYMAP.md`
- Decided on the 3-level capability ladder (L1/L2/L3)

### 2026-05-13 — Claude environment scaffold + session continuity
- Created `CLAUDE.md`, 7 sub-agents (`.claude/agents/`), `.claude/settings.json`, `.gitignore`
- Added `map-design-critic` as the 7th agent (quality gate)
- Set up `STATUS.md`, `docs/phases/*`, `docs/decisions/` (ADR system)
- Committed on branch `claude/review-repo-8r7nq`

---

## 7. References

- Vision: [`../../MCP_PORYMAP.md`](../../MCP_PORYMAP.md)
- Operating manual: [`../../CLAUDE.md`](../../CLAUDE.md)
- Snapshot: [`../../STATUS.md`](../../STATUS.md)
- Next phase: [`phase-2-l1-filesystem.md`](phase-2-l1-filesystem.md)
