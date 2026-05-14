# Case 01 — Littleroot Town (vanilla pokeemerald)

| | |
|---|---|
| Project | `pret/pokeemerald` (vanilla, **not** expansion) |
| Map | `MAP_LITTLEROOT_TOWN` (bare name: `LittlerootTown`) |
| Layout id | `LAYOUT_LITTLEROOT_TOWN` |
| Tilesets | `gTileset_General` (primary) + `gTileset_LittlerootTown` (secondary) |
| Map size | 20×20 metatiles |
| Include border | **yes** |
| Dual / triple layer | dual-layer (`enable_triple_layer_metatiles=0`) |
| Why this case | The README's "first map" hello-world. A small town with houses, fences, a researcher's lab, and a sandy yard. Exercises the small dual-layer mapping path with a reasonable variety of metatiles, palette slots, and one bordered town map.json (warps + signs + bg events). |

**Porymap export flags** (per [`HOW_TO_EXPORT.md`](../HOW_TO_EXPORT.md)):
scale **1×**, show connections **off**, all overlays **off**, include border **on**.

**To populate this case:**

1. Export the PNG in Porymap to `reference.png` (this directory).
2. Vendor the minimum project slice:
   ```bash
   python tests/fixtures/renders/vendor_case.py \
       --case case_01_littleroot_town \
       --pokeemerald /path/to/your/pokeemerald \
       --map LittlerootTown
   ```
