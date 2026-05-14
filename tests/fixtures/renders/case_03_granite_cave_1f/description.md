# Case 03 — Granite Cave 1F (vanilla pokeemerald)

| | |
|---|---|
| Project | `pret/pokeemerald` (vanilla) |
| Map | `MAP_GRANITE_CAVE_1F` (bare name: `GraniteCave_1F`) |
| Layout id | `LAYOUT_GRANITE_CAVE_1F` |
| Tilesets | `gTileset_Cave` (primary, typical) + map-specific secondary — verify on export |
| Map size | small interior map (≈ 12×12; verify) |
| Include border | **no** (caves render the dark void; not meaningful to compare) |
| Dual / triple layer | dual-layer |
| Why this case | An interior. Cave tilesets exercise a very different palette + metatile vocabulary than overworld maps — different stair / ladder / rock metatiles, fewer "biome" colours, and the metatile elevation field is genuinely used (ledges). The "no border" branch of `render_map` is also exercised here, which is otherwise only hit by the synthetic tests. |

**Porymap export flags** (per [`HOW_TO_EXPORT.md`](../HOW_TO_EXPORT.md)):
scale **1×**, show connections **off**, all overlays **off**, include border **off**.

**To populate this case:**

1. Export the PNG in Porymap to `reference.png` (this directory). **Uncheck "include border"** for this case.
2. Vendor the minimum project slice:
   ```bash
   python tests/fixtures/renders/vendor_case.py \
       --case case_03_granite_cave_1f \
       --pokeemerald /path/to/your/pokeemerald \
       --map GraniteCave_1F
   ```
