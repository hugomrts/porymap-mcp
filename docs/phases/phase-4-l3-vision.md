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

### 2026-05-14 — `tools/rendering.py` shipped (end-to-end render wiring)

Implementation slice 6 — the slice that finally consumes `compose` +
`layout` + `encode` end-to-end. New module
`src/porymap_mcp/tools/rendering.py` registers three FastMCP tools via
`register(mcp)`:

- `render_map(project_path, map_name, *, overlays=[], include_border=False, scale=1)`
- `render_map_region(project_path, map_name, x1, y1, x2, y2, *, overlays=[], scale=1)`
- `render_metatile(project_path, tileset_name, metatile_id, *, scale=4)`

All three return a `ToolResult` packaged via `package_render_result` — an
`ImageContent` PNG block plus a `structured_content` dict carrying the
canonical L1 fields (`summary`, `project_path`, `map_name`/`layout_id`,
`dimensions`, `pixel_dimensions`, `scale`, `encoding`, `byte_size`,
`tilesets`, plus tool-specific keys like `region` and
`companion_tileset`).

**Pipeline.** For each call: load `Project` → resolve the
primary/secondary `TilesetEntry` pair via `get_tileset_by_label` →
decode banks (`tile_bank: uint8[1024, 8, 8]`, `palette_bank:
uint8[13, 16, 4]`, `metatile_bank: uint8[N, 16, 16, 4]` where `N` is
`512 + secondary_metatile_count`) → `layout.assemble` or
`layout.assemble_region` → `_scale_nearest` (numpy `repeat`, clamped to
1..8) → `encode_png` (palette-vs-RGBA selection per ADR-0010) →
`package_render_result`. Primary is padded to slot 512 with zero
metatiles so secondary metatiles always land at index 512 even when the
primary tileset declares fewer metatiles.

**Numpy/Pillow imports are deferred inside each tool body.** Importing
`porymap_mcp.tools.rendering` requires only the base dependencies; only
invoking a tool requires the `render` extra. `server.build_server()`
imports `rendering` at construction time, which is fine because the
module top-level only references types under `TYPE_CHECKING`.

**Hard-coded vanilla slot counts** live as module constants
(`NUM_TILES_PRIMARY=512`, `NUM_METATILES_PRIMARY=512`,
`NUM_TILES_TOTAL=NUM_METATILES_TOTAL=1024`, `NUM_PALETTES_PRIMARY=6`,
`NUM_PALETTES_TOTAL=13`). These mirror Porymap's defaults; a future ADR
can surface them on `ProjectConfig` once a fork legitimately overrides
one.

**Out of scope for this slice (deferred to follow-ups):**

- Overlays (`collision` / `elevation` / `grid` / `events`) raise an
  explicit `ProjectError("overlays not yet implemented in this build")`
  — provides a clear extension point for `render/overlays.py`.
- `include_border=True` raises an explicit `ProjectError("include_border
  =True not yet implemented in this build")` — extension point for the
  border-framing helper.

These raises are tested so the next slice can land the implementations
behind the same parameter shape without breaking callers.

**+31 unit tests** under `tests/unit/tools/test_rendering.py` (suite:
401 → **432 passing**). The test file builds a complete synthetic
project under `tmp_path` — primary + secondary tilesets each with 13
`.pal` files, a 3x2 `map.bin` whose cells reference metatiles 0 (primary
palette 0), 1 (primary metatile that references palette 6, i.e. a
secondary palette slot), and 512 (secondary's metatile 0). Tests cover:

- **Pixel content of the full render** — every metatile cell's centre
  pixel asserted against the expected `(R, G, B, A)`.
- **Structured-content metadata** — every field asserted, including
  `tilesets`, `pixel_dimensions`, `encoding`, `byte_size`.
- **Nearest-neighbor scale invariant** — every 4x4 block in the
  `scale=4` render equals the matching 1x1 pixel in the `scale=1` render.
- **Region rendering** — pixel-content + `region`/`dimensions`/
  `pixel_dimensions` metadata + 6 parametrized invalid-bounds cases.
- **`render_metatile`** — primary + secondary metatile rendering, the
  default `scale=4` -> 64x64 image, companion-tileset pairing fields,
  out-of-range metatile_id, metatile-id-not-in-bank, invalid scale,
  missing-companion-tileset (project with only primaries).
- **Error contract** — overlays + include_border explicit raises, scale
  bounds (parametrized × 4), missing palette file -> `PaletteFormatError`,
  layout with swapped primary/secondary kinds -> `ProjectError`.
- **Registration smoke** — `build_server()` exposes the three render
  tools alongside the 21 L1 tools (= 24 total).

`ruff check .` + `ruff format --check .` + `mypy --strict src/porymap_mcp`
(28 source files) + `pytest --no-cov` all clean.

Notes for the next slice:

- The border-framing helper can be added inside `layout.py` and wired
  through `tools/rendering.py` by replacing the `_check_include_border_supported`
  raise with the actual composition. The map's border `MapBin` is already
  reachable via `project.read_border_bin(layout_id)`.
- The overlay slice can plug into `tools/rendering.py` by replacing the
  `_check_overlays_supported` raise with an overlay dispatch. The
  assembled RGBA buffer is available before encoding; pass it (and the
  L1 `MapBin` / `MapJson` for collision-elevation-events data) to
  `render/overlays.py`. Remember to force `encode_png(..., force_rgba=True)`
  because overlays produce non-opaque pixels.

### 2026-05-14 — `render/encode.py` shipped (PNG encode + ToolResult packaging)

Implementation slice 5. Added `src/porymap_mcp/render/encode.py`:

- `encode_png(rgba, *, area_metatiles, force_rgba=False) -> (bytes, EncodingName)` — selects palette-vs-RGBA per ADR-0010 §"PNG encoding": palette mode iff `not force_rgba` AND `area_metatiles <= 4096` AND the image is fully opaque AND has ≤ 256 distinct RGB values. Falls back to RGBA cleanly on any of those conditions. `optimize=True` only when `area_metatiles <= 4096`.
- Palette-mode encode is **lossless** by construction: `np.unique` over packed RGB → indexed image + custom palette. No Pillow quantization, no dithering. Verified by round-trip pytest assertions.
- `package_render_result(png_bytes, *, summary, extra=None) -> ToolResult` — wraps PNG bytes into the canonical `ToolResult(content=[Image(data=, format="png").to_image_content()], structured_content={...})` shape from ADR-0010 §"MCP return shape". FastMCP types are late-imported inside the function to keep `porymap_mcp.render` import-time free of FastMCP. `summary` from the kwarg always wins over `extra["summary"]`.

New error class `PngEncodeError` for the validation surface (wrong shape/dtype, zero dim, negative area).

**+18 unit tests** under `tests/unit/render/test_encode.py` (suite: 383 → **401 passing**). Coverage:

- Mode selection: small opaque → palette; `force_rgba=True` → RGBA; `area > 4096` → RGBA; `area == 4096` (exactly at threshold) → palette; >256 colours → RGBA; any non-opaque pixel → RGBA.
- Round-trip lossless: palette path (3 colour blocks), RGBA path (>256 colours), solid-image palette, forced-RGBA.
- Validation: wrong shape, 2D input, wrong dtype, zero dim, negative area.
- `package_render_result`: returns `ToolResult` with `ImageContent` + `image/png` mime + base64 data that round-trips as PNG; `summary` kwarg overrides `extra["summary"]`; `extra=None` accepted.

`ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` (27 source files) + `pytest --no-cov` all clean.

### 2026-05-14 — `render/layout.py` shipped (assembly slice)

Implementation slice 4. Added `src/porymap_mcp/render/layout.py`:

- `assemble(metatile_bank, metatile_grid) -> uint8[H*16, W*16, 4]` — pure-numpy paste. Single fancy-index over the flattened grid, then `reshape(H, W, 16, 16, 4).transpose(0, 2, 1, 3, 4).reshape(H*16, W*16, 4).copy()` interleaves the W and tile-pixel axes so adjacent metatiles end up adjacent in the output buffer. C-contiguous output for downstream Pillow encode.
- `assemble_region(bank, grid, *, x1, y1, x2, y2)` — strict half-open slice in metatile units. Raises on degenerate/out-of-grid bounds.
- `clip_region(grid_shape, x1, y1, x2, y2) -> (cx1, cy1, cx2, cy2)` — clamps a requested region to a grid's bounds; raises only when the clip collapses to empty (= caller asked for somewhere fully outside the grid). The tool layer composes `clip_region` + `assemble_region` when "render whatever fits" is the desired semantics.
- `mapbin_to_metatile_grid(mb: MapBin) -> uint16[H, W]` — adapter that drops the per-tile collision/elevation fields; the full :class:`MapBin` stays available to overlay renderers.

New error class `LayoutAssemblyError` (precondition failures: bank shape/dtype, grid shape/dtype, out-of-range IDs, region bounds).

**+32 unit tests** under `tests/unit/render/test_layout.py` (suite: 351 → **383 passing**). Coverage:

- `assemble`: single-cell grid, 2x3 grid pixel-by-pixel (origin top-left), metatile repetition, within-tile pixel order preserved (asymmetric metatile), C-contiguous output, accepts int32/int64/uint8/uint16 grid dtypes.
- Validation: out-of-range ID, negative ID, non-integer dtype, 1D grid, empty grid, wrong bank shape/dtype, empty bank.
- `assemble_region`: subgrid extraction, full-region equality with `assemble`, 1-cell region, 6 parametrized invalid-bounds cases (zero-width, zero-height, reversed bounds, negatives, beyond width, beyond height).
- `clip_region`: in-bounds passthrough, right/bottom overrun, left/top underflow, full-engulf, fully-outside (left + bottom), degenerate input.
- `mapbin_to_metatile_grid`: extracts metatile_id and drops collision/elevation; round-trip to `assemble`.

`ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp` + `pytest --no-cov` all clean.

Notes for the next slice:

- **Border framing is NOT in this slice.** The `assemble`/`assemble_region` primitives already render a `border.bin` (it's a small `MapBin`), but the *tiling* that wraps a map with its border (Porymap's "include border" exporter mode) requires a small composition step — defer until `tools/rendering.py` actually wires `include_border=True`. ADR-0010 §"Layout assembly" says border follows the same pipeline; that's correct for rendering the 2x2 grid itself but not for the wrap-around frame.
- **Performance.** The fancy-index + reshape path is a single C-level copy; bench should be sub-millisecond for 30x20 even on cold cache. Will measure once `tools/rendering.py` is in place.

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
