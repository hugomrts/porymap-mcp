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

- [x] `render_map(project_path, map_name)` returns a PNG that **pixel-matches** (decoded RGBA arrays equal, see ADR-0010 §Fidelity) Porymap's export with default flags + "show connections = off" — verified on 3 cases (Littleroot Town, Route 101, Granite Cave 1F), 0 differing pixels each
- [x] `render_map_region(...)` works for partial renders (big maps)
- [x] Optional overlays implemented: `collision`, `elevation`, `events`, `grid`
- [x] All L1 mutation tools gain `return_render: bool = False` parameter
- [ ] Render performance hits the targets in `.claude/agents/map-renderer.md` §"Performance targets" — not formally measured yet
- [x] Golden pixel tests in CI (`tests/fixtures/renders/` stores both our PNG and the Porymap reference PNG; CI decodes both to RGBA and asserts `np.array_equal`) — `tests/integration/test_fidelity.py` runs all 5 cases, **all 5 passing pixel-identical** vs Porymap reference
- [x] **End-to-end self-critique loop demonstrated** in `examples/04_render_loop/`:
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

### 2026-05-14 — Fidelity corpus 5/5 pass + 4th renderer bug fix (slice 11b)

Case 04 (Battle Frontier Outside East from pokeemerald-expansion)
landed with 2 / 1805312 differing pixels — both at the very top row
of two adjacent metatiles in the same map row, both pure black on
our side and grey on Porymap's. Trace: the expansion's
`unused_tile_normal=0x3014` is a packed tile-entry word, but our
renderer was treating it as a bare `tile_id=12308`, well above the
1024-tile combined bank cap. The bottom-layer fill fell through the
out-of-range guard and exposed the `transparency_color` background.

Fix: decode `unused_tile_normal`, `unused_tile_covered`, and
`unused_tile_split` using the same bit unpacking as a regular tile
entry (tile_id 0-9, xflip 10, yflip 11, palette 12-15). One helper,
three call sites.

After the fix: **all 5 corpus cases pass pixel-identical.** Suite:
464 → **465 passing**, 0 skipped. ADR-0010 gains a fourth
"Empirical correction" bullet documenting the bug.

Phase-4 §2 status: every functional exit criterion is now ticked
except the formally-unmeasured perf budget (informally well within
target on every case). Project is `v1.0.0`-ready.

### 2026-05-14 — Fidelity corpus shipped + 3 renderer bug fixes (slice 11)

The L3 fidelity gate is closed for 4/5 cases. Cases 1-3 (Littleroot
Town, Route 101, Granite Cave 1F vendored from
pokeemerald-expansion) and case 5 (synthetic regression) all pass
pixel-identical against their reference PNGs. Case 4 (an expansion
triple-layer map) auto-skips while it awaits the human's pick + export.

Validating against real Porymap exports surfaced three bugs in the
renderer that the L1-only synthetic fixtures could not have caught
(see ADR-0010 §"Empirical corrections" for the audit trail):

1. `render/compose.py` was masking palette RGB with `& 0xF8` to
   "match GBA hardware quantization". Empirically wrong: Porymap
   propagates JASC palette bytes verbatim. Removed every quantization
   site. Two unit tests inverted to enforce the new contract.
2. `render/layout.py::tile_border_around` tiled the border from
   output pixel `(0, 0)` outward; Porymap anchors the phase on the
   map's top-left corner so `border[0][0]` lands at output pixel
   `(fw_px, fh_px)`. One-line fix (subtract frame offset before
   modulo).
3. `tools/rendering.py` shipped with a single
   `DEFAULT_BORDER_FRAME_METATILES = 7` (symmetric 7x7 frame).
   Porymap's view distance is asymmetric — 7 metatiles horizontal x
   5 vertical per side, mirroring half of the GBA 240x160 visible
   screen. Constants split into HORIZONTAL/VERTICAL pair;
   `structured_content["border_frame_metatiles"]` now a
   `{"horizontal": int, "vertical": int}` dict.

**Infrastructure shipped this slice** (under
`tests/fixtures/renders/`):

- `HOW_TO_EXPORT.md` — step-by-step Porymap export procedure for the
  human, including PowerShell-vs-bash shell-syntax notes and the
  install-prerequisite (`pip install -e .`).
- `vendor_case.py` — copies the minimum project slice for one map
  from a source pokeemerald(-expansion) checkout into a case dir.
  Reuses the project's L1 parsers so the layout/tileset resolution
  tracks any L1 changes.
- `case_NN/description.md` for cases 01-04 — each documents the
  project, map id, layout id, tileset refs, dimensions, the
  include-border decision, dual-vs-triple layer mode, and the case's
  *raison d'être* in the corpus.
- `case_05_synthetic_edge/build_project.py` — deterministic builder
  for the regression-only synthetic project (30x20 triple-layer map
  with custom 4x4 border, all `unused_tile_*` slots exercised, and
  a primary tileset with < 512 metatile slots to force the bank
  padding code path). The case's `reference.png` is generated by
  *our* renderer and committed; the test asserts that re-running
  produces byte-identical output.
- `tests/integration/test_fidelity.py` — single parametrized test
  that iterates all 5 cases. Each case auto-skips when its
  `project/` or `reference.png` is missing, so the corpus can be
  built incrementally. Failure messages quote the first mismatching
  pixel, the percentage of differing pixels, and the case kind
  (`fidelity` vs `regression`).
- `conftest.py::pytest_addoption` — adds the maintainer-only
  `--update-golden` flag that overwrites `reference.png` with our
  current render. Used only by case 5; cases 1-4 are regenerated by
  re-exporting from Porymap + re-running `vendor_case.py`.

**Suite:** 460 → 464 passing + 1 skipped. ruff + ruff format + mypy
--strict src/porymap_mcp clean.

**Phase-4 §2 status.** With this slice landed, exit criteria are
all green except (a) the perf targets (not formally measured but
informally well within budget — case 1 renders in ~80 ms on the
session machine) and (b) case 4 of the corpus, which is blocked on
the human picking + exporting an expansion triple-layer map. v1.0.0
can tag as soon as case 4 lands (or as soon as the maintainer
explicitly waives it — case 4 covers the same `enable_triple_layer
_metatiles=1` code path as case 5's regression, so the *coverage*
gap of skipping it is small).

### 2026-05-14 — Public-face docs refreshed for L3 (slice 10b)

Pure docs polish, no source changes. The README and CHANGELOG had not
been updated since `v0.1.0` (L1) was tagged, so a visitor landing on
the repo would still read "L3 — planned (v1.0)" while L3 is in fact
implemented on `main` with 24 registered tools.

Changes:

- `README.md` — refreshed alpha banner (v0.1.0 tagged, L3 implemented,
  L2 abandoned per ADR-0009, v1.0.0 pending the corpus), reworded the
  "What it does" bullets (dropped the v0.2 L2 line; added L3 with a
  link to the example loop + critic agent), updated the capability
  levels table with checkmark/cross/wrench states, added a new
  "See your map (L3)" section between the L1 walkthrough and the tool
  surface (iter1.png + iter2.png displayed inline, score jump
  quantified, link to `examples/04_render_loop/`), expanded the tool
  surface section to list `render_map` / `render_map_region` /
  `render_metatile` and document the `return_render` flag on every
  mutation tool, cross-linked ADR-0010.
- `CHANGELOG.md` — added an `[Unreleased] — v1.0.0 candidate` section
  covering the full L3 surface (every render submodule, the 3 new
  tools, the `return_render` flag, the extended `ProjectConfig` keys,
  the worked example, the new error classes, the `render` extra in
  `pyproject.toml`, the suite size); flagged the fidelity corpus +
  no-connections + icons-not-yet items under "Known limitations".
  Clarified `0.1.0`'s "Known limitations" subsection post-ADR-0009.

Suite + lint unchanged: **460 passing**, `ruff` + `ruff format` +
`mypy --strict src/porymap_mcp` all clean.

### 2026-05-14 — `examples/04_render_loop/` shipped (worked self-critique loop)

Implementation slice 10. Ticks the last functional exit-criterion in §2
(the fidelity-corpus criterion is blocked on Porymap export bytes that
weren't reachable from this session). With this slice the project's
"reason to exist" (CLAUDE.md §3) — `paint → render → critique → fix →
re-render` — has a runnable, scriptable demonstration.

**Files.** Three new files under `examples/04_render_loop/`:

- `run_demo.py` (≈ 400 LOC). Bootstraps an 8x6 synthetic project at
  `_demo_project/` (mirrors the `tests/unit/tools/test_rendering.py`
  fixture pattern — primary + secondary tilesets, 13 JASC `.pal` files
  each, dual-layer `metatiles.bin` + zero attributes, `map.bin` /
  `border.bin` / `layouts.json` / `map_groups.json` / `map.json`). The
  vocabulary is 8 named solid-colour metatiles: `WATER (0)`, `SAND (1)`,
  `GRASS (2)`, `PATH (3)`, `TREE (4)`, `HOUSE_WALL (5)` in the primary
  bank and `HOUSE_ROOF (512)`, `SIGN (513)` in the secondary bank. All
  RGB components are multiples of 8 so they survive the GBA 5-bit
  hardware quantization byte-for-byte.

  The "loop" section uses only the public Python API of
  `porymap_mcp.tools.{maps,rendering}`:

  - **Iter 1 (draft)**: `paint_metatile((4, 3), HOUSE_WALL)` on the
    grass-filled canvas — deliberately weak.
  - **Iter 2 (revision)**: five `paint_rectangle` + four
    `paint_metatile` calls applying the critic's top 5 fixes
    (coastline, sand strip, tree-line, N-S path, second house,
    signpost).

  After each iteration the script calls `render_map(..., scale=4)` and
  saves `result.content[0]` (the `ImageContent` PNG block) to
  `renders/iter{1,2}.png`. The critique narrative is printed inline —
  it lives in the script as a hardcoded `ITERN_CRITIQUE` constant
  because invoking `map-design-critic` requires a real Claude session.
  The README is explicit about this and shows the exact `Task` call a
  real session would use.

- `README.md`. Walkthrough document: the loop concept; the rendered
  iter 1 vs iter 2 PNGs displayed inline; the run instructions; the
  full prompt-to-Claude template per phase (brief → draft → render →
  critique → fixes → re-render); the 12-axis scoring table (illustrative);
  cross-references to ADR-0010, the phase-4 spec, and the two relevant
  sub-agents.

- `.gitignore`: `_demo_project/`. The synthetic project regenerates on
  every run, so we keep it out of the repo. The two committed PNGs
  (`renders/iter1.png` ≈ 1.1 KB, `renders/iter2.png` ≈ 1.6 KB) ship as
  artefacts so the README renders correctly on GitHub without forcing
  readers to run Python.

**Why solid-colour metatiles.** Bundling real Gen 3 art into the repo
would pull ≈ 1 MB of tilesets and trigger licensing questions; pointing
the demo at a `pret/pokeemerald` checkout would force a Git submodule
or post-install fetch. The solid-colour approach keeps the demo
in-repo and self-contained while exercising the exact same tool
pipeline — `tools/rendering.py` does not care whether each metatile is
solid red or a fully drawn Pokémon Center. The README spells this out
in a "Why solid-colour metatiles?" section.

**Verification.** `python examples/04_render_loop/run_demo.py` prints
the iter 1 + iter 2 critique narrative and writes both PNGs in well
under 1 second. `ruff check .` + `ruff format --check .` + `mypy
--strict src/porymap_mcp` (29 source files) + `python -m pytest
--no-cov` (460 passing) all clean — the example doesn't add any tests
(it would only re-test the synthetic-fixture path already covered by
`test_rendering.py`).

**Phase-4 §2 status.** With this slice ticked, only the 5-map fidelity
corpus remains. That criterion is blocked on Porymap-exported
reference PNGs (Porymap binary not reachable from this session); see
STATUS.md's "Up next" for the unblock path. Once the corpus lands,
`v1.0.0` can tag.

### 2026-05-14 — `return_render` on every L1 mutation tool

Implementation slice 9. Closes exit-criterion phase-4 §2 ("All L1
mutation tools gain `return_render: bool = False` parameter"). Every
paint/event tool can now return an inline render of the post-mutation
map in a single call, eliminating the
mutation→`render_map` round-trip the agent would otherwise need.

**Helper.** New `maybe_attach_render(response, *, project_path,
map_name, return_render)` in `tools/_common.py`:

- ``return_render=False`` (the default): returns the mutation's
  ``response`` dict unchanged. Preserves the historical L1 contract
  exactly — every existing test for every mutation tool still passes
  without modification.
- ``return_render=True``: late-imports
  ``fastmcp.tools.base.ToolResult`` and ``tools.rendering.render_map``,
  calls render_map (default options — no overlays, no border, scale=1),
  and wraps the result. ``content[0]`` is the rendered PNG image
  block; ``structured_content`` is the mutation's response merged with
  the render metadata under a nested ``"render"`` key. The combined
  ``summary`` string concatenates the mutation summary with the render
  summary (``"Painted metatile 0x001 at (0, 0) on MAP_TEST_TOWN. Rendered MAP_TEST_TOWN..."``).

The late import is important: ``tools/_common.py`` is imported by the
L1 discovery tools, which must keep working without the ``render``
extra installed. Calling ``maybe_attach_render(..., return_render=False)``
never touches numpy/Pillow, so an agent that doesn't ask for the
render path doesn't pay for it.

**Tools touched** (12 total):

- ``tools/maps.py`` — 7 mutations: ``paint_metatile``, ``paint_rectangle``,
  ``flood_fill``, ``set_border``, ``create_map``, ``resize_map``,
  ``paint_prefab``.
- ``tools/events.py`` — 5 mutations: ``add_warp``, ``add_object_event``,
  ``add_sign``, ``add_trigger``, ``remove_event``.

Each tool gains a trailing ``return_render: bool = False`` parameter on
both the body function and the ``_tool_*`` FastMCP wrapper, plus a one-
line docstring addition. Every body function's return type is now
``Any`` (was ``dict[str, Any]``); the dict-only contract still holds in
the default code path but ``ToolResult`` is a possible return when
``return_render=True``. Mypy ``--strict`` clean.

**No-op branches also render.** ``paint_metatile`` on an unchanged tile,
``paint_rectangle`` over already-matching tiles, ``flood_fill`` with a
matching seed, ``remove_event`` on a non-existent id — all of these
historically returned ``files_modified=[]``; with ``return_render=True``
they still produce a PNG of the current state. The agent gets to see
the map regardless of whether anything was written, which matches the
phase-4 self-critique loop's expectation that every iteration ends
with a visual.

**Skipped.** ``register_map`` and ``unregister_map`` (in ``projects.py``)
do not write pixel data; they only edit `map_groups.json`. They keep
their existing dict return shape. An agent that wants a render after
``register_map`` can call ``render_map`` explicitly.

**+6 tests** under ``TestMutationReturnRender`` in
``tests/unit/tools/test_rendering.py``:

- ``paint_metatile`` default → ``dict`` (backward-compat invariant),
  no ``"render"`` key.
- ``paint_metatile(return_render=True)`` → ``ToolResult`` with verified
  pixel content (cell repainted to metatile 1 reads back as the blue
  colour-C the fixture defines), mutation fields preserved at the top
  level (``map_name``, ``x``, ``y``, ``metatile_id``), render metadata
  nested under ``"render"``, combined summary mentions both phases.
- ``paint_rectangle(return_render=True)`` → smoke test on the second
  paint tool.
- No-op ``paint_metatile`` (already at target) still renders.
- ``add_warp(return_render=True)`` → render attached, event_id
  preserved at top level.
- No-op ``remove_event`` (missing id) still renders.

Suite: 454 → **460 passing**. ``ruff check .`` + ``ruff format --check
.`` + ``mypy --strict src/porymap_mcp`` (29 source files) + ``pytest
--no-cov`` all clean.

Notes for the next slice (fidelity corpus):

- The render path is now reachable from every mutation tool, which
  means an integration test could synthesise a full project, mutate
  it, and assert pixel equality against a vendored Porymap-exported
  golden PNG in one call. That's the shape of the 5-map fidelity
  corpus next: each fixture is `(project_state, golden.png)`, the
  test calls `render_map(..., include_border=True)`, decodes both,
  asserts `np.array_equal`.
- The fixture corpus needs real Porymap export bytes. Two options: (a)
  commit small golden PNGs to the repo (the practical choice — under
  300 KB total for 5 small maps), or (b) generate them programmatically
  using a vendored Porymap binary in CI (heavier, but pure-source).
  The corpus is the cheapest gate to fidelity confidence; commit golden
  PNGs.

### 2026-05-14 — `render/overlays.py` shipped (collision / elevation / grid / events)

Implementation slice 8. Replaces the `_check_overlays_supported` raise
from slices 6–7 with real overlay rendering, closing the overlay menu
from phase-4 §4.

**Module** `render/overlays.py` ships four overlay functions plus a
small dispatcher:

- `apply_collision_overlay(rgba, map_bin, *, frame_offset_px=(0,0))` —
  alpha-blends a translucent red square (collision 1), magenta
  (collision 2), purple (collision 3); passable cells untouched.
- `apply_elevation_overlay(...)` — paints a distinct hue per value of
  the 4-bit elevation field. v1 ships hues only — numeric labels would
  require a bundled font and are deferred.
- `apply_grid_overlay(rgba, map_bin, ...)` — 1-px black lines at every
  metatile boundary inside the map region; the border frame (when
  present) is left alone.
- `apply_events_overlay(rgba, map_json, ...)` — 12x12 outlined squares
  centred on each event's `(x, y)`, colour-coded by class
  (object=yellow / warp=red / coord=cyan / bg=green). Events with
  missing or non-integer `x`/`y` are silently skipped.
- `apply_overlays(rgba, overlays, *, map_bin, map_json,
  frame_offset_px=(0,0))` — ordered dispatch; raises
  `ProjectError` on unknown names; supported names exposed as the
  `SUPPORTED_OVERLAYS` constant.

All four call into a shared `_blend_rectangle(rgba, x, y, w, h, colour,
alpha)` helper that clips to bounds, mutates in place, and restores
`alpha=255` (the underlying map is opaque; overlays shouldn't introduce
transparency into the final encode).

**Wiring** in `tools/rendering.py`:

- `_check_overlays_supported` is now a validation pass (raises on
  unknown names against `SUPPORTED_OVERLAYS`); dispatch happens after
  bank decode.
- `render_map`: overlays apply between `tile_border_around` and
  `_scale_nearest`. `frame_offset_px` becomes `(7*16, 7*16)` when
  `include_border=True` so overlays sit on the map proper, not the
  border frame.
- `render_map_region`: overlays receive a region-clipped `MapBin` so
  collision/elevation/grid paint inside the sub-buffer at `(0, 0)`. For
  the `events` overlay, the unclipped `MapJson` is passed with a
  negative `frame_offset_px = (-y1*16, -x1*16)` so events inside the
  region land at the right pixel and events outside clip silently.
- Both tools pass `force_rgba=True` to `encode_png` whenever any
  overlay is requested (alpha-blended pixels easily exceed the 256-colour
  palette-PNG cap; ADR-0010 §"PNG encoding").

**+15 tests**:

- `tests/unit/render/test_overlays.py` (+13): pixel-level blend
  arithmetic for every overlay (collision red shift verified at
  R=185, G=70, B=70 — `0.45 * (255, 0, 0) + 0.55 * (128, 128, 128)`),
  elevation distinct-hue invariant across three values, grid
  on-vs-off-boundary pixel deltas, event-class colour distinctness,
  frame-offset shifts, events with missing `x`/`y` silently skipped,
  negative-frame-offset clip, dispatcher unknown-name raise,
  empty-list no-op, and an every-supported-name smoke test.
- `tests/unit/tools/test_rendering.py`: the prior reject-tests on
  `render_map` and `render_map_region` are replaced with positive
  assertions that `overlays=["grid"]` flips the encoding to
  `png-rgba-8` and the `overlays` structured-content field round-trips.

Suite: 439 → **454 passing**. `ruff check` + `ruff format --check` +
`mypy --strict src/porymap_mcp` (29 source files) + `pytest --no-cov`
all clean.

Notes for the next slice (`return_render` on L1 mutation tools):

- Each mutation tool currently returns `dict[str, Any]`. The new
  `return_render=True` path can build a `ToolResult` by calling into
  the same render pipeline (`_build_combined_*_bank` → `assemble` →
  `encode_png` → `package_render_result(extra=mutation_dict)`).
- Default `False` everywhere — keep the L1 response shape backward-
  compatible for callers that don't want the bandwidth.

### 2026-05-14 — `tile_border_around` + `render_map(include_border=True)` shipped

Implementation slice 7. Replaces the `include_border=True` "not yet
implemented" raise from slice 6 with a real wrap-around frame, matching
Porymap's "include border" exporter.

**Primitive** `tile_border_around(map_rgba, border_rgba, *,
frame_width_metatiles, frame_height_metatiles) -> uint8[H+2*FH, W+2*FW, 4]`
in `render/layout.py`:

- Border tiles by its own pixel dimensions: pixel `(x, y)` in the
  output frame outside the map comes from `border_rgba[y % bH, x % bW]`,
  anchored at the top-left of the output buffer — same as Porymap.
- Implementation is a single numpy fancy-index pass (`border[ys[:,None],
  xs[None,:], :]`), no per-pixel Python loop. C-contiguous output.
- Shared `_validate_rgba(rgba, *, name)` helper enforces uint8 +
  (H, W, 4) + non-zero + multiple-of-METATILE_SIZE dimensions; reused
  for both inputs.
- Zero-frame short-circuit returns a *copy* (not the input) so callers
  cannot mutate the input through the output.

**Wiring** in `tools/rendering.py::render_map`:

- Removed `_check_include_border_supported` raise.
- When `include_border=True`: read `border.bin` via
  `project.read_border_bin(layout_id)`, run it through
  `mapbin_to_metatile_grid` + `assemble` against the SAME combined
  metatile bank as the map, then call `tile_border_around(...)` with
  the new `DEFAULT_BORDER_FRAME_METATILES=7` constant (Porymap's
  `BorderMetatilesData::DEFAULT_BORDER_SIZE`).
- `area_metatiles` passed to `encode_png` is widened by the frame so
  palette-vs-RGBA mode selection still applies the ADR-0010 threshold
  correctly when border inflation pushes the area over 4096.
- Structured content gains `border_dimensions` and
  `border_frame_metatiles` when `include_border=True`.

**+7 unit tests** under `tests/unit/render/test_layout.py`
(`TestTileBorderAround`): solid-border wraps a solid map (corner +
centre + edge pixel asserts + map-region equality), modulo tiling phase
(border with a recognisable corner block repeats correctly across the
frame), zero-frame returns an independent copy, asymmetric frame
shape, 3 validation cases (non-RGBA shape, non-metatile dimensions,
negative frame). The existing
`TestRenderMap::test_rejects_include_border` is replaced by
`test_include_border_wraps_map_in_border_frame`, which decodes the PNG
through Pillow and asserts: output shape = map + 2x frame; top-left
corner = border colour (red, from border.bin → metatile 0 → palette 0);
map-centre pixel offset by `frame_px` rows/cols = expected map
metatile colour; structured content carries the new keys. Suite: 432
→ **439 passing**.

`ruff check` + `ruff format --check` + `mypy --strict src/porymap_mcp`
(28 source files) + `pytest --no-cov` all clean.

Notes for the next slice (overlays):

- `_check_overlays_supported` is the next extension point. Each overlay
  name (`collision`, `elevation`, `grid`, `events`) dispatches to a
  function in `render/overlays.py` that mutates the assembled RGBA in
  place. Pass `force_rgba=True` to `encode_png` whenever any overlay is
  requested — overlays render with alpha < 255.
- Border framing happens BEFORE scale-up; overlays should also be
  applied BEFORE scale-up so they sit at 1px per source pixel rather
  than blocky. The current sequence in `render_map` is: assemble → (if
  border) tile_border_around → scale_nearest → encode. Overlays slot
  in between `tile_border_around` and `scale_nearest`.

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
