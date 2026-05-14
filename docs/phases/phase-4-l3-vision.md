# Phase 4 — L3: Vision (rendering + self-critique loop)

> **Status:** Active (phase 3 abandoned per [ADR-0009](../decisions/0009-abandon-l2-live-porymap.md); this is the immediate next phase)
> **Estimated effort:** 3–5 days
> **Target version:** `v1.0.0` (first stable). `v0.2.0` is intentionally skipped; the roadmap goes `v0.1.0` (L1, shipped) → `v1.0.0` (L3).
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

- [ ] `render_map(project_path, map_name)` returns a PNG that **pixel-matches** (decoded RGBA arrays equal, see ADR-0010 §Fidelity) Porymap's export with default flags + "show connections = off"
- [ ] `render_map_region(...)` works for partial renders (big maps)
- [ ] Optional overlays implemented: `collision`, `elevation`, `events`, `grid`
- [ ] All L1 mutation tools gain `return_render: bool = False` parameter
- [ ] Render performance hits the targets in `.claude/agents/map-renderer.md` §"Performance targets"
- [ ] Golden pixel tests in CI (`tests/fixtures/renders/` stores both our PNG and the Porymap reference PNG; CI decodes both to RGBA and asserts `np.array_equal`)
- [ ] **End-to-end self-critique loop demonstrated** in `examples/04_render_loop/`:
  - Agent generates a town from a one-line brief
  - Agent calls `render_map`
  - Agent invokes `map-design-critic`
  - Agent applies the top 3 fixes
  - Agent re-renders, score improves measurably
- [ ] Tagged `v1.0.0` (first stable)

---

## 3. Renderer architecture

Owned by the `map-renderer` agent. See [`../../.claude/agents/map-renderer.md`](../../.claude/agents/map-renderer.md) for design rules. **Design locked in [ADR-0010](../decisions/0010-l3-renderer-design.md).**

Stack: **`numpy` + `Pillow`**, both behind the `render` optional extra in `pyproject.toml`. Numpy carries the decode and compose hot path (vectorized palette indexing, layer alpha masking); Pillow handles indexed PNG decode at load time, `ImageDraw` for overlays, and the final PNG encode.

Source files read (per tileset pair, primary + secondary):

- `data/tilesets/<group>/<name>/tiles.png` — indexed PNG, masked `& 0x0F` (4-bpp).
- `data/tilesets/<group>/<name>/palettes/{00..12}.pal` — JASC-PAL text. RGB masked `& 0xF8` (GBA 5-bit hardware quantization). Index 0 of each palette is transparent for upper layers.
- `porymap.project.cfg` — `transparency_color`, `unused_tile_{normal,covered,split}`, `enable_triple_layer_metatiles`, attribute mask overrides. Read via an extended `ProjectConfig` parser.

Pipeline:

```
parsers → TileBank      uint8[num_tiles, 8, 8]            (palette indices)
       → PaletteBank   uint8[num_palettes, 16, 4]         (RGBA, GBA-quantized)
       → MetatileBank  uint8[num_metatiles, 16, 16, 4]    (composed once per call)
                       │
                       ▼
       Layout assembly (numpy advanced indexing)
       → layout_rgba   uint8[H*16, W*16, 4]
                       │
                       ▼
       Overlays (Pillow ImageDraw) → encode (Pillow PNG) → ToolResult(Image(...))
```

Composition rule: every metatile is rendered as **3 stacked layers**. In triple-layer mode all 3 come from the file (24-byte metatile). In dual-layer mode (16-byte metatile), one layer is filled from `unused_tile_{normal,covered,split}` per the metatile's `LayerType` — see ADR-0010's composition table for the exact mapping.

Modules:

```
src/porymap_mcp/render/
├── __init__.py
├── compose.py        # decode tiles + palettes + metatiles, build MetatileBank
├── layout.py         # assemble_layout, regions, border
├── overlays.py       # collision, elevation, events, grid
├── encode.py         # PNG encoding (palette vs RGBA), MCP ToolResult packaging
├── cache.py          # in-call caches (no cross-call state)
└── assets/
    └── icons/        # 12×12 RGBA PNGs: warp, object, sign, trigger, heal
```

`compose.py` replaces the earlier `tile.py` + `metatile.py` sketch — they share the tile/palette/metatile bank state and splitting them forces awkward parameter passing for combined ~150 LOC.

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

Acceptance test: **pixel-identical decoded RGBA** vs Porymap's export for a corpus of 5 reference maps. See [ADR-0010 §Fidelity](../decisions/0010-l3-renderer-design.md) — byte-identical PNG is **not** required (Pillow and Qt produce different but valid containers for identical pixels).

Reference corpus:

1. A vanilla pokeemerald town (Littleroot Town)
2. A vanilla pokeemerald route (Route 101)
3. A vanilla pokeemerald cave (Granite Cave 1F)
4. An expansion-specific map showcasing layered metatiles
5. A handcrafted edge case (max-size, border edge, multiple elevations)

Each Porymap reference PNG is produced via **File → Export Map Image** with: scale 1×, **show connections = off**, no overlays, include border per the test case. v1.0 explicitly does not render connections; see ADR-0010 §Alternatives considered #5.

Goldens live under `tests/fixtures/renders/`. CI loads both PNGs, converts each to RGBA via Pillow, and asserts `np.array_equal`. Regeneration uses the pytest `--update-golden` flag.

---

## 8. Open questions

- **OQ1**: Native `image` content support varies across MCP clients. What's the fallback? Probably: emit the image, *also* include a `render_url: file://...` field for clients that don't render inline.
- ~~**OQ2**~~: **Resolved by ADR-0010.** Animations: render the first frame only — it's already baked into `tiles.png` by construction (animated frames live in separate runtime-only files Porymap doesn't display). No work required for v1.0.
- ~~**OQ3**~~: **Resolved by ADR-0010.** Map connections: not rendered in v1.0. Reference Porymap exports use "show connections = off". Future v1.1 may add `include_connections: bool = False`; deferred to a future ADR.

---

## 9. Session log

### 2026-05-14 — `compose.decode_metatile_bank` shipped (compose slice 2)

Implementation slice 3 from the previous handoff. Added the metatile composer
to `src/porymap_mcp/render/compose.py`:

- `decode_metatile_bank(metatiles_bytes, attributes, tile_bank, palette_bank, *, layers, unused_tile_normal, unused_tile_covered, unused_tile_split, transparency_color)` returning `uint8[num_metatiles, 16, 16, 4]`.
- Always composes 3 stacked layers per ADR-0010 §"Metatile composition": triple-layer mode reads all three from disk; dual-layer mode fills the missing layer from `unused_tile_*` based on the metatile's `LayerType` (Normal → bottom, Covered → top, Split → middle). Unknown `layer_type` values fall back to Normal — matches Porymap's switch-default in `src/ui/imageproviders.cpp`.
- Tile entries unpack as `tile_id`=bits 0-9, `xflip`=bit 10, `yflip`=bit 11, `palette_num`=bits 12-15; xflip/yflip applied via numpy slice reversal.
- Bottom-layer transparency: canvas pre-filled with `transparency_color` (GBA-quantized via `& 0xF8`) when set, else `palette[0][0]` RGB with alpha 255. Upper-layer palette-0 pixels stay alpha-0 from `decode_palette_bank`, so the background shows through correctly.
- Out-of-range `tile_id` or `palette_num` are silently skipped — matches Porymap's behaviour when a metatile references a slot the loaded tilesets don't supply.
- New error class: `MetatilesBinFormatError` (size not a multiple of 8×layers bytes, attribute-count mismatch, invalid `layers`).

WebFetch'd Porymap's `imageproviders.cpp getMetatileImage()` to confirm: unused tiles render with palette 0 and no flips (bare `Tile(id)` ctor defaults); transparency_color falls back to palette 0 colour 0 when unset; index-0 alpha-zero is applied per tile.

**+21 unit tests** under `tests/unit/render/test_compose.py` (total now 43 in this file, 351 in the suite). Coverage: each `LayerType` branch, triple-layer mode ignores `layer_type`, xflip + yflip + both, transparency_color set + quantized + fallback, layer z-order (top overrides bottom), 2×2 quad position mapping, all four validation paths, out-of-range tile/palette skipping, multiple-metatile decoding.

`ruff check .` + `ruff format --check .` + `mypy --strict src/porymap_mcp` + `pytest --no-cov` all clean.

**Next up** (unchanged from STATUS handoff): `render/layout.py` (W×H numpy assembly + border) → `render/encode.py` (palette-vs-RGBA + FastMCP `ToolResult` packaging) → `tools/rendering.py` registering `render_map`/`render_map_region`/`render_metatile` → `render/overlays.py` + bundled icons → `return_render` on L1 mutation tools → 5-map fidelity corpus → `examples/04_render_loop/` → `v1.0.0` tag.

### 2026-05-13 — Phase 4 opened, design locked in ADR-0010

Per the L2-abandonment session (see Phase 3 session log + ADR-0009), the project pivoted directly to L3. This session ran two parallel static-source audits to populate ADR-0010:

1. **Decode-pipeline audit** (`porymap-format-expert`) — established exactly what Porymap reads (`tiles.png` + JASC `.pal`, never the compiled `.4bpp` / `.gbapal`), how metatiles compose (always 3 layers; in dual-layer mode the missing layer is filled from `unused_tile_{normal,covered,split}` config keys, selected by `LayerType`), how `metatile_attributes.bin` differs between RSE (2-byte) and FRLG/expansion (4-byte) layouts (the L1 parser already handles this), and that Porymap's PNG export is **RGBA-8888 via Qt's libpng**, scale 1×, no color profile.
2. **Renderer-design audit** (`map-renderer`) — recommended **numpy + Pillow** over pure Pillow (the latter cannot comfortably meet the 60×120 < 1 s target due to per-paste Python overhead; estimated 0.3–1.5 s vs budget). Confirmed the FastMCP image-content return shape (`ToolResult` + `Image(data=, format="png")` + `structured_content`). Established that **byte-identical PNG between Pillow and Qt is impossible** — recommended downgrading the fidelity criterion to *pixel-identical decoded RGBA*, which gives the same correctness signal for the agent's consumption.

Findings landed in [ADR-0010](../decisions/0010-l3-renderer-design.md). Updates to this doc reflect the locked design: §3 module layout adjusted (`tile.py` + `metatile.py` merged into `compose.py`; new `assets/icons/` directory for overlay icons); §7 fidelity criterion downgraded from "byte-identical" to "pixel-identical"; §8 OQ2 (animations) and OQ3 (connections) resolved.

Critical implementation notes worth surfacing for the next session:

- **GBA 5-bit palette quantization** (`c & 0xF8` on each RGB component during palette decode) is mandatory. Porymap's exported pixels reflect GBA hardware truncation, and missing this masking will fail the fidelity test on every map.
- **`porymap.project.cfg` is now in scope for L3** — the `ProjectConfig` parser must gain `unused_tile_{normal,covered,split}`, `transparency_color`, `enable_triple_layer_metatiles`, and the attribute mask overrides. Add these to `parsers/projectconfig.py` before any render code lands.
- **No connections in v1.0.** Reference Porymap exports for the fidelity corpus must be produced with "show connections = off". Document this clearly when goldens are generated.
- **Implementation order** (matches phase doc §3 module list): extend `ProjectConfig` → `compose.py` (tile + palette + metatile bank) → `layout.py` (W×H assembly + border) → `encode.py` (palette-vs-RGBA selection + MCP `ToolResult` packaging) → wire `render_map`, `render_map_region`, `render_metatile` as tools → `overlays.py` → add `return_render` to L1 mutations → assemble the 5-map fidelity corpus → `examples/04_render_loop/`.

Audits not committed to repo (they were tool-call transcripts), but every claim in ADR-0010 cites the underlying Porymap source file:line and external doc URLs.

---

## 10. References

- Phase 3: [`phase-3-l2-live-porymap.md`](phase-3-l2-live-porymap.md)
- Phase 5 (next): [`phase-5-release.md`](phase-5-release.md)
- Renderer agent: [`../../.claude/agents/map-renderer.md`](../../.claude/agents/map-renderer.md)
- Critic agent: [`../../.claude/agents/map-design-critic.md`](../../.claude/agents/map-design-critic.md)
