# ADR-0010: L3 renderer — decode pipeline, image stack, and fidelity criterion

- **Status:** Accepted (with 2026-05-14 corrections from corpus validation — see §"Empirical corrections")
- **Date:** 2026-05-13 (initial), 2026-05-14 (addendum after corpus validation)
- **Deciders:** project owner

---

## Context

Phase 4 (L3 — Vision) is now active per [ADR-0009](0009-abandon-l2-live-porymap.md). Its core deliverable is `render_map`: an MCP tool that turns a pokeemerald-family map (Gen-3 GBA, 16×16-pixel metatiles, 4-bpp indexed tiles, GBA palettes) into a PNG returned as an MCP `image` content block. The agent then sees its own work and runs it through `map-design-critic`, closing the `paint → render → critique → fix` loop.

Two static-source audits informed this ADR (see Phase 4 session log for full transcripts):

1. **Decode-pipeline audit** of Porymap master (`huderlem/porymap`) — established what Porymap actually reads from disk, in what order, with what masks, and what its export PNG format is.
2. **Renderer-design audit** — weighed Python image stacks (Pillow, numpy+Pillow, Cairo, Skia), cache strategies, FastMCP return shapes, and the byte-identity question.

Several findings reshape the phase doc's draft design:

- Porymap reads the **artist-edited source files** (`tiles.png`, JASC-PAL `.pal`), not the compiled GBA assets (`.4bpp` / `.gbapal`). We follow suit.
- Layer composition is **always 3 layers**, even in dual-layer mode. The "missing" layer in dual-layer is filled at render time from configurable `unused_tile_{normal,covered,split}` IDs read from `porymap.project.cfg`. The metatile's `LayerType` (already parsed by L1) selects which of the three layers is the missing one. Phase-4 §3's "compose all 8 tiles" sketch was incomplete.
- Porymap exports **RGBA 8888 PNG via Qt's libpng**. Pillow uses a different deflate tuning and chunk set. **Byte-identical PNG output is not achievable** without forking Pillow's encoder; the renderer can match Porymap on the pixels but not the file bytes.
- pokeemerald-expansion (and any project setting `enable_triple_layer_metatiles=1`) uses **24-byte metatiles** with three real layers from disk. Auto-detected from `metatiles.bin` size during L1 parse.
- **GBA hardware quantizes RGB to 5 bits per channel.** Porymap's exported pixels reflect that. The renderer must mask palette RGB with `& 0xF8` or pixel diffs will fail on every map.
- **Animations**: the static frame in `tiles.png` *is* "frame 0". No special handling needed for v1.0.
- **Connections**: Porymap's exporter composites neighbor strips by default. Including them recursively expands the fidelity surface (each connection drags its neighbor's tileset + layout into the test). v1.0 scopes them out; reference exports are produced with "show connections = off" in Porymap's dialog.

This ADR locks the design before any code lands under `src/porymap_mcp/render/`.

---

## Decision

### Image stack

`numpy` and `Pillow`, both added to `[project.optional-dependencies].render` in `pyproject.toml`. Numpy carries the decode and compose hot path; Pillow handles indexed PNG decode at load time, `ImageDraw` for overlays, and final PNG encode. No global state — every `render_map` call constructs its caches and discards them on return.

The renderer is gated behind the `render` extra: `pip install porymap-mcp[render]`. Importing `porymap_mcp.render` without numpy/Pillow installed raises a clean error from the tool layer; L1 mutation tools remain usable without the extra.

### Source files read

The renderer reads from disk:

1. `data/tilesets/<group>/<name>/tiles.png` (per tileset, primary + secondary). Indexed PNG, treated as 4-bpp by masking `& 0x0F` after `Image.open(...).convert("P")` and `np.array(...)`. Tiles are sliced row-major as 8×8 blocks; width must be a multiple of 8, height a multiple of 8 (otherwise: clean parse error). The PNG width is **convention**, not constraint — we don't assume 128 px.
2. `data/tilesets/<group>/<name>/palettes/{00..12}.pal` (per tileset). JASC-PAL text format only. Primary tileset owns palettes 0–5 (6 palettes), secondary owns 6–12 (7 palettes), 16 colors per palette. **Each RGB component is masked `& 0xF8`** to match GBA 5-bit hardware quantization. Palette index 0 of each palette has its alpha set to 0 (transparent for upper layers) unless `transparency_color` overrides it.
3. `porymap.project.cfg` for the project-config keys that affect rendering: `transparency_color`, `unused_tile_normal`, `unused_tile_covered`, `unused_tile_split`, `enable_triple_layer_metatiles`, plus any of the metatile-attribute mask overrides (`metatile_layer_type_mask`, etc.). The L1 `ProjectConfig` parser already reads this file; L3 extends it with the new keys (no parser duplication).
4. **No new format introduced.** `.gbapal`, `.4bpp`, and `.lz` are explicitly out of scope. A project that ships only compiled assets is rejected with a clear error; Porymap itself rejects it identically.

`metatiles.bin`, `metatile_attributes.bin`, `map.bin`, `border.bin`, and the JSON index files are already parsed by L1 and reused as-is.

### Metatile composition

A metatile is **always rendered as 3 stacked 16×16 RGBA layers**, composited bottom-to-top with palette-index-0 alpha. The source of each layer depends on whether the project uses dual-layer (16-byte) or triple-layer (24-byte) metatiles:

| Project mode | Layer 0 (bottom) | Layer 1 (middle) | Layer 2 (top) |
|---|---|---|---|
| Triple-layer (`enable_triple_layer_metatiles=1`) | from file (tiles 0–3) | from file (tiles 4–7) | from file (tiles 8–11) |
| Dual-layer + `LayerType::Normal` (0) | `unused_tile_normal` × 4 | from file (tiles 0–3) | from file (tiles 4–7) |
| Dual-layer + `LayerType::Covered` (1) | from file (tiles 0–3) | from file (tiles 4–7) | `unused_tile_covered` × 4 |
| Dual-layer + `LayerType::Split` (2) | from file (tiles 0–3) | `unused_tile_split` × 4 | from file (tiles 4–7) |

Each layer's 4 tiles tile a 2×2 grid in `(y * 2 + x)` order. Each tile entry's 2 bytes (little-endian) unpack as `tile_id = bits 0–9`, `xflip = bit 10`, `yflip = bit 11`, `palette_num = bits 12–15`. The L1 `Tile`/`Metatile` parser already exposes these fields; L3 consumes them unchanged.

### Cache

One per-call cache, dropped on return: `metatile_id -> np.ndarray[16, 16, 4] uint8`. Key by `metatile_id` only — palette and tile-id are baked into the metatile's own tile entries, so two visually different metatiles always have different IDs. `LayerType` is per-metatile (part of attributes), not a runtime variable, so it also folds into the metatile-id key.

Pre-decoded tile bank (`uint8[num_tiles, 8, 8]`, palette indices) and palette bank (`uint8[num_palettes, 16, 4]`, RGBA after GBA quantization and transparency masking) are call-scoped state as well.

### Layout assembly

Vectorized numpy: `layout_rgba[y*16:(y+1)*16, x*16:(x+1)*16] = metatile_bank[metatile_grid[y, x]]`. For a 30×20 map this is 600 indexed assignments, well inside the perf budget.

Border rendering follows the same pipeline. `include_border: bool = False` matches Porymap's exporter default.

### Connections

**Not rendered in v1.0.** Reference Porymap exports for the fidelity test corpus are produced with "show connections = off" in the Export Map Image dialog. v1.1 may add `include_connections: bool = False` if there's user demand; deferred to a future ADR.

### Overlays

Composited on top of the layout via Pillow `ImageDraw` (after one `np.ndarray → Image.fromarray` conversion). Each overlay layer is RGBA, so the output PNG mode switches from palette to RGBA whenever any overlay is requested.

- `collision`: translucent red tint (`(255, 0, 0, 100)`) on each cell where `collision != 0`.
- `elevation`: 1-px colored border per cell, color from a 16-entry LUT keyed by elevation value (definitive palette in `render/overlays.py`).
- `grid`: single-pixel 50%-gray lines along 16-px metatile boundaries.
- `events`: pre-rendered 12×12 PNG icons bundled at `src/porymap_mcp/render/assets/icons/{warp,object,sign,trigger,heal}.png`, alpha-composited at each event's `(x, y)`. Icons are package data, included via `pyproject.toml`'s build configuration.

### PNG encoding

Default: palette mode (`PIL` mode `"P"` with `tRNS` chunk) when no overlay is present and the map area is ≤ 4096 metatiles. This typically yields ≤ 60 KB for a 30×20 map, comfortably under the 100 KB target. For larger maps, fall back to RGBA. For any overlay-on render, always use RGBA (overlays require true alpha). `optimize=True` only when area ≤ 4096; above that the encode-time cost dominates and we drop it.

### MCP return shape

```python
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image

return ToolResult(
    content=[Image(data=png_bytes, format="png").to_image_content()],
    structured_content={
        "summary": "Rendered MAP_LITTLEROOT_TOWN (16×16 metatiles, 256×256 px).",
        "project_path": str(project_path),
        "map_name": map_name,
        "width_px": width_px,
        "height_px": height_px,
        "overlays": overlays_used,
        "include_border": include_border,
        "encoding": "png-palette-8" | "png-rgba-8",
        "render_ms": elapsed_ms,
    },
)
```

The `summary` field follows ADR-0006's convention. The `image` block is the **primary** content the agent consumes; the structured dict is metadata for logging and follow-up tool calls. `return_render: bool = False` on L1 mutation tools (per phase-4 §4) uses the same shape, downgraded to "structured only" when `False` (the default).

### Fidelity criterion (replaces phase-4 §7's "byte-identical")

For each of the 5 reference maps in the fidelity corpus, decoding our renderer's PNG and decoding Porymap's exported PNG must yield **the same RGBA pixel array** — zero differing pixels. The PNG container bytes are explicitly **not** required to match. Pillow's libpng wrapper and Qt's libpng wrapper produce different but valid PNG containers for identical pixels; chasing byte parity would require a custom encoder for no user-visible benefit.

Test implementation (informational; details belong to test plan):

```python
ours = np.array(Image.open(our_render_bytes).convert("RGBA"))
ref  = np.array(Image.open(porymap_export_path).convert("RGBA"))
assert ours.shape == ref.shape
assert np.array_equal(ours, ref)
```

The 5 reference maps are produced from Porymap with: scale 1×, show connections off, no overlays, include border according to the test case. Goldens live under `tests/fixtures/renders/`; regeneration uses the existing pytest convention (a `--update-golden` flag).

### Module structure (refines phase-4 §3)

```
src/porymap_mcp/render/
├── __init__.py
├── compose.py          # decode tiles + palettes + metatiles, build metatile bank (merges tile.py + metatile.py)
├── layout.py           # assemble W×H, regions, border
├── overlays.py         # collision, elevation, grid, events
├── encode.py           # PNG encode (palette vs RGBA, optimize threshold), MCP content packaging
├── cache.py            # per-call caches (no cross-call state)
└── assets/
    └── icons/          # warp, object, sign, trigger, heal — 12×12 RGBA PNG each
```

`compose.py` replaces the planned `tile.py` + `metatile.py`: they share the tile / palette / metatile banks and splitting forces awkward parameter passing for a combined ~150 LOC.

The `LayerType` enum and attribute-mask handling stay in `parsers/` (already shipped by L1) — `compose.py` consumes the already-decoded enum.

---

## Alternatives considered

### Alternative 1 — Pure Pillow (no numpy)
- **Upside:** One fewer dependency in the `render` extra.
- **Downside:** A 60×120 map demands ~7,200 metatiles × 4 tile pastes = ~29,000 `Image.paste(mask=...)` calls in the warmup path. Pillow's paste has ~10–50 µs Python overhead each — total 0.3–1.5 s on a typical laptop, blowing the < 1 s big-map target. The 30×20 path is borderline (estimated 80–150 ms vs a 100 ms budget). Layer alpha compositing through `Image.paste(mask=)` is also clunkier than numpy mask operations on palette index 0.
- **Why not:** Speed risk for negligible install simplification. numpy ships universal wheels everywhere we deploy.

### Alternative 2 — Cairo (pycairo) or Skia (skia-python)
- **Upside:** Mature 2D graphics libraries with hardware-accelerated paths.
- **Downside:** Both pull heavy compiled deps with patchy wheel coverage (skia-python lacks musllinux and some Windows configs; pycairo needs system libcairo). Both target vector graphics; the workload here is uniform 8×8 indexed-tile blits, where numpy + simple PNG encode is structurally better matched.
- **Why not:** Worse install story, no speed advantage for this workload, more API surface to maintain.

### Alternative 3 — Byte-identical PNG fidelity
- **Upside:** Stronger correctness signal; bit-for-bit reproducibility.
- **Downside:** Requires reproducing Qt's libpng filter heuristic, deflate tuning, and chunk set (including `pHYs` and `tIME` choices). Either we fork Pillow's encoder or call into libpng directly with hand-tuned options. Massive engineering for zero user-visible benefit — the agent looks at pixels, not at PNG container bytes.
- **Why not:** Wrong target. The pixel-identical criterion gives the same correctness guarantee for the agent's consumption path.

### Alternative 4 — Read compiled `.4bpp` / `.gbapal`
- **Upside:** Smaller files, no PNG decode at load.
- **Downside:** These files are build artifacts; many pret projects don't keep them under source control. Porymap itself never reads them. A project that doesn't `make` would have stale or missing binaries.
- **Why not:** Diverges from the authoritative source (the artist's PNG + JASC palette).

### Alternative 5 — Render map connections in v1.0
- **Upside:** Matches Porymap's export-with-default-flags exactly. Visually richer renders.
- **Downside:** Each connection drags its neighbor's tileset + layout into the fidelity-test surface. The 5-map corpus becomes a multi-map dependency graph; adding a 6th reference map could pull in 3–4 supporting maps. v1.0 shipping risk grows for a feature whose value is marginal in the early use case (agent looking at *its own* map).
- **Why not:** Defer to v1.1. v1.0's reference exports are produced with "show connections = off"; users get an explicit, predictable image.

### Alternative 6 — Cache metatiles across calls (process-global)
- **Upside:** Skips decode work on the second `render_map` call for the same project.
- **Downside:** Process-global state is exactly what `CLAUDE.md` §4 forbids for parsers and renderers ("Pure parsers ... no global state"). Invalidation on file change is non-trivial (and we just abandoned the file-watcher path for L2). The hot path is fast enough without it.
- **Why not:** Violates the project's architectural rules and solves a non-problem. If a user proves the per-call decode is a bottleneck in real workflows, a future ADR can revisit.

---

## Consequences

- **Positive:**
  - Concrete, citable decode pipeline. Anyone implementing `compose.py` knows exactly which fields and config keys feed which step.
  - Fidelity criterion is testable in CI without library-version flakiness.
  - numpy hot path leaves comfortable headroom against the perf targets.
  - Module layout is one file smaller than phase-4's draft and reflects how the code actually wants to be organized.
  - Renderer is gated behind a `render` extra, so L1-only users don't pay the numpy/Pillow install cost.

- **Negative:**
  - We must read `porymap.project.cfg` keys L1 didn't need (`unused_tile_*`, `transparency_color`, attribute mask overrides). The `ProjectConfig` parser gains a small surface.
  - GBA 5-bit palette quantization (`& 0xF8`) is easy to forget. Will be enforced by the fidelity test, but also called out in `compose.py` docstring + a unit test that checks one palette decode round-trip.
  - v1.0 cannot match Porymap's default export (which includes connections). Documented; mitigated by the explicit "show connections = off" instruction in the fidelity-test procedure.

- **Neutral:**
  - Phase 4 phase doc §3 (module layout) and §7 (fidelity criterion) get updated to match this ADR.
  - Phase 4 phase doc OQ2 (animations) and OQ3 (connections) are resolved by this ADR.

---

## Empirical corrections (2026-05-14, after corpus validation)

Three claims in this ADR were proven wrong by the L3 fidelity corpus
(cases 1-3: Littleroot Town, Route 101, Granite Cave 1F). After fixing
each, the renderer produces 0/261120 differing pixels vs Porymap's
own export on every measured case. Code in `src/porymap_mcp/render/`
and the dependent unit tests reflect the corrected behaviour; the rest
of this ADR (decode pipeline, layer composition, encode strategy,
return shape) stands unchanged.

### Correction 1 — No `& 0xF8` GBA quantization

§"Context" item "GBA hardware quantizes RGB to 5 bits per channel"
and §"Decision" item 2 ("Each RGB component is masked `& 0xF8`")
described an over-engineered safety belt. **Empirically, Porymap does
not quantize JASC palette values on export.** pokeemerald's pal files
already contain the artist's chosen 8-bit RGB (e.g. the grass entry
`57 139 49` is not on a 5-bit boundary), and Porymap propagates those
bytes byte-for-byte through to the rendered PNG. The hardware 5-bit
truncation is what happens at runtime *inside the GBA* when the LCD
driver clocks pixels out — it does not apply to the offline editor's
view of the same palette.

`render/compose.py` no longer applies any quantization mask. The
`transparency_color` config key is also propagated unchanged. Two
unit tests were inverted to enforce the new contract:
`test_jasc_values_passthrough_unchanged` and
`test_misaligned_5bit_values_preserved` (both in `test_compose.py`).

§"Risks" item 5 (which warned about forgetting the masking) is now
moot — the test it referenced (`test_palette_round_trip`) is replaced
by the two passthrough tests above.

### Correction 2 — Border tiling phase is anchored on the map's top-left, not the output's

`render/layout.py::tile_border_around` originally tiled the border
from output pixel `(0, 0)` outward, putting `border[0][0]` at the
top-left corner of the framed image. Wrong: Porymap anchors the phase
on the **map's** top-left corner, so `border[0][0]` lands at output
pixel `(fw_px, fh_px)` and tiles outside the map's bounding box cycle
backwards through the border's metatiles via modulo.

For a 2x2 `border.bin` with four distinct metatiles (the canonical
Littleroot tree-cluster border), the difference between the two
phases is the difference between getting *any* pixel right or *no*
pixels right. Fix is one line — subtract the frame offset from the
output coordinates before the modulo.

### Correction 4 — `unused_tile_*` config keys are packed tile-entry words, not bare tile ids

`render/compose.py::decode_metatile_bank` originally treated
`unused_tile_normal`, `unused_tile_covered`, and `unused_tile_split`
from the project config as raw `tile_id` integers, with palette
hardcoded to 0 and no flips:

    fill_normal = (unused_tile_normal, False, False, 0)  # WRONG

This works for the vanilla pokeemerald default
(`unused_tile_normal=0x0000`, which decodes the same way both wrong
and right) but breaks the moment a fork or expansion sets a non-zero
value with a non-zero palette. pokeemerald-expansion's
`unused_tile_normal=0x3014` is a full packed tile-entry word with the
exact same bit layout as a metatile's own entries (tile_id 0-9, xflip
bit 10, yflip bit 11, palette 12-15). The "wrong" decode treats
`0x3014` as `tile_id=12308`, which is well above the 1024-tile
combined bank cap; the bottom-layer fill silently fell through the
`if tid >= num_tiles: continue` guard and exposed the
`transparency_color=0x000000` background. Only 2 pixels in
`BattleFrontier_OutsideEast` (out of 1.8M) showed black where Porymap
shows the grey of palette 3 indices 3 and 4 — the actual decoded
`unused_tile_normal`.

Fix: decode `unused_tile_*` via the same bit unpacking as a regular
tile entry (one helper, three call sites). After the fix, case 04
matches Porymap byte-for-byte (0/1805312 differing pixels).

### Correction 3 — Border frame is asymmetric (7 horizontal x 5 vertical metatiles), not 7x7

§"Decision" doesn't pin the frame size, but `tools/rendering.py`
shipped with `DEFAULT_BORDER_FRAME_METATILES = 7` (symmetric).
**Porymap's `Metatile::pixelsPerMetatile` view distance is 7
horizontal x 5 vertical metatiles per side**, mirroring half of the
GBA visible screen area (240/16 = 15 metatiles wide x 160/16 = 10
metatiles tall, halved and rounded down to the nearest integer).

Constants split:
- `DEFAULT_BORDER_FRAME_METATILES_HORIZONTAL = 7`
- `DEFAULT_BORDER_FRAME_METATILES_VERTICAL = 5`

`structured_content["border_frame_metatiles"]` is now a dict with
`{"horizontal": 7, "vertical": 5}` keys instead of a single int.
Mutation tools' `return_render` path inherits the asymmetric default
through the same constants.

### Updated risk inventory

The single highest residual risk is now **Correction 4 (unknown)** —
some other Porymap-specific behaviour the corpus hasn't yet exposed.
The fidelity test runner (`tests/integration/test_fidelity.py`) is
designed to catch any such drift on any future case the maintainer
adds; CI fails the corpus on a single mismatching pixel, so a
regression cannot ship silently.

---

## Open questions (deferred)

- **OQ-A — Connection rendering** (Phase 4 §8 OQ3, deferred to v1.1). A future ADR covers the recursive-load semantics and the test-corpus expansion.
- **OQ-B — Vector overlay output**. Should `render_map` optionally return an SVG overlay (events + grid) alongside the raster PNG so an LLM can introspect coordinates? Deferred until the L3 self-critique loop is empirically running.
- **OQ-C — Animated-tile preview frame selection**. For v1.0 we render the static frame baked into `tiles.png`. A future option `animation_frame: int = 0` could read from `tileset_anims.c` to render alternative frames. Deferred until anyone asks.

---

## References

- ADR-0003: `Project` class as single entrypoint, config-driven format parameters (the `ProjectConfig` extension lands there).
- ADR-0004: Tileset metadata source-of-truth (filesystem-first), supersedes here for *graphics* too.
- ADR-0006: L1 mutation-tool conventions — `return_render: bool = False` on the L3 side follows ADR-0006's response shape, augmented with the `Image` content block.
- ADR-0009: L2 abandonment — establishes why L3 is the active phase.
- Phase 4 doc (active): [`../phases/phase-4-l3-vision.md`](../phases/phase-4-l3-vision.md) — updated by the same commit as this ADR.
- Porymap source citations (from the decode-pipeline audit):
  - `src/core/tileset.cpp` — `tiles.png` reader (`loadTilesImage`, 558–623), JASC-PAL reader (646–664), metatile byte layout (454–486).
  - `src/core/paletteutil.cpp` — JASC parser (90–155).
  - `src/core/metatile.cpp` — attribute mask defaults (8–19) and config-override hooks (120–123).
  - `src/ui/imageproviders.cpp` — layer composition with `unused_tile_*` fill (82–115), palette-index-0 alpha (130–134).
  - `src/ui/mapimageexporter.cpp` — RGBA-8888 export format (288–289, 224).
  - `src/config.cpp` — `unused_tile_*` keys (963–967, 1128–1130), `enable_triple_layer_metatiles` (918–919).
- FastMCP image-content pattern: https://gofastmcp.com/servers/tools (`ToolResult` + `Image(data=, format="png")`).
- `.claude/agents/map-renderer.md` — perf targets and design rules.
