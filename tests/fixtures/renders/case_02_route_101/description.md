# Case 02 — Route 101 (vanilla pokeemerald)

| | |
|---|---|
| Project | `pret/pokeemerald` (vanilla) |
| Map | `MAP_ROUTE101` (bare name: `Route101`) |
| Layout id | `LAYOUT_ROUTE101` |
| Tilesets | `gTileset_General` (primary) + `gTileset_PetalburgWoods` (secondary) — verify on export |
| Map size | 10×20 metatiles (the south-north stretch out of Littleroot) |
| Include border | **yes** |
| Dual / triple layer | dual-layer |
| Why this case | The classic "first route" — a single tall map of grass, tree borders, and the long path to Oldale. Exercises tree-clusters (tile flipping in metatile entries), a tall-thin aspect ratio that stresses the border-tiling code differently from Littleroot's square footprint, and tall-grass encounter cells. |

**Porymap export flags** (per [`HOW_TO_EXPORT.md`](../HOW_TO_EXPORT.md)):
scale **1×**, show connections **off**, all overlays **off**, include border **on**.

**To populate this case:**

1. Export the PNG in Porymap to `reference.png` (this directory).
2. Vendor the minimum project slice:
   ```bash
   python tests/fixtures/renders/vendor_case.py \
       --case case_02_route_101 \
       --pokeemerald /path/to/your/pokeemerald \
       --map Route101
   ```
