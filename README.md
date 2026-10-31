# porymap-mcp

**An [MCP](https://modelcontextprotocol.io) server that lets Claude, or any MCP client, paint, render and critique [Porymap](https://github.com/huderlem/porymap)-compatible maps for Pokémon Gen 3 decompilation projects.**

[![CI](https://github.com/hugomrts/porymap-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hugomrts/porymap-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/porymap-mcp)](https://pypi.org/project/porymap-mcp/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/hugomrts/porymap-mcp/blob/main/LICENSE)

| Iteration 1: first draft | Iteration 2: after one critique pass |
|:---:|:---:|
| ![Iteration 1 render](https://raw.githubusercontent.com/hugomrts/porymap-mcp/main/examples/04_render_loop/renders/iter1.png) | ![Iteration 2 render](https://raw.githubusercontent.com/hugomrts/porymap-mcp/main/examples/04_render_loop/renders/iter2.png) |
| Score **7 / 36** | Score **21 / 36** |

Both images were rendered by the server itself. The agent **paints** the map, **renders** it to PNG, gets the image back in the tool response, **critiques** it against a 12-criterion Gen 3 design rubric, fixes the top issues and renders again. Runnable walkthrough: [`examples/04_render_loop/`](https://github.com/hugomrts/porymap-mcp/tree/main/examples/04_render_loop).

---

## What it does

- **Reads** a pokeemerald-family project: maps, layouts, tilesets, metatiles, events, prefabs.
- **Writes** the same files Porymap writes: metatiles, rectangles, flood fills, borders, prefabs, warps, NPCs, signs (with a script stub), triggers, new maps and map-group registration. Writes are atomic.
- **Renders** maps, regions and single metatiles to PNG and returns them as MCP `image` content blocks. Output is pixel-identical to Porymap's own export on a 5-map reference corpus (Littleroot Town, Route 101, Granite Cave 1F, Battle Frontier Outside East, plus a synthetic edge case).

Porymap does not need to be running. Open the project in Porymap whenever you like: your manual workflow is untouched.

It does **not** edit tilesets (creating new metatiles stays in Porymap), and it does not generate graphics, music or story content.

## Compatibility

Built and tested against [`rh-hideout/pokeemerald-expansion`](https://github.com/rh-hideout/pokeemerald-expansion), the base most active hacks use today ([ADR-0002](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0002-target-pokeemerald-expansion-first.md)). Vanilla [`pret/pokeemerald`](https://github.com/pret/pokeemerald) uses the same file formats and loads the same way. Bit masks and paths are read from your `porymap.project.cfg`, so nothing is hard-coded per fork. `pokefirered` and `pokeruby` projects are recognised but not covered by the test corpus yet.

## Install

```bash
pip install "porymap-mcp[render]"
```

Or run it with no install step via [uv](https://docs.astral.sh/uv/):

```bash
uvx --from "porymap-mcp[render]" porymap-mcp
```

The `render` extra pulls in Pillow and numpy for the three render tools. Without it (`pip install porymap-mcp`), the 21 read/write tools work on their own.

Requires Python 3.11+.

## Register it with your MCP client

**Claude Code:**

```bash
claude mcp add porymap -- uvx --from "porymap-mcp[render]" porymap-mcp
```

**Claude Desktop** (`claude_desktop_config.json`) or any client that takes a JSON server list:

```json
{
  "mcpServers": {
    "porymap": {
      "command": "uvx",
      "args": ["--from", "porymap-mcp[render]", "porymap-mcp"]
    }
  }
}
```

If you installed with pip, use `"command": "porymap-mcp"` (or `"python"` with `"args": ["-m", "porymap_mcp"]`).

No environment variables are needed: the project path is passed on every tool call, so one server can work on several projects.

## First map in 5 minutes

With the server registered, ask your agent:

> *Open my pokeemerald project at `~/code/pokeemerald-expansion`. Create a 20×20 map called `LakesideTown` in the `gMapGroup_TownsAndRoutes` group, using `gTileset_General` + `gTileset_Petalburg`. Stamp a small house at (3, 4), put a sign next to its door that says "Welcome to Lakeside!", then render the map and critique it.*

The agent will typically:

1. Call `get_project_info` to confirm the project loads and read its config.
2. Call `list_tilesets` to check that both tilesets exist.
3. Call `create_map`, which writes `data/maps/LakesideTown/map.json`, `data/layouts/LakesideTown/map.bin` and `border.bin`, and registers the map in `data/layouts/layouts.json` and `data/maps/map_groups.json`.
4. Call `paint_prefab` with `house_small` at (3, 4): a 3×3 footprint with its door at (4, 6).
5. Call `add_sign` at (3, 7). This appends the event to `map.json` and generates a script stub (poryscript, or `.inc` if your project has `use_poryscript=0`).
6. Call `render_map` and look at the PNG it gets back.

Every write tool returns the list of files it modified. Open the project in Porymap, or rebuild your ROM: the map is there.

> **Tileset labels.** Littleroot Town, Oldale Town and Petalburg City all use `gTileset_General` + `gTileset_Petalburg`, in both vanilla `pokeemerald` and `pokeemerald-expansion`. There is no `gTileset_LittlerootTown`. If your fork renames or adds tilesets, ask the agent to call `list_tilesets` first and pick from what it returns.

## Tools

24 tools. Each tool's docstring is what your agent reads, and the full contracts are in the ADRs listed below. Every tool takes `project_path` as its first argument.

| Tool | Group | What it does |
|------|-------|--------------|
| `get_project_info` | Discovery | Project snapshot: base game, map, layout and tileset counts. |
| `list_maps` | Discovery | Every map registered in `map_groups.json`. |
| `get_map_info` | Discovery | Full metadata for one map: layout, tilesets, size, header. |
| `list_tilesets` | Discovery | Every primary and secondary tileset found on disk. |
| `list_metatiles` | Discovery | The metatiles of one tileset, with attributes. |
| `list_prefabs` | Discovery | Named multi-metatile stamps available to `paint_prefab`. |
| `list_events` | Discovery | Every event on a map, grouped by class. |
| `paint_metatile` | Mutation | Set one tile (metatile, collision, elevation). Idempotent. |
| `paint_rectangle` | Mutation | Fill an inclusive rectangle with one metatile. |
| `flood_fill` | Mutation | Replace a 4-connected region of identical metatiles. |
| `set_border` | Mutation | Replace the map's repeating border tiles. |
| `paint_prefab` | Mutation | Stamp a named prefab, top-left anchored. |
| `create_map` | Mutation | Create a new map: writes its files and registers it everywhere. |
| `resize_map` | Mutation | Resize a layout from its top-left corner, keeping the overlapping content. |
| `register_map` | Project | Add an existing map directory to `map_groups.json`. |
| `unregister_map` | Project | Remove a map from `map_groups.json` (files are kept). |
| `add_warp` | Events | Add a warp to another map. |
| `add_object_event` | Events | Add an NPC, item ball or other object event. |
| `add_sign` | Events | Add a sign with inline text and generate its script stub. |
| `add_trigger` | Events | Add a coordinate-based script trigger. |
| `remove_event` | Events | Remove any event by its id. |
| `render_map` | Render | Render a full map to PNG, optionally with its border frame. |
| `render_map_region` | Render | Render a rectangular slice of a large map. |
| `render_metatile` | Render | Preview a single metatile from a tileset. |

The three render tools accept `overlays` (`collision`, `elevation`, `grid`, `events`) and a `scale` factor. All seven map-mutation tools and all five event tools accept `return_render=True`, which adds the post-edit render to the same response and saves a round trip.

## Design records

Every decision that is hard to reverse is written up as an ADR in [`docs/decisions/`](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/README.md):

- [ADR-0001](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0001-fastmcp-as-mcp-framework.md): FastMCP as the MCP framework
- [ADR-0002](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0002-target-pokeemerald-expansion-first.md): pokeemerald-expansion as the primary target
- [ADR-0003](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0003-project-class-and-config-driven-format.md): a single `Project` entry point, config-driven formats
- [ADR-0004](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0004-tileset-metadata-source.md): where tileset metadata comes from
- [ADR-0005](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0005-l1-discovery-tools-api.md), [ADR-0006](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0006-l1-mutation-tools-api.md), [ADR-0007](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0007-l1-event-tools-api.md): discovery, mutation and event tool contracts
- [ADR-0008](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0008-prefab-library-and-paint-prefab.md): prefab library and `paint_prefab`
- [ADR-0009](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0009-abandon-l2-live-porymap.md): why live Porymap hot-reload was dropped
- [ADR-0010](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0010-l3-renderer-design.md): renderer design, including the four corrections found while validating against Porymap

The project's vision document is [`MCP_PORYMAP.md`](https://github.com/hugomrts/porymap-mcp/blob/main/MCP_PORYMAP.md) (in French).

## Prefabs

`paint_prefab` ships with three stamps: `single_tree`, `flower_patch` and `house_small`. Their metatile IDs follow vanilla `gTileset_General` conventions. If your fork uses custom tilesets, register your own prefabs in `porymap_mcp.prefabs.LIBRARY` (a plain dict). See [ADR-0008](https://github.com/hugomrts/porymap-mcp/blob/main/docs/decisions/0008-prefab-library-and-paint-prefab.md).

## Develop

```bash
git clone https://github.com/hugomrts/porymap-mcp
cd porymap-mcp
uv sync --all-extras        # or: pip install -e ".[dev]"
pre-commit install
pytest
```

CI blocks on `ruff check`, `ruff format --check`, `mypy --strict` and the full test suite (Linux and macOS, Python 3.11 to 3.13). [`CLAUDE.md`](https://github.com/hugomrts/porymap-mcp/blob/main/CLAUDE.md) describes the conventions used to develop this repo with Claude Code, including the sub-agents in [`.claude/agents/`](https://github.com/hugomrts/porymap-mcp/tree/main/.claude/agents), which anyone can reuse.

## Acknowledgements

- [Porymap](https://github.com/huderlem/porymap) by Marcus Huderle: the editor whose files this server writes.
- [pret](https://github.com/pret): the decompilation projects that make all of this possible.
- [rh-hideout](https://github.com/rh-hideout): the `pokeemerald-expansion` fork.
- [FastMCP](https://github.com/jlowin/fastmcp): the Python MCP framework used here.

## License

[MIT](https://github.com/hugomrts/porymap-mcp/blob/main/LICENSE)
