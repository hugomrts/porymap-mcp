# STATUS — porymap-mcp

> One-page snapshot of where the project stands right now.
> **Always read this first** when starting a new Claude Code session.
> Updated at the end of every session that moves the project forward.

**Last updated:** 2026-05-13
**Last session:** Wrote **ADR-0005** (L1 discovery-tool API surface, frozen for v0.1.0), added `Project.get_map_entry` / `Project.get_map_json` / `Project.iter_maps` with a per-instance `map.json` cache (bare-name keyed, resolves `MAP_*` constant via `MapJson.id`), and shipped all seven discovery tools in **`src/porymap_mcp/tools/discovery.py`** registered on the FastMCP server: `get_project_info`, `list_maps`, `get_map_info`, `list_tilesets`, `list_metatiles` (stub mode — `metatiles=[]` + file-size-derived count per ADR-0005), `list_prefabs` (empty list — discovery pair for the future `paint_prefab`), `list_events` (raw-dict events with synthesized `_event_id` of the form `<class>:<index>`). Each tool body is a plain function (testable directly); a thin `_tool_*` wrapper with the LLM-facing docstring is what FastMCP registers. Repo total: **207 passing**, ruff + format + mypy clean on 15 source files. **Discovery surface is shippable**; next session goes to mutation tools (`paint_metatile` → `flood_fill` → `set_border` → `create_map`).

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
- `docs/decisions/` — ADRs 0001 (FastMCP), 0002 (pokeemerald-expansion target), 0003 (`Project` class + config-driven format), 0004 (tileset-metadata source: filesystem-first), 0005 (L1 discovery-tool API surface).
- `pyproject.toml`, `LICENSE`, `README.md` (skeleton), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- `src/porymap_mcp/` — six production parsers (`mapbin`, `projectconfig`, `layoutsjson`, `mapgroups`, `mapjson`, `tileset`), the `Project` class (`project.py`) with `iter_maps` / `get_map_entry` / `get_map_json` on top of a lazy bare-name `map.json` cache, and **`tools/discovery.py`** implementing all seven L1 read-only tools registered on the FastMCP server.
- `tests/` — pytest skeleton + eight production test modules (207 cases total).
- `tests/fixtures/README.md` — hand-crafted fixture documentation.

**Not yet:** typed event dataclasses (deferred until first event-mutation tool), `parsers/metatiles.py`, `parsers/attributes.py`, all mutation tools, and the full fixture pokeemerald project beyond inline-text test fixtures.

**Verified locally:** `pytest` → 207 passed; `ruff check .` → clean; `ruff format --check .` → clean; `mypy --strict src/porymap_mcp` → clean on 15 source files.

---

## Phase progress

| Phase | Goal | Status | Next action |
|-------|------|--------|-------------|
| 1 — Spec | Finalize tool surface, formats, scope of L1 | ✅ Closed | — |
| 2 — L1 (Filesystem) | MCP server that edits map files without Porymap running | In progress | Discovery tools shipped (ADR-0005). Next: simple mutation tools — `paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border` — directly on top of `Project.read_map_bin` / `Project.write_map_bin`. Consult `mcp-tool-designer` before signing off on signatures. |
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
