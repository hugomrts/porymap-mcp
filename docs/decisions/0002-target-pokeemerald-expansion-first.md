# ADR-0002: Target pokeemerald-expansion as the primary base game

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** Hugo Martins

---

## Context

Porymap and pokeemerald-family decompilations support multiple `base_game_version` values that affect the on-disk format — most importantly the encoding of metatile attributes (16-bit packing in emerald vs. different bit widths in firered/ruby). Our parsers and writers must branch on this value, and our test fixtures must be authored against a specific target.

The realistic user base for `porymap-mcp` is the ROM-hack community in 2026, which has substantially consolidated onto **rh-hideout's `pokeemerald-expansion`** fork. Major active hacks (Inclement Emerald, Emerald Imperium, the user's own project) are built on it. Vanilla `pret/pokeemerald` is still maintained but largely as the upstream the expansion rebases against — fewer humans start projects directly on vanilla today.

We have to pick *one* target to ship L1 against; supporting all three (emerald, firered, expansion) on day one triples fixture work and delays the first release.

---

## Decision

We target **`pokeemerald-expansion`** (rh-hideout's fork) as the primary `base_game_version` for v0.1.0.

Concretely:

1. The synthetic test fixtures (`tests/fixtures/fake_project_*`) are authored to match expansion's format.
2. Parsers detect `base_game_version` from `project_config.cfg` and **only** the expansion code path is fully implemented in v0.1.0.
3. If a project declares a different `base_game_version`, the server returns a typed error (`UnsupportedBaseGameError`) listing the supported versions — it does not silently use the wrong encoding.
4. Vanilla `pokeemerald` is added in v0.2.0 (alongside L2), via the same branched-parser mechanism. FireRed in v0.3.0 or later.

The expansion code path is also written so that switching `base_game_version` to `emerald` (vanilla) is a one-or-two-line difference (a different attribute-bit-mask constant), so adding vanilla later is cheap.

---

## Alternatives considered

### Alternative 1 — Target vanilla `pokeemerald` first

- **Upside:** smaller surface (no expansion-specific features), the best-documented variant, the cleanest reference fixtures.
- **Downside:** ~0% of actual users start new projects on vanilla in 2026. Shipping for it first is shipping for an audience that doesn't exist.
- **Why not:** maximizes the gap between "shipped" and "useful".

### Alternative 2 — Support all three (emerald, firered, expansion) from v0.1.0

- **Upside:** maximal community reach on day one.
- **Downside:** 3× the test fixtures, 3× the parser-branch verification, slower path to ship. Some expansion features (e.g. extended map JSON keys) have no counterpart in firered, complicating the abstraction.
- **Why not:** classic over-scoping. The L2/L3 capabilities are higher leverage than format breadth. Adding a second base game is cheap once L1 ships.

### Alternative 3 — Target FireRed

- **Upside:** simplest format historically; FireRed is the "introductory" decomp for newcomers.
- **Downside:** smaller current active hacker base than emerald-family. The user's own project is on expansion.
- **Why not:** misaligned with the strongest user signal we have (the project's own author).

---

## Consequences

**Positive:**
- Day-one users are the realistic users.
- Test fixtures match the format of the user's actual project — manual cross-checks against real Porymap output cost minutes, not days.
- Expansion's extended JSON keys (Gen 1-9 species, modern moves) flow through naturally without needing normalization.

**Negative:**
- Vanilla and FireRed users get an explicit "not supported yet" error in v0.1.0. We must communicate this prominently in the README and on every "list of supported versions" surface.
- Expansion evolves quickly (rh-hideout ships breaking changes); we'll need to pin which expansion revisions are tested in CI and update as expansion ships.
- The parser code carries a base-game branch from day one. Branches not yet implemented must raise clearly — they cannot fall through to the default case.

**Neutral:**
- The `porymap-format-expert` agent now has a clear primary target — its citations should default to expansion's source when it differs from vanilla.
- The `rom-hack-domain` agent's conventions for naming and structure follow expansion's, not vanilla's, when they diverge.

---

## References

- pokeemerald-expansion: https://github.com/rh-hideout/pokeemerald-expansion
- Porymap project config format: https://huderlem.github.io/porymap/manual/project-files.html
- Related: `MCP_PORYMAP.md` §1, §5
- Phase docs affected: `docs/phases/phase-2-l1-filesystem.md` (parser branch), `docs/phases/phase-5-release.md` (supported-versions communication)
