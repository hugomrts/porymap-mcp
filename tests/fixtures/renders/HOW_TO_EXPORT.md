# How to export reference PNGs for the fidelity corpus

> This document is for **the human running Porymap**. Claude can't run Porymap; this is the one step that requires you.

## Prerequisites

From the repo root, install `porymap-mcp` in editable mode so `vendor_case.py` can import the parsers:

```bash
pip install -e .
```

(No need for `[dev]` or `[render]` extras — the vendor script only needs the L1 parsers.)

## Shell-syntax note

All multi-line commands below use bash `\` line continuations. On **PowerShell**, replace each `\` at end-of-line with a backtick `` ` ``, or put the whole command on one line.

The fidelity corpus is the last technical gate before `v1.0.0`. CI must be able to compare every byte of our rendered RGBA against Porymap's own RGBA for the same map. If they match across the corpus, we have proof that the L3 renderer is faithful. If they drift, we have a debuggable failure case.

This file documents the **5 reference cases** and the exact Porymap flags you should use when exporting each one. The export takes ~15 minutes total.

---

## Common settings (apply to every export)

In Porymap, open **File → Export Map Image** and set:

| Setting | Value |
|---|---|
| Scale | **1×** |
| Show connections | **OFF** |
| Show grid | **OFF** |
| Show events | **OFF** |
| Show collision | **OFF** |
| Show elevation | **OFF** |
| Show border | per case (see table below) |

Save as PNG. No JPG, no other format.

> **Why these flags?** Our `render_map(...)` default is `overlays=[], scale=1`. The renderer does not support connections in v1.0 (see [ADR-0010 §"Alternatives considered" #5](../../../docs/decisions/0010-l3-renderer-design.md)). The fidelity test compares decoded RGBA arrays, not PNG bytes — so Pillow's vs Qt's PNG containers don't matter, but the pixel content must match identically.

---

## The 5 cases

For each case, place the exported PNG at the path shown. The directory may already contain a `description.md` describing the case; you don't need to edit it.

### Case 1 — Littleroot Town (vanilla)

| | |
|---|---|
| Project | `pret/pokeemerald` (vanilla, **not** expansion) |
| Map | `MAP_LITTLEROOT_TOWN` |
| Include border | **YES** |
| Output | `tests/fixtures/renders/case_01_littleroot_town/reference.png` |

Then run from the repo root:

```bash
python tests/fixtures/renders/vendor_case.py \
    --case case_01_littleroot_town \
    --pokeemerald /path/to/your/pokeemerald \
    --map LittlerootTown
```

(The vendor script copies the minimum project slice — porymap.project.cfg + data/maps/LittlerootTown/* + data/layouts/LittlerootTown/* + the two referenced tilesets — into `tests/fixtures/renders/case_01_littleroot_town/project/`.)

### Case 2 — Route 101 (vanilla)

| | |
|---|---|
| Project | `pret/pokeemerald` (vanilla) |
| Map | `MAP_ROUTE101` |
| Include border | **YES** |
| Output | `tests/fixtures/renders/case_02_route_101/reference.png` |

```bash
python tests/fixtures/renders/vendor_case.py \
    --case case_02_route_101 \
    --pokeemerald /path/to/your/pokeemerald \
    --map Route101
```

### Case 3 — Granite Cave 1F (vanilla)

| | |
|---|---|
| Project | `pret/pokeemerald` (vanilla) |
| Map | `MAP_GRANITE_CAVE_1F` |
| Include border | **NO** (caves don't have a meaningful border) |
| Output | `tests/fixtures/renders/case_03_granite_cave_1f/reference.png` |

```bash
python tests/fixtures/renders/vendor_case.py \
    --case case_03_granite_cave_1f \
    --pokeemerald /path/to/your/pokeemerald \
    --map GraniteCave_1F
```

### Case 4 — A multi-layer expansion map

| | |
|---|---|
| Project | `rh-hideout/pokeemerald-expansion` |
| Map | Your pick — a map that exercises **triple-layer metatiles** (`enable_triple_layer_metatiles=1` in `porymap.project.cfg`). Battle Frontier maps and many post-game expansion-only zones qualify. |
| Include border | **YES** |
| Output | `tests/fixtures/renders/case_04_expansion_layered/reference.png` |

```bash
python tests/fixtures/renders/vendor_case.py \
    --case case_04_expansion_layered \
    --pokeemerald /path/to/your/pokeemerald-expansion \
    --map <YourMapBareName>
```

Tell me which map you picked and I'll update `description.md` to mention it.

### Case 5 — Synthetic edge case

| | |
|---|---|
| Project | **Built by Claude** at `tests/fixtures/renders/case_05_synthetic_edge/project/` (already in the repo when you read this). |
| Map | `MAP_EDGECASETOWN` |
| Include border | **YES** |
| Output | `tests/fixtures/renders/case_05_synthetic_edge/reference.png` |

Open Porymap, **Open Project → tests/fixtures/renders/case_05_synthetic_edge/project/**, then export `MAP_EDGECASETOWN` with the common settings + include border = YES.

The synthetic project deliberately exercises:

- maximum supported map width/height (within a sane corpus budget — see `description.md`)
- triple-layer metatiles (covered / split / normal mix in one map)
- non-zero elevation cells
- a custom border with non-trivial composition
- a primary tileset that uses fewer than 512 metatile slots (forces the bank padding code path in `_build_combined_metatile_bank`)

No `vendor_case.py` step for this case — the project is already in the repo.

---

## After exporting

Once all 5 PNGs are in place, run from the repo root:

```bash
python -m pytest tests/integration/test_fidelity.py -v
```

Expected: all 5 cases pass. If any fail, the test prints the first mismatching pixel coordinate and its (got, want) RGBA — that's the debugging starting point.

If a case is mis-flagged on the Porymap side (wrong scale, connections on, etc.) the test will detect a systematic drift and you can re-export. Don't be afraid to regenerate.

---

## Regenerating goldens after an intentional renderer change

If a change to `src/porymap_mcp/render/` *legitimately* changes pixel output (e.g. a bug fix where Porymap was right and we were wrong), regenerate the goldens with:

```bash
python -m pytest tests/integration/test_fidelity.py --update-golden
```

This overwrites `reference.png` with our render. **Only run this when you're sure our new output is the desired one — verify against a fresh Porymap export of the same case first.** The test refuses to run `--update-golden` in CI to prevent accidental rubber-stamping.

---

## What if I can't run Porymap on a specific case?

Skip it. Don't commit a partial `reference.png`. The fidelity test is configured to skip any case where `reference.png` is missing — CI will report the skipped cases so we can chase them later. Better to ship 4 of 5 than fake one.
