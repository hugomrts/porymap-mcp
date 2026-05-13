# Architecture Decision Records (ADRs)

Irreversible (or expensive-to-reverse) decisions about `porymap-mcp` are recorded here. Each ADR is **immutable once accepted** — corrections happen by writing a new ADR that supersedes the old one.

The goal: a future Claude Code session, or a contributor 6 months from now, can read an ADR and understand *why* we built it this way without having to relitigate the decision.

---

## How to write an ADR

1. Copy `0000-template.md` to `NNNN-short-slug.md` where `NNNN` is the next free number.
2. Fill in every section. Don't skip "Consequences".
3. Set the status to `Proposed` while you draft.
4. Once accepted (commit landed), change status to `Accepted` and never edit the file again.
5. If a future ADR supersedes this one, set status to `Superseded by 00XX`.

---

## Index

| ID | Title | Status |
|----|-------|--------|
| [0001](0001-fastmcp-as-mcp-framework.md) | Use FastMCP as the MCP framework | Accepted |
| [0002](0002-target-pokeemerald-expansion-first.md) | Target pokeemerald-expansion as the primary base game | Accepted |
| [0003](0003-project-class-and-config-driven-format.md) | `Project` class as single entrypoint, config-driven format parameters | Accepted |
| [0004](0004-tileset-metadata-source.md) | Tileset metadata is filesystem-first, C-struct lexer is a deferred enrichment | Accepted |
| [0005](0005-l1-discovery-tools-api.md) | L1 discovery tools — MCP API surface | Accepted |
| [0006](0006-l1-mutation-tools-api.md) | L1 mutation tools — MCP API surface | Accepted |
| [0007](0007-l1-event-tools-api.md) | L1 event-mutation tools — MCP API surface | Accepted |
| [0008](0008-prefab-library-and-paint-prefab.md) | Prefab library format and `paint_prefab` semantics | Accepted |
| [0009](0009-abandon-l2-live-porymap.md) | Abandon L2 (Live Porymap) and pivot directly to L3 (Vision) | Accepted |

> Add new rows here when an ADR lands.

---

## When does something need an ADR?

Write an ADR when:

- The decision is technical and hard to reverse later (framework choice, file format, API contract shape)
- The decision will surprise a future reader who doesn't know the context
- The decision was contentious — multiple options were seriously considered

**Don't** write an ADR for:

- Implementation details that can be refactored cheaply
- Stylistic preferences already covered by `CLAUDE.md`
- Decisions documented in a phase doc that affect only that phase

When in doubt, write the ADR. The cost is 10 minutes; the cost of *not* writing it is a debate re-run in 3 months.

---

## Format

We use a lightweight variant of [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions). See `0000-template.md`.
