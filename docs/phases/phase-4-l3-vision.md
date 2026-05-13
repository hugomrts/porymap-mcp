# Phase 4 — L3: Vision (rendering + self-critique loop)

> **Status:** Not started (blocked on Phase 3 ship)
> **Estimated effort:** 3–5 days
> **Closes when:** the agent can paint a map, see a PNG of its output in the tool response, run it through the design critic, apply fixes, and converge on a quality result — all in a single conversation.

---

## 1. Goal

Close the feedback loop. After L1 and L2, the agent edits the project but is *blind* to the visual result. L3 makes the agent see:

1. **Render**: the MCP server composes the tilesets + layout into a PNG.
2. **Return**: the PNG comes back in the tool response as a native MCP `image` content block.
3. **Self-critique**: the agent (or the user explicitly) invokes the `map-design-critic` sub-agent, which scores the render against the 12-criterion rubric.
4. **Iterate**: the agent applies the critic's top fixes and re-renders.

This is the **reason the project exists in its final form**. Without L3, Claude is just a fast typist on map files. With L3, Claude is a junior mapper that improves with each iteration.

---

## 2. Exit criteria

- [ ] `render_map(project_path, map_name)` returns a PNG that pixel-matches Porymap's export (0 pixel diff on default config)
- [ ] `render_map_region(...)` works for partial renders (big maps)
- [ ] Optional overlays implemented: `collision`, `elevation`, `events`, `grid`
- [ ] All L1 mutation tools gain `return_render: bool = False` parameter
- [ ] Render performance hits the targets in `.claude/agents/map-renderer.md` §"Performance targets"
- [ ] Golden PNG tests in CI (`tests/fixtures/renders/`)
- [ ] **End-to-end self-critique loop demonstrated** in `examples/04_render_loop/`:
  - Agent generates a town from a one-line brief
  - Agent calls `render_map`
  - Agent invokes `map-design-critic`
  - Agent applies the top 3 fixes
  - Agent re-renders, score improves measurably
- [ ] Tagged `v1.0.0` (first stable)

---

## 3. Renderer architecture

Owned by the `map-renderer` agent. See [`../../.claude/agents/map-renderer.md`](../../.claude/agents/map-renderer.md) for design rules.

Pipeline:

```
parsers → Tileset(tiles, palettes, metatiles, attributes)
       → MapLayout(metatile_grid, collision_grid, elevation_grid)
                       │
                       ▼
       Renderer (Pillow)
       ├── decode_tile(tile_id, palette) → Image 8×8 RGBA   (cached)
       ├── compose_metatile(metatile_id) → Image 16×16 RGBA (cached)
       ├── assemble_layout(layout)       → Image W×H RGBA
       ├── apply_overlay(...)            → modifies in place
       └── encode_png(image)             → bytes
```

Modules:

```
src/porymap_mcp/render/
├── __init__.py
├── tile.py          # decode_tile, palette application
├── metatile.py      # compose_metatile
├── layout.py        # assemble_layout, regions, border
├── overlays.py      # collision, elevation, events, grid
├── encode.py        # PNG encoding, optimization
└── cache.py         # in-call caches (no cross-call state)
```

---

## 4. Tool surface additions

| Tool | Signature | Notes |
|------|-----------|-------|
| `render_map` | `(project_path, map_name, *, overlays=[], include_border=False, scale=1)` | Returns MCP `image` content. |
| `render_map_region` | `(project_path, map_name, x1, y1, x2, y2, *, overlays=[], scale=1)` | Partial render. Same return shape. |
| `render_metatile` | `(project_path, tileset_name, metatile_id, *, scale=4)` | Single metatile preview. Useful for `list_metatiles` follow-up. |

All L1/L2 mutation tools gain `return_render: bool = False`. When `True`, the response includes a render of the affected map. Default `False` to keep responses small.

---

## 5. Self-critique loop (the user-visible behavior)

This is what the user actually experiences. From `CLAUDE.md`:

> Any map-generation task that doesn't close this loop is incomplete.

Concretely, when the user asks "make me a small coastal town", a well-behaved Claude session:

1. Calls `create_map` + paints the town (L1 tools).
2. Calls `render_map(return_render=True)` *or* uses the inline render from the mutation tools.
3. Spawns the `map-design-critic` agent with the render + the user's brief.
4. Reads the critic's prioritized fix list.
5. Applies the top 2–3 fixes (high-gain, low-effort first).
6. Re-renders, re-critiques.
7. Stops when score ≥ 30/36 or the user signals they're satisfied.

The loop converges in 2–4 iterations on simple maps. The critic agent is the convergence signal.

---

## 6. Performance

The renderer must be cheap because the loop calls it 2–4× per generation. Targets (from `map-renderer.md`):

- 30×20 map, no overlays: < 100 ms
- 30×20 map, all overlays: < 200 ms
- 60×120 map, no overlays: < 1 s
- PNG output for 30×20: < 100 KB

If we miss these, the loop feels slow. Profile early.

---

## 7. Visual fidelity verification

Acceptance test: byte-identical to Porymap's export for a corpus of 5 reference maps:

1. A vanilla pokeemerald town (Littleroot Town)
2. A vanilla pokeemerald route (Route 101)
3. A vanilla pokeemerald cave (Granite Cave 1F)
4. An expansion-specific map showcasing layered metatiles
5. A handcrafted edge case (max-size, border edge, multiple elevations)

These live under `tests/fixtures/renders/`. CI fails on any pixel diff.

---

## 8. Open questions

- **OQ1**: Native `image` content support varies across MCP clients. What's the fallback? Probably: emit the image, *also* include a `render_url: file://...` field for clients that don't render inline.
- **OQ2**: Animated/seasonal tilesets in expansion (e.g. flowers that animate in-game). Render the first frame? All frames? Default: first frame, document.
- **OQ3**: Map connections — show the neighboring map's edge tiles bleeding into the render, or just our map? Porymap shows neighbors at low opacity. Match it.

---

## 9. Session log

*(empty — phase not started)*

---

## 10. References

- Phase 3: [`phase-3-l2-live-porymap.md`](phase-3-l2-live-porymap.md)
- Phase 5 (next): [`phase-5-release.md`](phase-5-release.md)
- Renderer agent: [`../../.claude/agents/map-renderer.md`](../../.claude/agents/map-renderer.md)
- Critic agent: [`../../.claude/agents/map-design-critic.md`](../../.claude/agents/map-design-critic.md)
