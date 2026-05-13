# CLAUDE.md — porymap-mcp

> Operating manual for Claude Code sessions on this repository.
> Read this end-to-end before doing any non-trivial task.
> The strategic vision document is `MCP_PORYMAP.md` (in French) — defer to it for *why*, defer to this file for *how*.

---

## 1. What this project is

`porymap-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server that lets an AI agent (Claude or any MCP client) author Pokémon Gen-3 decompilation maps — the same files [Porymap](https://github.com/huderlem/porymap) edits graphically — without needing Porymap to be open.

Target downstream projects: `pret/pokeemerald`, `pret/pokefirered`, `pret/pokeruby`, and forks like `rh-hideout/pokeemerald-expansion`.

The roadmap has three levels, each shippable on its own:

| Level | Capability | Status |
|-------|-----------|--------|
| **L1 — Filesystem** | Read/write map files directly. Porymap not required. | Not started |
| **L2 — Live Porymap** | Porymap (running in parallel) reloads as the agent edits. | Not started |
| **L3 — Vision** | Server renders the map as PNG and returns it inside tool results so the agent can *see* its output. | Not started |

This repo is currently at the **specification stage**. No Python code yet. The next implementation milestone is L1.

---

## 2. Tech stack & repo layout

**Runtime:** Python 3.11+
**MCP framework:** [FastMCP](https://github.com/jlowin/fastmcp) (the canonical Python framework for MCP servers)
**Tests:** `pytest` + `pytest-cov`
**Image rendering (L3):** `Pillow`
**Packaging:** `pyproject.toml`, published to PyPI as `porymap-mcp`
**Linting/formatting:** `ruff` (lint + format), `mypy --strict` for type checking
**Pre-commit:** `pre-commit` with ruff + mypy hooks

**Planned repo layout** (do not create speculatively — create as needed):

```
porymap-mcp/
├── src/porymap_mcp/
│   ├── __init__.py
│   ├── server.py             # FastMCP entry point
│   ├── tools/                # MCP tool implementations
│   │   ├── discovery.py      # list_maps, get_map_info, list_metatiles
│   │   ├── maps.py           # create_map, paint_metatile, paint_rectangle
│   │   ├── events.py         # add_warp, add_object_event, add_sign
│   │   ├── prefabs.py        # list_prefabs, paint_prefab
│   │   └── rendering.py      # render_map (L3)
│   ├── parsers/              # Read/write pokeemerald project files
│   │   ├── mapbin.py         # .bin metatile/collision/elevation layout
│   │   ├── mapjson.py        # map.json (events + metadata)
│   │   ├── layoutsjson.py    # layouts.json index
│   │   ├── mapgroups.py      # map_groups.json index
│   │   └── tileset.py        # tilesets_headers + metatile data
│   └── render/               # L3 rendering pipeline
├── tests/
│   ├── fixtures/             # Tiny synthetic pokeemerald project for tests
│   ├── unit/
│   └── integration/
├── examples/                 # MCP client recipes, sample prompts
├── docs/
├── pyproject.toml
├── README.md
├── ROADMAP.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                   # MIT (planned)
├── MCP_PORYMAP.md           # Strategic vision (FR, source of truth)
└── CLAUDE.md                # This file
```

---

## 3. Sub-agents available in `.claude/agents/`

Delegate to these agents whenever the task matches their domain. Each agent has its own system prompt with specialized knowledge — using them keeps the main context clean and produces better results than trying to be a generalist.

| Agent | Use when |
|-------|----------|
| `porymap-format-expert` | Parsing, writing, or reasoning about `.bin` layouts, `map.json`, `layouts.json`, `map_groups.json`, tileset headers, metatile data, attribute formats. The reverse-engineering specialist. |
| `mcp-tool-designer` | Designing or refactoring FastMCP tool signatures, return shapes, error contracts, server lifecycle, MCP best practices. Use *before* writing a new tool. |
| `rom-hack-domain` | Questions about pokeemerald-expansion conventions, prefab semantics, Gen 3 map idioms, rh-hideout patterns, ROM-hack community expectations. |
| `map-renderer` | Phase 4 work: Pillow image composition, tileset → metatile → map rendering, layer compositing (collision, elevation), PNG output optimization. |
| `map-design-critic` | **The quality gate.** Reviews rendered maps against a 12-criterion rubric (path geometry, tile variety, building placement, etc.) and produces a prioritized fix list. Use after any non-trivial map generation, before reporting "done" to the user. |
| `test-engineer` | Designing pytest fixtures with synthetic pokeemerald projects, golden-file testing strategies, integration tests against real Porymap output. |
| `docs-curator` | README, ROADMAP, CHANGELOG, CONTRIBUTING, examples, community-facing copy. Keeps tone consistent and publishable. |

**Default rule:** if a task is dominated by *one* of these domains, spawn the agent rather than doing it yourself. If a task spans two or more, do it yourself and pull each agent in for targeted questions.

**Quality loop (the project's reason to exist):** the end-to-end agent loop is
`paint → render (map-renderer) → critique (map-design-critic) → fix → re-render`.
Any map-generation task that doesn't close this loop is incomplete. The user's directive: *Claude must produce **quality** maps*, not just syntactically valid files.

---

## 4. Coding conventions

- **Types everywhere.** All functions, methods, and module-level names are fully annotated. CI fails on `mypy --strict` errors.
- **Pure parsers.** Code under `parsers/` is side-effect-free and works on `bytes` / `dict` / `pathlib.Path`. No `print`, no logging there.
- **Tools are thin.** Functions under `tools/` orchestrate parsers and return MCP-friendly responses. Business logic stays in parsers/renderers.
- **Errors are explicit.** Define a small `PorymapMCPError` hierarchy in `porymap_mcp/errors.py`. Tools translate these into structured MCP error responses — never raise raw `Exception` across the MCP boundary.
- **No silent fallbacks.** If a project file is missing or malformed, fail fast with a descriptive error. Don't paper over corruption.
- **File I/O is atomic.** Writes to project files go through a `write_atomic(path, data)` helper (write to `.tmp`, then `os.replace`). Never partially overwrite a map.
- **Encoding.** All text files are UTF-8 with LF line endings (matches pret conventions).
- **Naming.** Snake_case for Python, kebab-case for CLI flags, match upstream casing exactly for game data (e.g. `MAP_LITTLEROOT_TOWN`, `gMapHeader_LittlerootTown`).
- **Public API stability.** Anything exported from `porymap_mcp.__init__` is semver-stable. Tool *names* and *parameter schemas* are also semver-stable once a tool ships — breaking changes require a major bump.

---

## 5. MCP tool design rules

- **Idempotent where possible.** `paint_metatile(x, y, id)` called twice with the same args is a no-op. Required for safe retries.
- **Coordinates are `(x, y)` with origin top-left**, matching Porymap. Never flip Y silently.
- **Project path is always the first argument.** Allows multi-project usage; never use a global "current project" state.
- **Return structured data, not prose.** Tools return JSON-serializable dicts. Human-readable summaries go in a `summary` field, never as the whole response.
- **Render results (L3) attach the PNG as an `image` content block**, not as base64 in JSON — use the MCP content type properly.
- **Side-effects in the response.** Every write-tool's response includes the list of files modified, so the agent can reason about what changed.
- **Discovery before mutation.** Encourage agents to call `get_map_info` before `paint_*`. Document this in tool descriptions.

When designing a new tool, consult `mcp-tool-designer` first.

---

## 6. Testing rules

- Every parser has unit tests with both happy-path and corruption fixtures.
- Every tool has at least one integration test against a synthetic pokeemerald project under `tests/fixtures/fake_project/`.
- Golden-file tests for rendered PNGs (L3) live under `tests/fixtures/renders/`. Update them with `pytest --update-golden` (custom flag).
- Coverage target: 90% line, 80% branch. Enforced in CI.
- **No network in tests.** No GitHub fetches, no PyPI lookups, no real Porymap invocation in unit tests.
- Integration tests that require Porymap binary are marked `@pytest.mark.requires_porymap` and skipped by default.

When designing tests, consult `test-engineer`.

---

## 7. Workflow

### Branching
- `main` is protected, always green, always releasable.
- Feature branches: `feat/<short-slug>`, `fix/<short-slug>`, `docs/<short-slug>`, `chore/<short-slug>`.
- Claude Code review branches: `claude/<purpose>-<short-hash>`.

### Commits
- [Conventional Commits](https://www.conventionalcommits.org/) format:
  - `feat(tools): add paint_rectangle`
  - `fix(parsers): handle empty border_blockdata`
  - `docs(readme): document L2 hot-reload`
- One logical change per commit. Refactors separate from behavior changes.
- Never `git add -A` blindly — stage files individually or by directory.

### Pull requests
- Title in conventional-commit form.
- Body: *what* changed and *why*, with an explicit "Testing" section.
- Link to the relevant ROADMAP item / MCP_PORYMAP.md section.

### Releases
- Semver. Tag `vX.Y.Z`. `CHANGELOG.md` updated in the same commit.
- L1 ships as `0.1.0`. L2 as `0.2.0`. L3 as `1.0.0` (first stable).

---

## 8. How to run things (once implemented)

```bash
# Install for development
uv sync --all-extras            # or: pip install -e ".[dev]"

# Run the MCP server (stdio transport, default)
python -m porymap_mcp

# Test
pytest                          # all tests except those needing Porymap
pytest -m requires_porymap      # opt-in integration

# Lint & type-check
ruff check .
ruff format --check .
mypy src

# Pre-commit (auto-runs ruff + mypy)
pre-commit run --all-files
```

The MCP server is registered in an MCP client (Claude Desktop, Claude Code, etc.) via:

```json
{
  "mcpServers": {
    "porymap": {
      "command": "python",
      "args": ["-m", "porymap_mcp"],
      "env": {}
    }
  }
}
```

The project path is passed per-tool-call, never via env.

---

## 9. Domain quick-reference

| Term | Meaning |
|------|---------|
| **MCP** | Model Context Protocol — Anthropic's open protocol for tool-enabled LLMs. |
| **FastMCP** | Pythonic framework for building MCP servers (decorator-based, like FastAPI). |
| **Porymap** | The graphical map editor for pokeemerald-family decomps. C++/Qt. |
| **pokeemerald** | The community decompilation of Pokémon Emerald (pret org). |
| **pokeemerald-expansion** | Fork by rh-hideout adding Gen 1-9, Mega Evolution, modern QoL. |
| **Metatile** | 16×16-pixel block, composed of four 8×8 tiles. The atomic unit of a map. |
| **Tileset** | A library of metatiles. Each map uses a *primary* (shared) + *secondary* (map-specific) tileset. |
| **Layout** | The 2D grid of metatile IDs + collision + elevation, stored as `.bin`. |
| **Border** | The repeating frame shown when the camera is outside the map proper. |
| **Prefab** | A named group of metatiles (Pokémon Center, Pokémart, generic house) Porymap can stamp. |
| **Map group** | Logical grouping of maps (e.g. all routes, all towns). Index lives in `map_groups.json`. |
| **Warp** | Tile that teleports the player to another map. |
| **Object event** | An NPC, item ball, hidden item, or other interactable. |

For deeper reference, the [Porymap manual](https://huderlem.github.io/porymap/) and the pokeemerald source itself are the canonical sources.

---

## 10. Things to *not* do

- **Don't add features beyond what the current phase requires.** L1 doesn't need a renderer. L2 doesn't need PyPI. Stay disciplined.
- **Don't invent file formats.** Always match what Porymap writes byte-for-byte. If unsure, generate the file in Porymap and diff.
- **Don't break upstream conventions.** Constants, paths, JSON keys must match pokeemerald exactly. Even harmless renames hurt downstream users.
- **Don't ship without integration tests against the synthetic project fixture.** Unit tests on parsers alone don't catch wiring bugs.
- **Don't commit `MCP_PORYMAP.md` edits without owner sign-off** — it's the strategic source of truth, not a working doc.
- **Don't add a license header to every file.** One `LICENSE` at the repo root is enough.

---

## 11. Current status snapshot

- **Branch model:** `main` exists with only the strategic doc; this Claude environment lives on the working branch.
- **Phase:** 0 (spec & env setup). Phase 2 (L1 implementation) is the next code milestone.
- **Open POC question:** still need to confirm the exact `.bin` byte layout for collision/elevation on `pokeemerald-expansion`'s tileset format. The `porymap-format-expert` agent should be the one to verify when we start parsing.

Keep this section honest — update it as phases close.
