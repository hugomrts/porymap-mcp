# Case 04 — Battle Frontier Outside East (pokeemerald-expansion, triple-layer)

| | |
|---|---|
| Project | `rh-hideout/pokeemerald-expansion` |
| Map | `MAP_BATTLE_FRONTIER_OUTSIDE_EAST` (bare name: `BattleFrontier_OutsideEast`) |
| Layout id | `LAYOUT_BATTLE_FRONTIER_OUTSIDE_EAST` |
| Tilesets | `gTileset_General` (primary) + `gTileset_BattleFrontierOutsideEast` (secondary) |
| Include border | **yes** |
| Dual / triple layer | **triple-layer** (this is the whole point of this case) |
| Why this case | Vanilla pokeemerald is dual-layer everywhere. The expansion is one of the few publicly available projects shipping triple-layer metatiles, and our renderer's most complex composition branch (3 stacked layers, `enable_triple_layer_metatiles=1`, no `unused_tile_*` fallbacks) needs explicit fidelity coverage. The Battle Frontier eastern outdoor map exercises a wide variety of triple-layer metatiles — building tops + ground decoration + foliage — making it a strong cross-section for the renderer's most complex composition branch. |

**Porymap export flags** (per [`HOW_TO_EXPORT.md`](../HOW_TO_EXPORT.md)):
scale **1×**, show connections **off**, all overlays **off**, include border **on**.

**Choosing the map.** Anything that visibly uses three stacked metatile layers works. Good candidates (verify they're triple-layer in your fork):

- `BattleFrontier_OutsideEast` / `BattleFrontier_OutsideWest` (Frontier overworld)
- `BattleFrontier_BattleFactoryLobby` (Factory interior)
- Any map in the expansion's added regions with elaborate ground decoration

Once you've picked one, tell me the bare directory name and I'll fill in the missing fields above.

**To populate this case:**

1. Export the PNG in Porymap to `reference.png` (this directory).
2. Vendor the minimum project slice:
   ```bash
   python tests/fixtures/renders/vendor_case.py \
       --case case_04_expansion_layered \
       --pokeemerald /path/to/your/pokeemerald-expansion \
       --map BattleFrontier_OutsideEast
   ```
