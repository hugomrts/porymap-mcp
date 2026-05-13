# porymap-mcp

> An [MCP](https://modelcontextprotocol.io) server that lets Claude — or any MCP client — author [Porymap](https://github.com/huderlem/porymap)-compatible Pokémon Gen-3 decompilation maps.

[![Status](https://img.shields.io/badge/status-alpha-orange)](#status)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)

---

> ⚠️ **Alpha.** v0.1.0 is in active development. The tool surface is frozen but no public release exists yet. See [`STATUS.md`](STATUS.md) for current progress.

---

## What it does

`porymap-mcp` exposes a set of high-level tools to an AI agent so it can:

- **Read** a pokeemerald-family project's maps, tilesets, events, and prefabs.
- **Write** map layouts (paint metatiles, rectangles, prefabs), events (warps, NPCs, signs, triggers), and project structure (register new maps).
- **(coming in v0.2)** Push changes to a running Porymap instance for live preview.
- **(coming in v1.0)** Render maps as PNG so the agent can *see* its own output and self-critique.

It edits the same files Porymap edits — your manual workflow in Porymap is never disrupted.

## What it doesn't do

- It does **not** modify your tilesets (creating new metatiles stays in Porymap).
- It does **not** run Porymap or require it to be open (for L1).
- It does **not** generate Pokémon graphics, music, or story content. It generates map *files*.

## Capability levels

| Level | What it gives you | Status |
|-------|-------------------|--------|
| **L1 — Filesystem** | Edit map files directly. Open Porymap *after* to visualize. | In progress (v0.1) |
| **L2 — Live Porymap** | Porymap reloads automatically as the agent edits. | Planned (v0.2) |
| **L3 — Vision** | Renders maps to PNG and returns them in tool calls — agent sees its work. | Planned (v1.0) |

## Compatibility

Currently targeting **`pokeemerald-expansion`** (rh-hideout's fork) as the primary base game. Vanilla `pokeemerald` and `pokefirered` are planned for v0.2 and v0.3 respectively. See [ADR-0002](docs/decisions/0002-target-pokeemerald-expansion-first.md) for rationale.

## Install (when released)

```bash
pip install porymap-mcp
# or
uvx porymap-mcp
```

Register it with your MCP client (example: Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "porymap": {
      "command": "python",
      "args": ["-m", "porymap_mcp"]
    }
  }
}
```

Then point your agent at a pokeemerald-expansion project — the project path is passed per tool call.

## First map in 5 minutes

Once registered, ask your agent something like:

> *Open my pokeemerald project at `~/code/pokeemerald`. Create a new map called `LakesideTown` in the `gMapGroup_TownsAndRoutes` group, 20×20, using `gTileset_General` + `gTileset_LittlerootTown`. Paint a small house at (3,4) and put a sign in front of it that says "Welcome to Lakeside!".*

The agent will:

1. Call `get_project_info` to confirm the project loads and which base game it targets.
2. Call `list_tilesets` to confirm the two requested tilesets exist.
3. Call `create_map` — this writes `data/maps/LakesideTown/map.json`, `data/layouts/LakesideTown/map.bin`, `data/layouts/LakesideTown/border.bin`, updates `data/layouts/layouts.json`, and registers the map in `data/maps/map_groups.json`.
4. Call `paint_prefab("house_small", x=3, y=4)` to stamp the house footprint.
5. Call `add_sign(x=4, y=7, text="Welcome to Lakeside!")` — this appends to `map.json` AND generates a poryscript stub at `data/maps/LakesideTown/scripts.pory`.

Open the project in Porymap (or rebuild your ROM) — the map is there.

### Tool surface (v0.1)

**Discovery (read-only):**
`get_project_info`, `list_maps`, `get_map_info`, `list_tilesets`, `list_metatiles`, `list_prefabs`, `list_events`.

**Mutation:**
`paint_metatile`, `paint_rectangle`, `flood_fill`, `set_border`, `paint_prefab`, `create_map`, `resize_map`, `register_map`, `unregister_map`.

**Events:**
`add_warp`, `add_object_event`, `add_sign`, `add_trigger`, `remove_event`.

Every tool is documented inline (its docstring is what your agent reads). The full contracts live in the ADRs:

- [ADR-0005](docs/decisions/0005-l1-discovery-tools-api.md) — discovery
- [ADR-0006](docs/decisions/0006-l1-mutation-tools-api.md) — mutation
- [ADR-0007](docs/decisions/0007-l1-event-tools-api.md) — events
- [ADR-0008](docs/decisions/0008-prefab-library-and-paint-prefab.md) — prefabs

### Prefab library

`paint_prefab` ships with a small built-in library of tileset-agnostic stamps: `single_tree`, `flower_patch`, `house_small`. The metatile IDs target vanilla pokeemerald conventions; forks with custom tilesets may need to retarget by registering replacement prefabs into `porymap_mcp.prefabs.LIBRARY` (a plain dict). See [ADR-0008](docs/decisions/0008-prefab-library-and-paint-prefab.md).

## Develop

```bash
git clone https://github.com/hugomrts/porymap-mcp
cd porymap-mcp
uv sync --all-extras   # or: pip install -e ".[dev]"
pre-commit install
pytest
```

See [`docs/phases/`](docs/phases/) for the implementation roadmap and [`CLAUDE.md`](CLAUDE.md) for the AI-assisted development conventions used in this repo (anyone can use them — the `.claude/agents/` are open-source too).

## Status

See [`STATUS.md`](STATUS.md) for the live snapshot of progress and [`docs/phases/`](docs/phases/) for the per-phase specifications.

## Acknowledgements

- [Porymap](https://github.com/huderlem/porymap) by Marcus Huderle — the editor we extend by AI.
- [pret](https://github.com/pret) — the decompilation projects that make all of this possible.
- [rh-hideout](https://github.com/rh-hideout) — the `pokeemerald-expansion` fork.
- [FastMCP](https://github.com/jlowin/fastmcp) — the Python MCP framework used here.
- [Anthropic](https://anthropic.com) — for MCP itself.

## License

[MIT](LICENSE).
